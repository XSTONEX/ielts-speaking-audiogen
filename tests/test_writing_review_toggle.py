"""写作实战提交即收录进复习中心，之后可以把这条记录移出、再放回。

大作文、小作文、模板写作三套记录各一组接口；数据目录在临时目录里（见 AppTestBase）。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_auth_guard import AppTestBase  # noqa: E402

KINDS = {
    'big': ('/api/writing/save_practice', '/api/writing/practice_history',
            '/api/writing/set_in_review/{}'),
    'small': ('/api/writing/small/save_practice', '/api/writing/small/practice_history',
              '/api/writing/small/set_in_review/{}'),
    'tpl': ('/api/writing/template/save_practice', '/api/writing/template/practice_history',
            '/api/writing/template/set_in_review/{}'),
}

RECORD = {'category': '人群', 'subcategory': '学前儿童', 'question': 'Q', 'chart_type': '柱状图',
          'example_name': '例题 1', 'section_name': '开头段', 'type_id': 't1', 'question_id': 'q1',
          'section_id': 's1', 'target_chinese': '目标', 'user_translation': 'answer', 'score': '6.5',
          'feedback': {'score': '6.5'}, 'save_to_review': True}


def _ids(node):
    """复习中心接口按题型 / 题目分了好几层，这里把所有记录 id 摊平"""
    if isinstance(node, dict):
        found = {node['id']} if isinstance(node.get('id'), str) else set()
        for v in node.values():
            found |= _ids(v)
        return found
    if isinstance(node, list):
        return set().union(*map(_ids, node)) if node else set()
    return set()


class ReviewToggleTest(AppTestBase):
    def review_ids(self, kind):
        resp = self.client.get(KINDS[kind][1], headers=self.auth())
        self.assertEqual(resp.status_code, 200, resp.get_json())
        return _ids(resp.get_json())

    def set_in_review(self, kind, record_id, flag, token=None):
        return self.client.post(KINDS[kind][2].format(record_id), json={'in_review': flag},
                                headers=self.auth(token) if token != '' else {})

    def test_record_can_be_taken_out_and_put_back(self):
        for kind, (save_url, _, _) in KINDS.items():
            with self.subTest(kind=kind):
                rid = self.client.post(save_url, json=RECORD, headers=self.auth()).get_json()['id']
                self.assertIn(rid, self.review_ids(kind))

                resp = self.set_in_review(kind, rid, False)
                self.assertEqual(resp.get_json(), {'success': True, 'in_review': False})
                self.assertNotIn(rid, self.review_ids(kind))

                self.set_in_review(kind, rid, True)
                self.assertIn(rid, self.review_ids(kind))

    def test_unknown_record_and_missing_login(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.assertEqual(self.set_in_review(kind, 'nope', False).status_code, 404)
                self.assertEqual(self.set_in_review(kind, 'nope', False, token='').status_code, 401)


if __name__ == '__main__':
    unittest.main()
