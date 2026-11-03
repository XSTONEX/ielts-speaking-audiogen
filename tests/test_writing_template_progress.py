"""模板写作：练习进度只算复习中心里的记录；题型详情带上总结构，「打开总结构」才打得开。

语料是编的，写进临时目录（见 AppTestBase）。
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_auth_guard import AppTestBase  # noqa: E402

RECORD = {'task': 'task2', 'type_id': 'opinion', 'question_id': 'q1', 'section_id': 'intro',
          'sentence_index': 0, 'target_chinese': '目标', 'user_translation': 'answer',
          'score': '6.5', 'feedback': {'score': '6.5'}, 'save_to_review': True}

# 和导入脚本的输出一样：参考资料只挂在 big 顶层，题型上没有 references
CORPUS = {
    'generated_at': '2026-11-03T09:00:00',
    'big': {
        'types': [{'id': 'opinion', 'name': '观点型', 'variants': [], 'samples': []},
                  {'id': 'discuss', 'name': '讨论型', 'variants': [], 'samples': [],
                   'references': [{'id': 'own', 'name': '讨论型自带资料', 'kind': '句型库'}]}],
        'references': [
            {'id': 'ex', 'name': '一篇作文的举例（视频讲解）', 'kind': '举例子', 'groups': []},
            {'id': 'st', 'name': '总结构（视频讲解）', 'kind': '讨论型', 'groups': []},
        ],
    },
    'small': {'charts': []},
}


class TemplateProgressTest(AppTestBase):
    def progress(self):
        resp = self.client.get('/api/writing/template/progress', headers=self.auth())
        self.assertEqual(resp.status_code, 200, resp.get_json())
        return resp.get_json()

    def test_removed_record_no_longer_ticks(self):
        rid = self.client.post('/api/writing/template/save_practice', json=RECORD,
                               headers=self.auth()).get_json()['id']
        self.assertEqual(self.progress()['opinion']['q1']['sections']['intro']['count'], 1)

        self.client.post(f'/api/writing/template/set_in_review/{rid}', json={'in_review': False},
                         headers=self.auth())
        self.assertEqual(self.progress(), {})

        self.client.post(f'/api/writing/template/set_in_review/{rid}', json={'in_review': True},
                         headers=self.auth())
        self.assertEqual(self.progress()['opinion']['q1']['count'], 1)


class TemplateReferenceTest(AppTestBase):
    def setUp(self):
        super().setUp()
        import routers.writing_logic as wl
        self.write_json(wl.WRITING_TEMPLATE_FILE, CORPUS)
        self._patch(wl, '_template_cache', None)

    def detail(self, type_id):
        resp = self.client.get(f'/api/writing/template/big/{type_id}', headers=self.auth())
        self.assertEqual(resp.status_code, 200, resp.get_json())
        return resp.get_json()

    def test_type_gets_top_level_references_structure_first(self):
        refs = self.detail('opinion')['references']
        self.assertEqual([r['id'] for r in refs], ['st', 'ex'])
        self.assertEqual(set(refs[0]), {'id', 'name', 'kind'})
        # 补上的 id 在资料接口里真能打开
        resp = self.client.get('/api/writing/template/reference/st', headers=self.auth())
        self.assertEqual(resp.get_json()['name'], '总结构（视频讲解）')

    def test_type_with_own_references_keeps_them(self):
        self.assertEqual([r['id'] for r in self.detail('discuss')['references']], ['own'])

    def test_corpus_file_is_not_modified(self):
        import routers.writing_logic as wl
        self.detail('opinion')
        with open(wl.WRITING_TEMPLATE_FILE, encoding='utf-8') as f:
            self.assertNotIn('references', json.load(f)['big']['types'][0])
        self.assertNotIn('references', wl._load_template_corpus()['big']['types'][0])


if __name__ == '__main__':
    unittest.main()
