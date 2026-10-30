"""批改结果归一化：不管模型返回字符串还是数组，前端拿到的结构都一致。纯函数测试，不发任何网络请求。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routers.writing_logic import _normalize_feedback  # noqa: E402


class NormalizeFeedbackTest(unittest.TestCase):
    def test_vocab_string_on_one_line_becomes_list(self):
        r = _normalize_feedback({'vocabulary_upgrade':
            '1. [build] -> [fostering] (促进/营造) 2. [quiet environment] -> [tranquil atmosphere] (宁静)'})
        self.assertEqual(r['vocabulary_upgrade'], [
            {'original': 'build', 'replacement': 'fostering', 'reason': '促进/营造'},
            {'original': 'quiet environment', 'replacement': 'tranquil atmosphere', 'reason': '宁静'},
        ])

    def test_vocab_list_keys_are_unified(self):
        r = _normalize_feedback({'vocabulary_upgrade': [{'original': 'a', 'upgrade': 'b', 'explanation': 'c'}]})
        self.assertEqual(r['vocabulary_upgrade'], [{'original': 'a', 'replacement': 'b', 'reason': 'c'}])

    def test_native_fields_are_composed_with_blank_line(self):
        r = _normalize_feedback({'native_standard': 'A.', 'native_optimized': 'B.'})
        self.assertEqual(r['native_version'], '1. 标准答案：A.\n\n2. 你的结构优化版：B.')
        self.assertNotIn('native_standard', r)

    def test_reference_fills_standard_when_model_leaves_it_empty(self):
        r = _normalize_feedback({'native_standard': '', 'native_optimized': 'B.'}, ' Ref. ')
        self.assertEqual(r['native_version'], '1. 标准答案：Ref.\n\n2. 你的结构优化版：B.')
        self.assertNotIn('native_standard', r)

    def test_reference_wins_over_model_copy(self):
        r = _normalize_feedback({'native_standard': 'Ref (miscopied).', 'native_optimized': 'B.'}, 'Ref.')
        self.assertTrue(r['native_version'].startswith('1. 标准答案：Ref.\n'))

    def test_no_reference_keeps_model_sentence(self):
        r = _normalize_feedback({'native_standard': 'Own.', 'native_optimized': 'B.'}, '')
        self.assertTrue(r['native_version'].startswith('1. 标准答案：Own.\n'))

    def test_legacy_single_line_native_gets_line_breaks(self):
        r = _normalize_feedback({'native_version': '1. 标准答案： A. 2. 你的结构优化版： B.'})
        self.assertEqual(r['native_version'], '1. 标准答案： A.\n\n2. 你的结构优化版： B.')

    def test_grammar_items_keep_type_and_drop_no_ops(self):
        r = _normalize_feedback({'grammar_corrections': [
            {'original': ' sepcial ', 'corrected': 'special', 'type': '拼写', 'reason': None},
            {'original': 'rules', 'corrected': 'rules', 'type': '用词', 'reason': '没改'},
            {'original': 'and strict', 'corrected': '', 'type': '多余'},
            {'original': '', 'corrected': ''},
        ]})
        self.assertEqual(r['grammar_corrections'], [
            {'original': 'sepcial', 'corrected': 'special', 'type': '拼写', 'reason': ''},
            {'original': 'and strict', 'corrected': '', 'type': '多余', 'reason': ''},
        ])

    def test_legacy_grammar_string_is_left_alone(self):
        self.assertEqual(_normalize_feedback({'grammar_corrections': 'a -> b'})['grammar_corrections'], 'a -> b')

    def test_vocab_original_that_was_a_mistake_uses_the_corrected_text(self):
        r = _normalize_feedback({
            'grammar_corrections': [{'original': 'speechs', 'corrected': 'speeches', 'type': '拼写'}],
            'vocabulary_upgrade': [{'original': 'Speechs', 'replacement': 'lectures', 'reason': '学术讲座'},
                                   {'original': 'take part in', 'replacement': 'participate in', 'reason': ''}],
        })
        self.assertEqual([v['original'] for v in r['vocabulary_upgrade']], ['speeches', 'take part in'])

    def test_empty_and_non_dict_are_safe(self):
        self.assertEqual(_normalize_feedback({}), {})
        self.assertEqual(_normalize_feedback({'vocabulary_upgrade': '', 'native_version': ''})['vocabulary_upgrade'], [])
        self.assertEqual(_normalize_feedback([1]), [1])


if __name__ == '__main__':
    unittest.main()
