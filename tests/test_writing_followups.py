"""写作实战「追问 AI」的追问记录：按句子存、取、删。

数据目录都在临时目录里（见 AppTestBase）；模型调用换成桩，不发任何网络请求。
"""

import os
import sys
import unittest

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_auth_guard import AppTestBase  # noqa: E402

KEY = 'big|人群|学前儿童|一方面，有些人认为学龄前的孩子应该参加有组织的活动。'
CONTEXT = {'target_chinese': '目标', 'user_translation': 'answer', 'ai_feedback_summary': '总结',
           'grammar_corrections': '[]'}


class FollowupTest(AppTestBase):
    def setUp(self):
        super().setUp()
        self.writing = sys.modules['routers.writing_logic']
        self.llm_calls = []

        def fake_llm(messages, cfg):
            self.llm_calls.append(messages)
            return f'回答：{messages[-1]["content"]}'
        self._patch(self.writing, '_call_ai_chat', fake_llm)

    def ask(self, question, key=KEY, attempt=None, token=None):
        body = {'context': CONTEXT, 'user_query': question}
        if key is not None:
            body['followup_key'] = key
        if attempt is not None:
            body['attempt'] = attempt
        return self.client.post('/api/writing/ai_chat/practice', json=body, headers=self.auth(token))

    def items(self, key=KEY, token=None):
        resp = self.client.get('/api/writing/followups', query_string={'key': key}, headers=self.auth(token))
        self.assertEqual(resp.status_code, 200, resp.get_json())
        return resp.get_json()['items']

    def test_answers_are_saved_in_order_with_their_attempt(self):
        attempt1 = {'answer': 'Preschool children should join organized activity.', 'score': 6, 'graded_at': 1000}
        attempt2 = {'answer': 'Children of preschool age should take part.', 'score': '6.5', 'graded_at': 2000}
        r1 = self.ask('activity 为什么要用复数？', attempt=attempt1).get_json()
        self.ask('organised 和 organized 哪个更好？', attempt=attempt2)

        self.assertEqual(r1['content'], '回答：activity 为什么要用复数？')
        self.assertEqual(r1['item']['answer'], r1['content'])
        items = self.items()
        self.assertEqual([it['question'] for it in items],
                         ['activity 为什么要用复数？', 'organised 和 organized 哪个更好？'])
        self.assertEqual(items[0]['attempt'], {'answer': attempt1['answer'], 'score': '6', 'graded_at': 1000})
        self.assertEqual(items[1]['attempt']['score'], '6.5')
        self.assertEqual(items[0]['id'], r1['item']['id'])

    def test_each_question_is_still_a_single_call(self):
        self.ask('第一问')
        self.ask('第二问')
        # 第二次调用只带 system + 这一问，不带上一轮的问答
        self.assertEqual([m['role'] for m in self.llm_calls[1]], ['system', 'user'])
        self.assertEqual(self.llm_calls[1][-1]['content'], '第二问')

    def test_without_key_nothing_is_saved(self):
        data = self.ask('随便问问', key=None).get_json()
        self.assertEqual(data['content'], '回答：随便问问')
        self.assertIsNone(data['item'])
        self.assertFalse(os.path.exists(os.path.join(self.core.WRITING_DATA_DIR, 'tester_followups.json')))

    def test_failed_call_is_not_saved(self):
        def timeout(messages, cfg):
            raise requests.exceptions.Timeout()
        self._patch(self.writing, '_call_ai_chat', timeout)
        resp = self.ask('会超时的问题')
        self.assertEqual(resp.status_code, 504)
        self.assertEqual(self.items(), [])

    def test_keys_are_separate(self):
        self.ask('问 A', key='big|a')
        self.ask('问 B', key='big|b')
        self.assertEqual([it['question'] for it in self.items('big|a')], ['问 A'])
        self.assertEqual([it['question'] for it in self.items('big|b')], ['问 B'])

    def test_delete_removes_only_that_item(self):
        first = self.ask('留下').get_json()['item']
        second = self.ask('删掉').get_json()['item']
        resp = self.client.delete(f'/api/writing/followups/{second["id"]}', query_string={'key': KEY},
                                  headers=self.auth())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([it['id'] for it in self.items()], [first['id']])

        self.client.delete(f'/api/writing/followups/{first["id"]}', query_string={'key': KEY}, headers=self.auth())
        self.assertEqual(self.items(), [])

    def test_only_the_latest_items_are_kept(self):
        self._patch(self.writing, 'FOLLOWUP_MAX_PER_KEY', 3)
        for i in range(5):
            self.ask(f'问题 {i}')
        self.assertEqual([it['question'] for it in self.items()], ['问题 2', '问题 3', '问题 4'])

    def test_bad_keys_are_rejected(self):
        for key in ['', '   ', 'x' * 301]:
            resp = self.client.get('/api/writing/followups', query_string={'key': key}, headers=self.auth())
            self.assertEqual(resp.status_code, 400, key)
        # 追问本身照常回答，只是不记
        data = self.ask('键太长', key='x' * 301).get_json()
        self.assertIsNone(data['item'])

    def test_records_belong_to_each_user(self):
        self.write_json(self.users_file, {
            'tester': {'username': 'tester', 'password': 'secret', 'display_name': 'Test User',
                       'role': 'admin', 'avatar': 'avatar_admin.svg'},
            'other': {'username': 'other', 'password': 'secret2', 'display_name': 'Other',
                      'role': 'user', 'avatar': 'avatar_admin.svg'},
        })
        other = self.login('other', 'secret2')
        self.ask('我的问题')
        self.assertEqual(self.items(token=other), [])
        self.assertEqual(len(self.items()), 1)

    def test_requires_login(self):
        resp = self.client.get('/api/writing/followups', query_string={'key': KEY})
        self.assertEqual(resp.status_code, 401)
        resp = self.client.delete('/api/writing/followups/x', query_string={'key': KEY})
        self.assertEqual(resp.status_code, 401)


if __name__ == '__main__':
    unittest.main()
