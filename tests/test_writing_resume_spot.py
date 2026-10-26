"""写作「接着练」：进实战页要停在这一篇第一句还没分数的句子上，而不是开头。

把页面里的定位逻辑摘出来，用 node 配假数据跑；没装 node 的环境跳过行为测试，只跑页面接线检查。
"""

import json
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, 'templates', 'writing_practice.html')


def _page():
    with open(PAGE, encoding='utf-8') as f:
        return f.read()


def _method(html, head):
    """从 Tpl 对象里摘出一个多行方法（到它自己的 `  },` 为止）。"""
    start = html.index(head)
    end = html.index('\n  },\n', start) + len('\n  },\n')
    return html[start:end]


def _tpl_js():
    html = _page()
    start = html.index('var Tpl = {')
    tpl = html[start:]
    return ''.join([
        _method(tpl, '  savedScore(stepId, idx) {'),
        _method(tpl, '  cellScore(stepId, idx) {'),
        _method(tpl, '  gotoFirstUnscored() {'),
        '  cellKey(stepId, idx) { return `${stepId}#${idx}`; },\n',
    ])


def _enter_practice_js():
    html = _page()
    start = html.index('async function enterPractice(catIdx, subIdx) {')
    end = html.index('async function quickPractice(')
    return html[start:end]


RUNNER = r"""
const Tpl = {
  s: {},
%(tpl)s
};

const API = { get: async (url) => API.routes[url] };
const Nav = { enter() {} };
const state = {};
async function ensureBigChain() {}
function rememberBigSpot() {}
function renderPractice() {}
function switchView() {}
function alert() {}
%(enter)s

// 模板实战：两段，A 段 2 句、B 段 3 句
function tplCase(saved, results) {
  const sections = {};
  Object.entries(saved).forEach(([stepId, idxs]) => {
    sections[stepId] = { sentences: Object.fromEntries(idxs.map(i => [String(i), { best_score: '6.5' }])) };
  });
  Tpl.s.progress = { T: { Q: { sections } } };
  Tpl.s.prac = {
    typeId: 'T', questionId: 'Q', stepIdx: 0, activeIdx: 0, results: results || {},
    steps: [{ id: 'A', sentences: [{}, {}] }, { id: 'B', sentences: [{}, {}, {}] }],
  };
  Tpl.gotoFirstUnscored();
  return [Tpl.s.prac.stepIdx, Tpl.s.prac.activeIdx];
}

// 思维链实战：三道例题，每道 2 句；done 是已经有记录的 [例题, 句子]
async function bigCase(done) {
  const examples = [0, 1, 2].map(ei => ({
    example_idx: ei,
    sentences: [0, 1].map(si => done.some(([e, s]) => e === ei && s === si) ? [{ score: '6' }] : []),
  }));
  API.routes = {
    '/api/writing/subcategory/0/0': { examples: [0, 1, 2].map(() => ({ sentences: [{}, {}] })) },
    '/api/writing/practice_progress': { '0_0': { examples } },
  };
  await enterPractice(0, 0);
  return state.currentExIdx;
}

(async () => {
  const out = {
    tpl_fresh: tplCase({}),
    tpl_mid_second_step: tplCase({ A: [0, 1], B: [0] }),
    tpl_gap_in_first_step: tplCase({ A: [1], B: [0, 1, 2] }),
    tpl_all_done: tplCase({ A: [0, 1], B: [0, 1, 2] }),
    tpl_this_session_result: tplCase({}, { 'A#0': { score: '7' } }),
    big_fresh: await bigCase([]),
    big_first_example_done: await bigCase([[0, 0], [0, 1], [1, 0]]),
    big_all_done: await bigCase([[0, 0], [0, 1], [1, 0], [1, 1], [2, 0], [2, 1]]),
  };
  process.stdout.write(JSON.stringify(out));
})();
"""


@unittest.skipUnless(shutil.which('node'), 'node 不可用')
class ResumeAtFirstUnscoredTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        js = RUNNER % {'tpl': _tpl_js(), 'enter': _enter_practice_js()}
        proc = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            raise AssertionError('node 跑失败：' + proc.stderr)
        cls.r = json.loads(proc.stdout)

    def test_template_starts_at_first_sentence_when_nothing_scored(self):
        self.assertEqual(self.r['tpl_fresh'], [0, 0])

    def test_template_jumps_into_later_paragraph(self):
        self.assertEqual(self.r['tpl_mid_second_step'], [1, 1])

    def test_template_goes_back_to_an_earlier_gap(self):
        # 找的是第一句没分数的，不是练到的最后一句的下一句
        self.assertEqual(self.r['tpl_gap_in_first_step'], [0, 0])

    def test_template_all_scored_stays_at_start(self):
        self.assertEqual(self.r['tpl_all_done'], [0, 0])

    def test_template_counts_this_session_results(self):
        self.assertEqual(self.r['tpl_this_session_result'], [0, 1])

    def test_chain_opens_first_example_with_unscored_sentence(self):
        self.assertEqual(self.r['big_fresh'], 0)
        self.assertEqual(self.r['big_first_example_done'], 1)
        self.assertEqual(self.r['big_all_done'], 0)


class ResumeWiringTest(unittest.TestCase):
    """大小作文模板实战建好练习状态后、画页面之前，都要先定位到第一句没分数的。"""

    @classmethod
    def setUpClass(cls):
        html = _page()
        cls.tpl = html[html.index('var Tpl = {'):]

    def test_both_template_practices_locate_before_render(self):
        for head in ('  startBigPractice() {', '  buildSmallPractice() {'):
            with self.subTest(head=head):
                body = _method(self.tpl, head)
                self.assertIn('this.gotoFirstUnscored();', body)
                self.assertLess(body.index('this.gotoFirstUnscored();'), body.index('this.renderPractice();'))


if __name__ == '__main__':
    unittest.main()
