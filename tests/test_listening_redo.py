"""听力精听：「显示答案 / 重做」——交卷判分规则、地图题和多选题的识别、交卷 / 删除记录的接口。

fixture tests/fixtures/jiufen_listening_map.json 是编造的：地图题的形状照真实的九分学长 JSON
（type "map"、有 imageUrl、每题选项 A–E 只有字母没有文字）；多选题（Choose TWO letters）还没有真实样本，
type "multiple-choice"、两个题号各带一份同样的选项是猜的。
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_auth_guard import AppTestBase  # noqa: E402
from utils import jiufen_listening  # noqa: E402
from utils.listening_grade import canon, grade, normalize_groups, text_matches  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')


def fixture_text(name):
    with open(os.path.join(FIXTURES, name), encoding='utf-8') as f:
        return f.read()


MAP = fixture_text('jiufen_listening_map.json')
SINGLE = fixture_text('jiufen_listening_single.json')


def opts(*texts):
    return [{'key': 'ABCDEFGH'[i], 'text': t} for i, t in enumerate(texts)]


class BlankMarkingTest(unittest.TestCase):
    """填空题照雅思官方的判法。"""

    def test_case_and_spaces_do_not_matter(self):
        self.assertTrue(text_matches('thursday', 'Thursday'))
        self.assertTrue(text_matches('  THE   museum ', 'the museum'))
        self.assertTrue(text_matches('Thursday', 'Thursday '))   # 九分学长的答案末尾常带空格

    def test_spelling_must_be_exact(self):
        self.assertFalse(text_matches('thurday', 'Thursday'))
        self.assertFalse(text_matches('Franch', 'French'))

    def test_singular_and_plural_must_match(self):
        self.assertFalse(text_matches('cat', 'cats'))
        self.assertFalse(text_matches('cats', 'cat'))

    def test_extra_words_do_not_match(self):
        self.assertFalse(text_matches('the bus', 'bus'))

    def test_any_listed_alternative_counts(self):
        self.assertTrue(text_matches('twelve', '12|twelve'))
        self.assertTrue(text_matches('12', '12|twelve'))

    def test_figures_or_words_both_count(self):
        self.assertTrue(text_matches('nine', '9'))
        self.assertTrue(text_matches('320', 'three hundred and twenty'))
        self.assertTrue(text_matches('twenty-one', '21'))
        self.assertTrue(text_matches('30,000', '30000'))
        self.assertTrue(text_matches('3 days', 'three days'))
        self.assertFalse(text_matches('12', '21'))
        self.assertEqual(canon('one two'), '1 2')            # 不是一个数
        self.assertEqual(canon('bread and butter'), 'bread and butter')

    def test_british_and_american_spellings_both_count(self):
        for us, uk in [('color', 'colour'), ('center', 'centre'), ('theater', 'theatre'),
                       ('organize', 'organise'), ('organization', 'organisation'), ('analyze', 'analyse'),
                       ('traveled', 'travelled'), ('neighborhood', 'neighbourhood'), ('program', 'programme'),
                       ('jewelry', 'jewellery'), ('favorite', 'favourite')]:
            self.assertTrue(text_matches(us, uk), us)
            self.assertTrue(text_matches(uk, us), uk)
        self.assertFalse(text_matches('sise', 'size'))       # size 不是 -ize 拼法

    def test_bracketed_words_are_optional(self):
        self.assertTrue(text_matches('museum', '(the) museum'))
        self.assertTrue(text_matches('the museum', '(the) museum'))
        self.assertFalse(text_matches('a museum', '(the) museum'))
        self.assertTrue(text_matches('dog', '(a) (big) dog'))

    def test_hyphen_and_space_are_different_spellings(self):
        self.assertFalse(text_matches('mobile-phone', 'mobile phone'))

    def test_empty_answer_is_not_right(self):
        self.assertFalse(text_matches('', 'x'))
        self.assertFalse(text_matches('   ', 'x'))


class NormalizeGroupsTest(unittest.TestCase):
    def test_letters_only_options_become_map_even_in_old_data(self):
        # 以前导入的地图题存成了 choice（每题 8 个空白选项）
        g = {'kind': 'choice', 'questions': [{'num': '11', 'options': opts('', '', ''), 'answer': 'C'}]}
        self.assertEqual(normalize_groups([g])[0]['kind'], 'map')
        self.assertEqual(g['kind'], 'choice')                 # 原数据不动

    def test_choose_two_letters_is_multi_with_units(self):
        g = {'kind': 'choice', 'instruction_html': 'Choose <strong>TWO</strong> letters, <strong>A–E</strong>.',
             'questions': [{'num': '21', 'options': opts('a', 'b', 'c', 'd', 'e'), 'answer': 'B'},
                           {'num': '22', 'options': opts('a', 'b', 'c', 'd', 'e'), 'answer': 'D'},
                           {'num': '23', 'options': opts('a', 'b', 'c', 'd', 'e'), 'answer': 'A'},
                           {'num': '24', 'options': opts('a', 'b', 'c', 'd', 'e'), 'answer': 'E'}]}
        n = normalize_groups([g])[0]
        self.assertEqual((n['kind'], n['pick'], n['units']), ('multi', 2, [['21', '22'], ['23', '24']]))

    def test_single_question_with_two_letter_answer_is_one_unit(self):
        g = {'kind': 'choice', 'type': 'multiple-choice',
             'questions': [{'num': '21', 'options': opts('a', 'b', 'c', 'd', 'e'), 'answer': 'B,D'}]}
        n = normalize_groups([g])[0]
        self.assertEqual((n['kind'], n['pick'], n['units']), ('multi', 2, [['21']]))

    def test_box_of_answers_is_not_multi(self):
        g = {'kind': 'choice', 'instruction_html': 'Choose FOUR answers from the box and write the correct letter, A–G.',
             'questions': [{'num': '27', 'options': opts('a', 'b'), 'answer': 'A'}]}
        self.assertEqual(normalize_groups([g])[0]['kind'], 'choice')

    def test_single_choice_stays_choice(self):
        g = {'kind': 'choice', 'instruction_html': 'Choose the correct letter, A, B or C.',
             'questions': [{'num': '16', 'options': opts('x', 'y', 'z'), 'answer': 'C'}]}
        self.assertEqual(normalize_groups([g])[0]['kind'], 'choice')

    def test_blank_answered_with_letters_from_a_box_is_match(self):
        g = {'kind': 'blank', 'options': opts('survey', 'budget', 'photos'),
             'questions': [{'num': '26', 'options': [], 'answer': 'A'}, {'num': '27', 'options': [], 'answer': 'C'}]}
        self.assertEqual(normalize_groups([g])[0]['kind'], 'match')

    def test_parser_marks_map_type_and_keeps_raw_type(self):
        groups = jiufen_listening.parse(MAP)['parts'][0]['groups']
        self.assertEqual([(g['kind'], g['type']) for g in groups],
                         [('map', 'map'), ('choice', 'multiple-choice'), ('choice', 'single-choice')])
        self.assertTrue(groups[0]['image'].endswith('greenfield-plan.png'))
        self.assertEqual([g['kind'] for g in normalize_groups(groups)], ['map', 'multi', 'choice'])


class GradeTest(unittest.TestCase):
    def setUp(self):
        self.groups = jiufen_listening.parse(MAP)['parts'][0]['groups']

    def test_map_multi_and_choice(self):
        r = grade(self.groups, {'1': 'c', '2': 'B', '4': 'D,B', '6': 'B'})
        a = r['answers']
        self.assertEqual(a['1'], {'user': 'C', 'state': 'right'})
        self.assertEqual(a['2'], {'user': 'B', 'state': 'wrong'})
        self.assertEqual(a['3'], {'user': '', 'state': 'blank'})
        # 多选不分先后：选 D、B，两题都对
        self.assertEqual((a['4']['state'], a['5']['state']), ('right', 'right'))
        self.assertEqual({a['4']['user'], a['5']['user']}, {'B', 'D'})
        self.assertEqual(a['6'], {'user': 'B', 'state': 'right'})
        self.assertEqual((r['correct'], r['total']), (4, 6))

    def test_multi_with_one_right_letter(self):
        a = grade(self.groups, {'4': 'C,B'})['answers']
        self.assertEqual(a['4'], {'user': 'B', 'state': 'right'})
        self.assertEqual(a['5'], {'user': 'C', 'state': 'wrong'})

    def test_multi_with_one_letter_and_extra_letters_ignored(self):
        a = grade(self.groups, {'5': 'D'})['answers']        # 选择记在哪个题号上都行
        self.assertEqual((a['4'], a['5']), ({'user': '', 'state': 'blank'}, {'user': 'D', 'state': 'right'}))
        a = grade(self.groups, {'4': 'E,A,B'})['answers']      # 一组两个题号最多认两个字母，第三个 B 不算
        self.assertEqual((a['4'], a['5']), ({'user': 'E', 'state': 'wrong'}, {'user': 'A', 'state': 'wrong'}))

    def test_blanks_use_text_rules(self):
        groups = jiufen_listening.parse(SINGLE)['parts'][0]['groups']
        answers = grade(groups, {'1': 'Twelve', '2': 'Passport ', '3': 'hill', '5': 'b'})['answers']
        self.assertEqual([answers[n]['state'] for n in '12345'], ['right', 'right', 'wrong', 'blank', 'right'])
        self.assertEqual(answers['1']['user'], 'Twelve')        # 记下的是你写的原样

    def test_single_question_needing_two_letters(self):
        g = [{'kind': 'choice', 'type': 'multiple-choice',
              'questions': [{'num': '21', 'options': opts('a', 'b', 'c', 'd'), 'answer': 'B|D'}]}]
        self.assertEqual(grade(g, {'21': 'D,B'})['answers']['21']['state'], 'right')
        self.assertEqual(grade(g, {'21': 'B'})['answers']['21']['state'], 'wrong')


class RedoApiTest(AppTestBase):
    def setUp(self):
        super().setUp()
        self.lr = sys.modules['routers.listening_review']
        part = jiufen_listening.parse(MAP)['parts'][0]
        self.part = part
        record = self.lr._create_jiufen_project('tester', part, 'Part 1 · Greenfield Library Tour')
        record['status'] = 'completed'
        self.pid = record['id']
        self.write_json(self.lr._user_projects_path('tester'), [record])
        self.write_json(self.lr._project_data_path(self.pid), {'segments': part['segments'], 'notes': [], 'vocab_annotations': []})

    def submit(self, answers, elapsed=95, token=None, pid=None):
        return self.client.post(f'/api/listening_review/project/{pid or self.pid}/attempts',
                                json={'answers': answers, 'elapsed_seconds': elapsed},
                                headers={'Authorization': f'Bearer {token or self.token}'})

    def detail(self):
        return self.client.get(f'/api/listening_review/project/{self.pid}', headers=self.auth()).get_json()

    def project(self):
        return self.client.get('/api/listening_review/list', headers=self.auth()).get_json()['projects'][0]

    def test_detail_returns_normalized_kinds(self):
        exam = self.detail()['exam']
        self.assertEqual([g['kind'] for g in exam['groups']], ['map', 'multi', 'choice'])
        self.assertEqual(exam['groups'][1]['units'], [['4', '5']])
        stored = self.read_json(self.lr._exam_path(self.pid))
        self.assertEqual(stored['groups'][1]['kind'], 'choice')   # 存的不改

    def test_submit_grades_and_saves_a_new_self_attempt(self):
        r = self.submit({'1': 'C', '2': 'E', '3': 'A', '4': 'B,D', '6': 'A'}, elapsed=125)
        self.assertEqual(r.status_code, 200, r.get_json())
        body = r.get_json()
        att = body['attempt']
        self.assertEqual(att['source'], 'self')
        self.assertTrue(att['id'].startswith('self-'))
        self.assertEqual((att['correct'], att['total'], att['elapsed_seconds']), (5, 6, 125))
        self.assertEqual(att['answers']['6'], {'user': 'A', 'state': 'wrong'})
        self.assertEqual(att['marks'], [])
        self.assertEqual((body['index'], body['attempt_count']), (1, 2))
        self.assertEqual(body['score'], {'correct': 5, 'total': 6})
        attempts = self.detail()['exam']['attempts']
        self.assertEqual([a.get('source') for a in attempts], [None, 'self'])
        self.assertEqual(attempts[0]['id'], '9100000000000000700')   # 导入的那次还在
        p = self.project()
        self.assertEqual((p['attempt_count'], p['score']), (2, {'correct': 5, 'total': 6}))

    def test_empty_submission_counts_every_question_as_blank(self):
        att = self.submit({}).get_json()['attempt']
        self.assertEqual((att['correct'], att['total']), (0, 6))
        self.assertEqual({a['state'] for a in att['answers'].values()}, {'blank'})

    def test_bad_requests(self):
        self.assertEqual(self.client.post(f'/api/listening_review/project/{self.pid}/attempts', json={'answers': {}}).status_code, 401)
        self.assertEqual(self.client.post(f'/api/listening_review/project/{self.pid}/attempts', json={'answers': 'x'},
                                          headers=self.auth()).status_code, 400)
        self.assertEqual(self.submit({}, pid='lr_nope').status_code, 404)
        # 没有题目的篇（自己上传的音频）不能交卷
        self.write_json(self.lr._user_projects_path('tester'), [
            {'id': self.pid, 'title': 'x', 'status': 'completed'}, {'id': 'lr_plain', 'title': 'plain', 'status': 'completed'}])
        self.assertEqual(self.submit({}, pid='lr_plain').status_code, 400)

    def test_cannot_submit_to_someone_elses_project(self):
        users = self.read_json(self.users_file)
        users['other'] = {'username': 'other', 'password': 'pw', 'display_name': 'O', 'role': 'user', 'avatar': 'avatar_admin.svg'}
        self.write_json(self.users_file, users)
        other = self.login('other', 'pw')
        self.assertEqual(self.submit({'1': 'C'}, token=other).status_code, 404)
        self.assertEqual(len(self.read_json(self.lr._exam_path(self.pid))['attempts']), 1)

    def test_elapsed_time_is_clamped(self):
        self.assertEqual(self.submit({}, elapsed=-5).get_json()['attempt']['elapsed_seconds'], None)
        self.assertEqual(self.submit({}, elapsed=10 ** 9).get_json()['attempt']['elapsed_seconds'], 6 * 3600)
        self.assertEqual(self.submit({}, elapsed='abc').get_json()['attempt']['elapsed_seconds'], None)

    def test_delete_only_self_attempts(self):
        first = self.submit({'1': 'C'}).get_json()['attempt']
        second = self.submit({'1': 'C', '2': 'E'}).get_json()['attempt']
        url = f'/api/listening_review/project/{self.pid}/attempts/'
        r = self.client.delete(url + '9100000000000000700', headers=self.auth())
        self.assertEqual(r.status_code, 400)                    # 九分学长导入的不能删
        self.assertEqual(self.client.delete(url + 'self-nope', headers=self.auth()).status_code, 404)
        r = self.client.delete(url + second['id'], headers=self.auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual([a['id'] for a in r.get_json()['attempts']], ['9100000000000000700', first['id']])
        p = self.project()
        self.assertEqual((p['attempt_count'], p['score']), (2, {'correct': first['correct'], 'total': 6}))

    def test_reimport_keeps_self_attempts(self):
        self.submit({'1': 'C'})
        part = dict(self.part, attempt=dict(self.part['attempt'], id='9100000000000000701', submitted_at='2030-01-01T09:00:00'))
        projects = self.lr._load_user_projects('tester')
        self.assertEqual(self.lr._merge_jiufen_attempt(projects[0], part), 'added')
        attempts = self.read_json(self.lr._exam_path(self.pid))['attempts']
        self.assertEqual([a.get('source') for a in attempts], [None, 'self', None])


if __name__ == '__main__':
    unittest.main()
