"""听力精听：九分学长 JSON 导入（预解析 → 导入 → 下载音频 → 只翻译）和同一个 Part 再导入。

两份 fixture（tests/fixtures/jiufen_listening_*.json）是编造的，结构照九分学长接口（单篇练习、组卷）。
下载、转录、润色翻译、读音频时长都换成桩，不发任何网络请求。
"""

import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_auth_guard import AppTestBase  # noqa: E402
from utils import jiufen_listening  # noqa: E402
from utils.jiufen_import import JiufenFormatError  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')


def fixture_text(name):
    with open(os.path.join(FIXTURES, name), encoding='utf-8') as f:
        return f.read()


SINGLE = fixture_text('jiufen_listening_single.json')
MIXED = fixture_text('jiufen_listening_mixed.json')


class ParseTest(unittest.TestCase):
    def test_single_attempt(self):
        r = jiufen_listening.parse(SINGLE)
        self.assertEqual(r['kind'], 'single')
        self.assertEqual(r['submitted_at'], '2026-09-24T08:05:08')
        self.assertEqual(r['elapsed_seconds'], 303)
        [part] = r['parts']
        self.assertEqual(part['label'], 'Part 1')
        self.assertEqual(part['title'], 'Riverside Bike Hire')   # unit.title
        self.assertEqual(part['audio_url'], 'https://static.example.com/practice/part/riverside.mp3')
        self.assertEqual([s['id'] for s in part['segments']], list(range(10)))
        self.assertEqual(part['duration'], 68.0)
        self.assertEqual([g['kind'] for g in part['groups']], ['blank', 'choice'])
        q1 = part['groups'][0]['questions'][0]
        self.assertEqual((q1['num'], q1['answer'], q1['evidence']), ('1', '12|twelve', [5, 5]))
        self.assertEqual(q1['analysis']['explain'], '录音说半天十二英镑，含头盔。')
        att = part['attempt']
        self.assertEqual(att['id'], '9100000000000000500')
        self.assertEqual((att['correct'], att['total']), (3, 5))
        self.assertEqual(att['answers']['3'], {'user': 'hill', 'state': 'wrong'})
        self.assertEqual(att['answers']['4'], {'user': '', 'state': 'blank'})
        summary = jiufen_listening.summarize(part)
        self.assertEqual((summary['wrong'], summary['blank'], summary['marks']), (['3'], ['4'], 5))

    def test_silence_folded_into_first_word_is_trimmed(self):
        # "Now" 从 13.2 秒拖到 40.9 秒（看题静音），句子开头按这个词结束前半秒算
        seg = jiufen_listening.parse(SINGLE)['parts'][0]['segments'][3]
        self.assertEqual(seg['text'], 'Now listen carefully and answer questions 1 to 4.')
        self.assertEqual((seg['start'], seg['end']), (40.4, 44.6))

    def test_highlights_in_question_layout_and_in_choice_text(self):
        part = jiufen_listening.parse(SINGLE)['parts'][0]
        marks = part['attempt']['marks']
        layout = jiufen_listening.text_content(json.loads(SINGLE)['data']['attempt']['parts'][0]['groups'][0]['contentHtml'])
        for m in [m for m in marks if m['g'] == 0]:
            self.assertNotIn('q', m)
            self.assertEqual(layout[m['start']:m['end']], m['text'])
        choice = part['groups'][1]['questions'][0]
        stem = next(m for m in marks if m['text'] == 'electric')
        self.assertEqual((stem['q'], stem['o']), ('5', None))
        self.assertEqual(choice['text'][stem['start']:stem['end']], 'electric')
        opt = next(m for m in marks if m['text'] == 'steep')
        self.assertEqual((opt['q'], opt['o']), ('5', 'B'))
        self.assertEqual(choice['options'][1]['text'][opt['start']:opt['end']], 'steep')

    def test_highlight_with_shifted_offset_is_found_nearby(self):
        obj = json.loads(SINGLE)
        for a in obj['data']['annotationSnapshot']['annotations']:
            a['range']['start'] += 2   # 复制时空白被收过，下标偏了几位
        words = [m['text'] for m in jiufen_listening.parse(obj)['parts'][0]['attempt']['marks']]
        self.assertEqual(sorted(words), sorted(['Half-day', 'old', 'under', 'electric', 'steep']))

    def test_composition_matches_children_by_part_id(self):
        r = jiufen_listening.parse(MIXED)
        self.assertEqual(r['kind'], 'composition')
        self.assertIsNone(r['elapsed_seconds'])
        p2, p4 = r['parts']
        self.assertEqual((p2['label'], p2['title']), ('Part 2', ''))          # 组卷没有题目名
        self.assertEqual((p4['label'], p4['title']), ('Part 4', 'Urban Beekeeping'))  # 题组带的 title
        self.assertEqual([g['kind'] for g in p2['groups']], ['choice', 'match'])
        self.assertEqual(p2['attempt']['id'], '9200000000000000702')
        self.assertEqual(p4['attempt']['id'], '9200000000000000704')
        self.assertEqual(p2['attempt']['answers']['13'], {'user': 'C', 'state': 'wrong'})
        self.assertEqual([m['text'] for m in p2['attempt']['marks']], ['visitors', 'ferry', 'campsites'])
        self.assertEqual([m['text'] for m in p4['attempt']['marks']], ['placed', 'feel'])

    def test_paste_that_lost_its_backslashes_explains_why(self):
        # 从网页复制时里层 JSON 引号前的反斜杠丢了；换行的 \r\n 有时留着、有时也被收成空格
        lost = SINGLE.replace('\\"', '"')
        for broken in (lost, lost.replace('\\r\\n', ' ')):
            with self.assertRaises(JiufenFormatError) as ctx:
                jiufen_listening.parse(broken)
            self.assertIn('反斜杠', str(ctx.exception))
            self.assertRegex(str(ctx.exception), r'第 \d+ 行第 \d+ 列')

    def test_truncated_paste_says_it_may_be_incomplete(self):
        with self.assertRaises(JiufenFormatError) as ctx:
            jiufen_listening.parse(SINGLE[:len(SINGLE) // 2] + '}')
        self.assertIn('没复制完整', str(ctx.exception))

    def test_reading_json_is_refused(self):
        obj = json.loads(SINGLE)
        obj['data']['attempt']['channel'] = 'reading'
        with self.assertRaises(JiufenFormatError) as ctx:
            jiufen_listening.parse(obj)
        self.assertIn('阅读', str(ctx.exception))


class ImportApiTest(AppTestBase):
    def setUp(self):
        super().setUp()
        self.lr = sys.modules['routers.listening_review']
        self._patch(self.lr, '_active_jobs', {})
        self._patch(self.lr, '_jiufen_previews', {})
        self.downloads, self.asr_calls, self.polish_calls = [], [], []
        self.download_error = None
        self.audio_seconds = 70.0

        def fake_download(url, path):
            self.downloads.append(url)
            if self.download_error:
                return None, self.download_error
            with open(path, 'wb') as f:
                f.write(b'ID3 fake audio')
            return path, None

        def fake_transcribe(audio_path):
            self.asr_calls.append(audio_path)
            return {'segments': [{'id': 0, 'start': 0.0, 'end': 2.0, 'text': 'whisper text'}], 'duration': 2.0}, None

        def fake_polish(segments):
            self.polish_calls.append(segments)
            return [{'id': s['id'], 'text': s['text'], 'translation': f'译文{s["id"]}'} for s in segments], None

        self._patch(self.lr, '_download_audio_from_url', fake_download)
        self._patch(self.lr, '_transcribe', fake_transcribe)
        self._patch(self.lr, '_polish_and_translate', fake_polish)
        self._patch(self.lr, 'probe_duration', lambda path: self.audio_seconds)

    # ---------- helpers ----------

    def lr_path(self, *parts):
        return os.path.join(self.lr.LISTENING_REVIEW_DIR, *parts)

    def wait_jobs(self):
        for thread in list(self.lr._active_jobs.values()):
            thread.join(5)
            self.assertFalse(thread.is_alive(), 'background job did not finish')

    def preview(self, raw, token=None):
        headers = {'Authorization': f'Bearer {token or self.token}', 'Content-Type': 'text/plain; charset=utf-8'}
        return self.client.post('/api/listening_review/jiufen/preview', data=raw.encode('utf-8'), headers=headers)

    def do_import(self, key, parts, token=None):
        return self.client.post('/api/listening_review/jiufen/import', json={'key': key, 'parts': parts},
                                headers={'Authorization': f'Bearer {token or self.token}'})

    def preview_ok(self, raw):
        response = self.preview(raw)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def projects(self):
        return self.client.get('/api/listening_review/list', headers=self.auth()).get_json()['projects']

    def import_single(self, raw=SINGLE, **choice):
        r = self.preview_ok(raw)
        choice = {'index': 0, 'mode': 'new', 'title': 'Riverside Bike Hire', **choice}
        response = self.do_import(r['key'], [choice])
        self.assertEqual(response.status_code, 200, response.get_json())
        self.wait_jobs()
        return r, response.get_json()

    def another_attempt(self, attempt_id, user3):
        obj = json.loads(SINGLE)
        att = obj['data']['attempt']
        att['id'] = attempt_id
        att['submittedAt'] = '2026-10-31 09:00:00'
        q3 = att['parts'][0]['groups'][0]['questions'][2]
        q3['userAnswer'], q3['state'] = user3, '1' if user3 == 'mill' else '2'
        obj['data']['annotationSnapshot']['annotations'] = obj['data']['annotationSnapshot']['annotations'][:1]
        return json.dumps(obj, ensure_ascii=False)

    # ---------- 预解析 ----------

    def test_preview_lists_parts_and_keeps_the_upload(self):
        r = self.preview_ok(MIXED)
        self.assertEqual(r['kind'], 'composition')
        self.assertEqual([p['label'] for p in r['parts']], ['Part 2', 'Part 4'])
        self.assertEqual([p['title'] for p in r['parts']], ['', 'Urban Beekeeping'])
        self.assertEqual(r['parts'][0]['wrong'], ['11', '13'])
        self.assertNotIn('existing', r['parts'][0])
        self.assertIn(r['key'], self.lr._jiufen_previews)

    def test_preview_reports_broken_json(self):
        response = self.preview('{"code": 0, "data": {')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.get_json()['format_error'])

    def test_preview_needs_login(self):
        response = self.client.post('/api/listening_review/jiufen/preview', data=SINGLE)
        self.assertEqual(response.status_code, 401)

    # ---------- 导入：下载音频 → 用 JSON 的字幕 → 只翻译 ----------

    def test_import_downloads_audio_and_translates_json_transcript_without_asr(self):
        _, result = self.import_single()
        [created] = result['created']
        pid = created['id']

        self.assertEqual(self.downloads, ['https://static.example.com/practice/part/riverside.mp3'])
        self.assertEqual(self.asr_calls, [])
        self.assertEqual(len(self.polish_calls), 1)
        self.assertEqual([s['id'] for s in self.polish_calls[0]], list(range(10)))

        [p] = self.projects()
        self.assertEqual(p['status'], 'completed')
        self.assertEqual(p['title'], 'Part 1 · Riverside Bike Hire')
        self.assertEqual(p['source_type'], 'jiufen')
        self.assertEqual(p['score'], {'correct': 3, 'total': 5})
        self.assertEqual(p['attempt_count'], 1)
        self.assertTrue(os.path.exists(self.lr_path(pid, 'original.mp3')))

        detail = self.client.get(f'/api/listening_review/project/{pid}', headers=self.auth()).get_json()
        self.assertEqual(detail['data']['segments'][5]['text'], "It's twelve pounds for half a day, and that includes a helmet.")
        self.assertEqual(detail['data']['segments'][5]['translation'], '译文5')
        exam = detail['exam']
        self.assertTrue(exam['aligned'])
        self.assertEqual(exam['part_id'], '9100000000000000001')
        self.assertEqual(len(exam['groups']), 2)
        [att] = exam['attempts']
        self.assertEqual(att['answers']['3']['user'], 'hill')
        self.assertEqual(len(att['marks']), 5)

    def test_untitled_part_is_named_after_its_label(self):
        r = self.preview_ok(MIXED)
        response = self.do_import(r['key'], [{'index': 0, 'mode': 'new', 'title': ''},
                                             {'index': 1, 'mode': 'new', 'title': 'Urban Beekeeping'}])
        self.assertEqual(len(response.get_json()['created']), 2)
        self.wait_jobs()
        self.assertEqual(sorted(p['title'] for p in self.projects()), ['Part 2', 'Part 4 · Urban Beekeeping'])

    def test_preview_can_only_be_imported_once_and_by_its_owner(self):
        r = self.preview_ok(SINGLE)
        self.write_json(self.users_file, {
            **self.read_json(self.users_file),
            'other': {'username': 'other', 'password': 'pw', 'display_name': 'Other', 'role': 'user', 'avatar': 'avatar_admin.svg'},
        })
        other = self.login('other', 'pw')
        self.assertEqual(self.do_import(r['key'], [{'index': 0, 'mode': 'new'}], token=other).status_code, 410)
        self.assertEqual(self.do_import(r['key'], [{'index': 0, 'mode': 'new'}]).status_code, 200)
        response = self.do_import(r['key'], [{'index': 0, 'mode': 'new'}])
        self.assertEqual(response.status_code, 410)
        self.assertTrue(response.get_json()['expired'])
        self.wait_jobs()

    def test_failed_download_is_retried_by_downloading_again(self):
        self.download_error = '下载失败: HTTP 403'
        self.import_single()
        [p] = self.projects()
        self.assertEqual((p['status'], p['error_phase']), ('error', 'download'))
        self.assertEqual(p['error'], 'HTTP 403，可能是链接过期了')
        self.assertEqual(self.polish_calls, [])

        self.download_error = None
        response = self.client.post(f"/api/listening_review/project/{p['id']}/retry", headers=self.auth())
        self.assertEqual(response.get_json()['phase'], 'download')
        self.wait_jobs()
        self.assertEqual(self.projects()[0]['status'], 'completed')
        self.assertEqual(len(self.downloads), 2)
        self.assertEqual(self.asr_calls, [])

    def test_audio_that_does_not_match_the_transcript_is_transcribed_instead(self):
        self.audio_seconds = 20.0   # JSON 的字幕到 68 秒，音频只有 20 秒：不是同一段
        _, result = self.import_single()
        pid = result['created'][0]['id']
        self.assertEqual(len(self.asr_calls), 1)
        detail = self.client.get(f'/api/listening_review/project/{pid}', headers=self.auth()).get_json()
        self.assertEqual(detail['project']['status'], 'completed')
        self.assertEqual(detail['data']['segments'][0]['text'], 'whisper text')
        self.assertFalse(detail['exam']['aligned'])

    def test_restart_while_downloading_is_marked_as_download_failure(self):
        r = self.preview_ok(SINGLE)
        self._patch(self.lr, '_start_thread', lambda *a, **k: None)   # 线程没跑起来就"重启"了
        self.do_import(r['key'], [{'index': 0, 'mode': 'new'}])
        [p] = self.projects()
        self.assertEqual((p['status'], p['error_phase']), ('error', 'download'))

    # ---------- 同一个 Part 再导入 ----------

    def test_reimport_same_attempt_replaces_answers_and_keeps_notes(self):
        _, first = self.import_single()
        pid = first['created'][0]['id']
        note = self.client.put(f'/api/listening_review/project/{pid}/note', headers=self.auth(), json={
            'segment_id': 7, 'quote': 'old mill', 'note': '磨坊', 'start_offset': 32, 'end_offset': 40})
        self.assertEqual(note.status_code, 200)

        obj = json.loads(SINGLE)
        obj['data']['annotationSnapshot']['annotations'].append(copy.deepcopy(obj['data']['annotationSnapshot']['annotations'][0]))
        obj['data']['annotationSnapshot']['annotations'][-1]['range'].update(start=55, end=60, text='route')
        r = self.preview_ok(json.dumps(obj, ensure_ascii=False))
        existing = r['parts'][0]['existing']
        self.assertEqual(existing['id'], pid)
        self.assertTrue(existing['same_attempt'])
        self.assertEqual(existing['attempt_count'], 1)

        response = self.do_import(r['key'], [{'index': 0, 'mode': 'update'}])
        self.assertEqual(response.get_json()['updated'], [{'id': pid, 'label': 'Part 1', 'how': 'replaced', 'attempt_count': 1}])
        self.assertEqual(self.lr._active_jobs, {})
        self.assertEqual(len(self.downloads), 1)        # 没有重新下载
        self.assertEqual(len(self.polish_calls), 1)     # 也没有重新翻译
        detail = self.client.get(f'/api/listening_review/project/{pid}', headers=self.auth()).get_json()
        [att] = detail['exam']['attempts']
        self.assertEqual(len(att['marks']), 6)
        self.assertEqual([n['note'] for n in detail['data']['notes']], ['磨坊'])
        self.assertEqual(len(self.projects()), 1)

    def test_reimport_new_attempt_is_kept_as_second_attempt(self):
        _, first = self.import_single()
        pid = first['created'][0]['id']
        r = self.preview_ok(self.another_attempt('9100000000000000501', 'mill'))
        self.assertFalse(r['parts'][0]['existing']['same_attempt'])
        self.assertEqual(r['parts'][0]['existing']['previous'], {'correct': 3, 'total': 5})

        response = self.do_import(r['key'], [{'index': 0, 'mode': 'update'}])
        self.assertEqual(response.get_json()['updated'][0]['how'], 'added')
        [p] = self.projects()
        self.assertEqual(p['attempt_count'], 2)
        self.assertEqual(p['score'], {'correct': 4, 'total': 5})
        attempts = self.client.get(f'/api/listening_review/project/{pid}', headers=self.auth()).get_json()['exam']['attempts']
        self.assertEqual([a['id'] for a in attempts], ['9100000000000000500', '9100000000000000501'])
        self.assertEqual([a['answers']['3']['user'] for a in attempts], ['hill', 'mill'])
        self.assertEqual([len(a['marks']) for a in attempts], [5, 1])

    def test_reimport_as_new_project_leaves_the_old_one(self):
        self.import_single()
        r = self.preview_ok(SINGLE)
        response = self.do_import(r['key'], [{'index': 0, 'mode': 'new', 'title': 'Again'}])
        self.assertEqual(len(response.get_json()['created']), 1)
        self.wait_jobs()
        self.assertEqual(sorted(p['title'] for p in self.projects()), ['Part 1 · Again', 'Part 1 · Riverside Bike Hire'])

    def test_reimport_while_first_import_is_still_running(self):
        r = self.preview_ok(SINGLE)
        self._patch(self.lr, '_start_thread', lambda *a, **k: None)
        pid = self.do_import(r['key'], [{'index': 0, 'mode': 'new'}]).get_json()['created'][0]['id']
        r2 = self.preview_ok(self.another_attempt('9100000000000000502', 'mill'))
        self.do_import(r2['key'], [{'index': 0, 'mode': 'update'}])
        exam = self.read_json(self.lr_path(pid, 'exam.json'))
        self.assertEqual(len(exam['attempts']), 2)


if __name__ == '__main__':
    unittest.main()
