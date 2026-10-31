"""学习技巧（词汇替换 / 上下义词 / 做题技巧）的存储：并发保存不丢、写坏的文件不被覆盖、接口行为不变。

数据目录都在临时目录里（见 AppTestBase），内容都是编造的。
"""

import json
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_auth_guard import AppTestBase  # noqa: E402

BASE = '/api/study_techniques'
PAYLOADS = {
    'synonyms': lambda i: {'title': f'组 {i}', 'synonyms': [{'word': f'word{i}', 'definition': f'释义{i}'}]},
    'hypernyms': lambda i: {'title': f'组 {i}', 'upper_words': [{'word': f'upper{i}', 'definition': ''}],
                            'lower_words': [{'word': f'lower{i}', 'definition': ''}]},
    'techniques': lambda i: {'title': f'技巧 {i}', 'content': f'## 第 {i} 节\n\n内容'},
}


class StudyTipsStorageTest(AppTestBase):
    def setUp(self):
        super().setUp()
        self.data_dir = sys.modules['routers.study_tips'].STUDY_TECHNIQUES_DATA_DIR
        os.makedirs(self.data_dir, exist_ok=True)

    def path(self, data_type, category='reading'):
        return os.path.join(self.data_dir, f'{category}_{data_type}.json')

    def raw(self, data_type, category='reading'):
        with open(self.path(data_type, category), encoding='utf-8') as f:
            return f.read()

    def post(self, data_type, body, client=None):
        return (client or self.client).post(f'{BASE}/{data_type}/reading', json=body, headers=self.auth())

    def run_threads(self, jobs):
        errors = []

        def wrap(job):
            def run():
                try:
                    job(self.app.test_client())
                except Exception as exc:   # pragma: no cover - 只在失败时有用
                    errors.append(exc)
            return run

        threads = [threading.Thread(target=wrap(job)) for job in jobs]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])

    def assert_no_temp_files(self):
        leftovers = [f for f in os.listdir(self.data_dir) if f.endswith('.tmp')]
        self.assertEqual(leftovers, [])

    # ---------- 并发 ----------

    def test_concurrent_adds_keep_every_entry(self):
        for data_type, make in PAYLOADS.items():
            with self.subTest(data_type=data_type):
                statuses = []

                def job(client, i):
                    statuses.append(self.post(data_type, make(i), client).status_code)

                self.run_threads([lambda c, i=i: job(c, i) for i in range(30)])
                self.assertEqual(statuses, [200] * 30)
                stored = json.loads(self.raw(data_type))
                self.assertEqual(sorted(e['title'] for e in stored), sorted(make(i)['title'] for i in range(30)))
                self.assertEqual(len({e['id'] for e in stored}), 30)
                self.assert_no_temp_files()

    def test_concurrent_deletes_and_adds_do_not_undo_each_other(self):
        seeded = [self.post('synonyms', PAYLOADS['synonyms'](i)).get_json()['id'] for i in range(20)]
        doomed = seeded[:10]
        jobs = [lambda c, item_id=item_id: c.delete(f'{BASE}/synonyms/reading/{item_id}', headers=self.auth())
                for item_id in doomed]
        jobs += [lambda c, i=i: self.post('synonyms', PAYLOADS['synonyms'](100 + i), c) for i in range(10)]
        self.run_threads(jobs)
        stored = json.loads(self.raw('synonyms'))
        ids = {e['id'] for e in stored}
        self.assertTrue(ids.isdisjoint(doomed))
        self.assertTrue(set(seeded[10:]) <= ids)
        self.assertEqual(len(stored), 20)

    # ---------- 写到一半出错 ----------

    def test_failed_write_leaves_previous_file_intact(self):
        self.post('synonyms', PAYLOADS['synonyms'](1))
        before = self.raw('synonyms')
        real_dump = json.dump

        def broken_dump(obj, fp, *args, **kwargs):
            fp.write('[{"id": "half-written')
            raise OSError('disk full')

        json.dump = broken_dump
        try:
            response = self.post('synonyms', PAYLOADS['synonyms'](2))
        finally:
            json.dump = real_dump
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.raw('synonyms'), before)
        self.assert_no_temp_files()
        self.assertEqual(len(self.client.get(f'{BASE}/synonyms/reading', headers=self.auth()).get_json()), 1)

    # ---------- 文件写坏了 ----------

    def test_unreadable_file_is_never_overwritten(self):
        for data_type, make in PAYLOADS.items():
            for broken in ('[{"id": "a", "title": "写到一半', '{"not": "a list"}', ''):
                with self.subTest(data_type=data_type, broken=broken):
                    with open(self.path(data_type), 'w', encoding='utf-8') as f:
                        f.write(broken)
                    url = f'{BASE}/{data_type}/reading'
                    responses = [
                        self.client.get(url, headers=self.auth()),
                        self.post(data_type, make(1)),
                        self.client.put(f'{url}/a', json=make(1), headers=self.auth()),
                        self.client.delete(f'{url}/a', headers=self.auth()),
                    ]
                    for response in responses:
                        self.assertEqual(response.status_code, 500)
                        self.assertEqual(response.get_json(), {'error': 'Data file is unreadable'})
                    self.assertEqual(self.raw(data_type), broken)

    def test_missing_file_reads_as_empty_and_first_save_creates_it(self):
        self.assertEqual(self.client.get(f'{BASE}/hypernyms/writing', headers=self.auth()).get_json(), [])
        response = self.client.post(f'{BASE}/hypernyms/writing', json=PAYLOADS['hypernyms'](1), headers=self.auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(json.loads(self.raw('hypernyms', 'writing'))), 1)

    # ---------- 接口行为不变 ----------

    def test_group_title_rules_unchanged(self):
        item_id = self.post('synonyms', PAYLOADS['synonyms'](1)).get_json()['id']
        url = f'{BASE}/synonyms/reading/{item_id}'
        words = [{'word': 'kept', 'definition': ''}]

        self.client.put(url, json={'synonyms': words}, headers=self.auth())
        self.assertEqual(json.loads(self.raw('synonyms'))[0]['title'], '组 1')   # 不传 title：保留旧标题

        self.client.put(url, json={'synonyms': words, 'title': ''}, headers=self.auth())
        stored = json.loads(self.raw('synonyms'))[0]
        self.assertNotIn('title', stored)                                        # 传空字符串：删掉标题
        self.assertEqual(stored['synonyms'], words)

        untitled = self.post('hypernyms', {'lower_words': words}).get_json()
        self.assertNotIn('title', json.loads(self.raw('hypernyms'))[0])
        self.assertEqual(self.post('hypernyms', {'upper_words': [], 'lower_words': []}).status_code, 400)
        self.assertTrue(untitled['success'])

    def test_technique_round_trip_unchanged(self):
        self.assertEqual(self.post('techniques', {'title': '  ', 'content': 'x'}).status_code, 400)
        item_id = self.post('techniques', {'title': ' 标题 ', 'content': '\n## 一\n\n正文\n'}).get_json()['id']
        stored = json.loads(self.raw('techniques'))[0]
        self.assertEqual((stored['title'], stored['content']), ('标题', '## 一\n\n正文'))
        url = f'{BASE}/techniques/reading/{item_id}'
        self.assertEqual(self.client.put(url, json={'title': '新', 'content': '新内容'}, headers=self.auth()).status_code, 200)
        self.assertEqual(json.loads(self.raw('techniques'))[0]['content'], '新内容')
        self.assertEqual(self.client.delete(url, headers=self.auth()).status_code, 200)
        self.assertEqual(self.client.delete(url, headers=self.auth()).status_code, 404)
        self.assertEqual(json.loads(self.raw('techniques')), [])


if __name__ == '__main__':
    unittest.main()
