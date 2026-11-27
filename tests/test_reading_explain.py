"""精读 AI 讲解：题型判断、提示词拼装、模型输出校验（utils/reading_explain.py）。"""

import unittest

import yaml

from utils import reading_explain as rx


def _part():
    judge = [{'key': 'A', 'text': 'TRUE'}, {'key': 'B', 'text': 'FALSE'}, {'key': 'C', 'text': 'NOT GIVEN'}]
    return {
        'title': 'Tea',
        'paragraphs': [
            {'label': 'A', 'sentences': [
                {'i': 0, 'en': 'Tea was first drunk in China, where it was presented to the emperor.'},
                {'i': 1, 'en': 'Unlike many drinks, it didn’t spoil on long journeys.'}]},
            {'label': 'B', 'sentences': [
                {'i': 2, 'en': 'By 1700 the price had fallen and merchants shipped it in wooden chests.'}]},
        ],
        'groups': [
            {'kind': 'judge', 'type': 'single-choice', 'subtype': 'judgment_true_false_not_given', 'range': 'Questions 1-2',
             'instruction_html': 'Do the following statements agree', 'content_html': '', 'options': [],
             'questions': [
                 {'num': '1', 'text': 'Tea usually went bad during transport.', 'options': judge, 'answer': 'B',
                  'user_answer': 'C', 'state': 'wrong', 'evidence': [0, 1]},
                 {'num': '2', 'text': 'The emperor disliked tea.', 'options': judge, 'answer': 'C',
                  'user_answer': 'C', 'state': 'right', 'evidence': None}]},
            {'kind': 'blank', 'type': 'fill-in-the-blank', 'subtype': '', 'range': 'Question 3',
             'instruction_html': 'Complete the sentence. ONE WORD ONLY',
             'content_html': '<p>Tea was transported in wooden <span class="ir-blank" data-q="3">3</span>.</p>', 'options': [],
             'questions': [{'num': '3', 'text': 'Tea was transported in wooden ____.', 'options': [], 'answer': 'chests',
                            'user_answer': '', 'state': 'blank', 'evidence': [2, 2]}]},
        ],
    }


def _q(**over):
    base = {'num': '1', 'marks': [], 'evidence': [1], 'verdict': 'F1', 'steps': ['定位：a', '证据：b', '结论：c']}
    base.update(over)
    return base


class ReadingExplainTest(unittest.TestCase):
    def test_find_span_prefers_whole_words_and_ignores_quote_style(self):
        assert rx.find_span('He presented his first paper, on the human eye', 'on') == (30, 32)
        assert rx.find_span('it didn’t spoil on long journeys', "didn't spoil") == (3, 15)
        assert rx.find_span('Tea was first drunk', 'coffee') is None

    def test_group_type(self):
        part = _part()
        assert [rx.group_type(g) for g in part['groups']] == ['judge', 'blank']
        two = {'kind': 'choice', 'type': 'multiple-choice', 'instruction_html': 'Choose <b>TWO</b> letters, A-E.'}
        assert rx.group_type(two) == 'choose_two'
        assert rx.group_type({'kind': 'choice', 'type': 'map', 'instruction_html': ''}) == 'para_match'
        assert rx.group_type({'kind': 'choice', 'type': 'matching', 'subtype': 'reading_heading'}) == 'heading'
        assert rx.group_type({'kind': 'choice', 'type': 'matching', 'subtype': 'reading_person_match'}) == 'name_match'

    def test_group_messages_carry_passage_answers_and_the_method_for_this_type(self):
        cfg = yaml.safe_load(open('prompts/intensive_explain.yaml', encoding='utf-8'))
        user = rx.group_messages(cfg, _part(), 0)[1]['content']
        assert '[1] Unlike many drinks' in user and '¶ B' in user
        assert '本组题型：判断题' in user and '本组题型：填空题' not in user
        assert '标准答案：B（FALSE）' in user and '学生：C（NOT GIVEN） ✗' in user
        blank = rx.group_messages(cfg, _part(), 1)[1]['content']
        assert '__(3)__' in blank and '学生：没作答' in blank

    def test_validate_keeps_good_marks_with_offsets_and_compares_with_jiufen(self):
        data = {'questions': [_q(marks=[
            {'in': 'stem', 'text': 'went bad', 'role': '题眼', 'p': "didn't spoil", 's': 1, 'rel': '反向'},
            {'in': 'stem', 'text': 'during transport', 'role': '定位词', 'p': 'on long journeys', 's': 1, 'rel': '同替'}])]}
        e = rx.validate_group(_part(), 0, data)['questions']['1']
        assert e['issues'] == [] and e['pairs'] == 2
        assert e['marks'][0]['ps'] < e['marks'][0]['pe'] and e['marks'][0]['s'] == 1
        assert e['jiufen'] == {'range': [0, 1], 'agree': True, 'width': 2}
        assert e['slip'] is None   # 模型没写；答错的题才会保留 slip

    def test_validate_flags_invented_quotes_wrong_verdict_and_missing_questions(self):
        data = {'questions': [_q(verdict='T', marks=[
            {'in': 'stem', 'text': 'went sour', 'role': '题眼', 'p': 'spoil', 's': 1},
            {'in': 'stem', 'text': 'Tea', 'role': '定位词', 'p': 'rotted quickly', 's': 1}])]}
        out = rx.validate_group(_part(), 0, data)['questions']
        issues = out['1']['issues']
        assert any(i.startswith('题目里找不到引用') for i in issues)
        assert any(i.startswith('原文里找不到引用') for i in issues)
        assert any(i.startswith('判断结论和答案不符') for i in issues)
        assert out['2']['missing'] and rx.hard_issues(out['2']['issues'])
        assert len(rx.hard_issues(issues)) == 3

    def test_validate_fixes_a_wrong_sentence_number_and_accepts_ng_without_eye_match(self):
        data = {'questions': [
            _q(marks=[{'in': 'stem', 'text': 'went bad', 'role': '题眼', 'p': "didn't spoil", 's': 0},
                      {'in': 'stem', 'text': 'transport', 'role': '定位词', 'p': 'journeys', 's': 1}]),
            _q(num='2', verdict='NG', evidence=[0], marks=[
                {'in': 'stem', 'text': 'disliked', 'role': '题眼', 'p': None, 's': None, 'rel': '无对应'},
                {'in': 'stem', 'text': 'emperor', 'role': '定位词', 'p': 'emperor', 's': 0}])]}
        out = rx.validate_group(_part(), 0, data)['questions']
        assert out['1']['marks'][0]['s'] == 1 and any(i.startswith('句号报错了') for i in out['1']['issues'])
        assert not rx.hard_issues(out['1']['issues'])
        assert out['2']['issues'] == [] and out['2']['jiufen'] is None

    def test_blank_answer_must_be_in_the_evidence_sentence(self):
        marks = [{'in': 'stem', 'text': 'transported', 'role': '定位词', 'p': 'shipped', 's': 2},
                 {'in': 'stem', 'text': 'wooden', 'role': '题眼', 'p': 'wooden', 's': 2}]
        good = rx.validate_group(_part(), 1, {'questions': [_q(num='3', verdict=None, evidence=[2], marks=marks, answer_text='chests')]})
        assert good['questions']['3']['issues'] == [] and good['questions']['3']['answer_text'] == 'chests'
        bad = rx.validate_group(_part(), 1, {'questions': [_q(num='3', verdict=None, evidence=[0], marks=marks)]})
        assert any(i.startswith('答案不在证据句里') for i in bad['questions']['3']['issues'])

    def test_parse_reply_strips_fences_and_chatter(self):
        assert rx.parse_reply('```json\n{"questions": []}\n```') == {'questions': []}
        assert rx.parse_reply('好的：{"questions": []} 以上') == {'questions': []}


    # ---------- generate：一篇从头到尾 ----------

    GOOD = {
        0: {'questions': [
            {'num': '1', 'evidence': [1], 'verdict': 'F1', 'marks': [
                {'in': 'stem', 'text': 'went bad', 'role': '题眼', 'p': "didn't spoil", 's': 1},
                {'in': 'stem', 'text': 'transport', 'role': '定位词', 'p': 'journeys', 's': 1}]},
            {'num': '2', 'evidence': [0], 'verdict': 'NG', 'marks': [
                {'in': 'stem', 'text': 'disliked', 'role': '题眼', 'p': None, 's': None},
                {'in': 'stem', 'text': 'emperor', 'role': '定位词', 'p': 'emperor', 's': 0}]}]},
        1: {'questions': [
            {'num': '3', 'evidence': [2], 'answer_text': 'chests', 'marks': [
                {'in': 'stem', 'text': 'transported', 'role': '定位词', 'p': 'shipped', 's': 2},
                {'in': 'stem', 'text': 'wooden', 'role': '题眼', 'p': 'wooden', 's': 2}]}]},
    }

    def _llm(self, replies):
        """假模型：按提示词里的题组（判断 / 填空 / 全篇）依次吐 replies 里排好的回复。"""
        import json as _json
        calls = []

        def llm(cfg, messages):
            user = messages[1]['content']
            key = 'overview' if '# 各题证据句' in user else (0 if '本组题型：判断题' in user else 1)
            calls.append(key)
            reply = replies[key].pop(0) if isinstance(replies[key], list) else replies[key]
            if isinstance(reply, Exception):
                raise reply
            return reply if isinstance(reply, str) else _json.dumps(reply, ensure_ascii=False)
        return llm, calls

    def test_generate_explains_every_group_then_the_overview(self):
        cfg = yaml.safe_load(open('prompts/intensive_explain.yaml', encoding='utf-8'))
        llm, calls = self._llm({0: self.GOOD[0], 1: self.GOOD[1],
                                'overview': {'paragraphs': [{'label': 'A', 'gist': '茶的起源'}],
                                             'vocab': [{'word': 'spoil', 'meaning': 'v. 变质', 'tier': '必背', 's': 1}]}})
        seen = []
        state = rx.generate(_part(), cfg, llm, on_update=lambda s: seen.append((s['status'], s['done'])))
        assert state['status'] == 'done' and state['errors'] == []
        assert sorted(state['groups']) == [0, 1] and state['groups'][1]['questions']['3']['answer_text'] == 'chests'
        assert state['overview']['vocab'][0]['word'] == 'spoil'
        assert sorted(map(str, calls)) == ['0', '1', 'overview'] and calls[-1] == 'overview'
        assert seen[0] == ('running', 0) and seen[-1] == ('done', 3)

    def test_generate_retries_a_group_with_invented_quotes_and_keeps_the_better_reply(self):
        cfg = yaml.safe_load(open('prompts/intensive_explain.yaml', encoding='utf-8'))
        bad = {'questions': [dict(self.GOOD[1]['questions'][0], marks=[
            {'in': 'stem', 'text': 'wooden', 'role': '题眼', 'p': 'made of oak', 's': 2},
            {'in': 'stem', 'text': 'transported', 'role': '定位词', 'p': 'shipped', 's': 2}])]}
        llm, calls = self._llm({0: self.GOOD[0], 1: [bad, self.GOOD[1]], 'overview': {}})
        state = rx.generate(_part(), cfg, llm)
        assert calls.count(1) == 2 and state['status'] == 'done'
        assert state['groups'][1]['questions']['3']['issues'] == []

    def test_generate_reports_a_group_it_could_not_explain(self):
        cfg = yaml.safe_load(open('prompts/intensive_explain.yaml', encoding='utf-8'))
        llm, calls = self._llm({0: self.GOOD[0], 1: [RuntimeError('上游 504'), '这不是 JSON'], 'overview': {}})
        state = rx.generate(_part(), cfg, llm)
        assert state['status'] == 'partial' and list(state['groups']) == [0]
        assert len(state['errors']) == 1 and '第 2 组' in state['errors'][0]
        llm, calls = self._llm({0: [RuntimeError('x')] * 2, 1: [RuntimeError('x')] * 2, 'overview': {}})
        state = rx.generate(_part(), cfg, llm)
        assert state['status'] == 'error' and 'overview' not in calls


if __name__ == '__main__':
    unittest.main()
