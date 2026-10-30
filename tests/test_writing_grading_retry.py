"""写作实战「提交批改」的前端失败重试：把页面里的 postGrading 摘出来，用 node 配一个假 fetch 跑。

不发任何网络请求；没装 node 的环境跳过行为测试，只跑页面接线检查。
"""

import json
import os
import re
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, 'templates', 'writing_practice.html')


def _page():
    with open(PAGE, encoding='utf-8') as f:
        return f.read()


def _retry_js():
    html = _page()
    start = html.index('const GRADE_RETRY_DELAYS')
    end = html.index('function alertGradingFailed')
    return html[start:end]


# 每个场景是一串假响应：{"status": 504, "body": {...}} / {"status": 524, "html": true} / {"network": true}
SCENARIOS = {
    'two_504_then_ok': [{'status': 504, 'body': {'error': 'AI 服务超时，请重试'}},
                        {'status': 504, 'body': {'error': 'AI 服务超时，请重试'}},
                        {'status': 200, 'body': {'score': '6.5'}}],
    'html_every_time': [{'status': 524, 'html': True}] * 10,
    'bad_json_then_ok': [{'status': 502, 'body': {'error': 'AI 返回格式异常'}},
                         {'status': 200, 'body': {'score': '7'}}],
    'network_then_ok': [{'network': True}, {'status': 200, 'body': {'score': '6'}}],
    'unauthorized': [{'status': 401, 'body': {'error': '未登录'}}] * 5,
    'bad_request': [{'status': 400, 'body': {'error': '翻译内容不能为空'}}] * 5,
    'rate_limited_then_ok': [{'status': 429, 'body': {'error': 'busy'}},
                             {'status': 200, 'body': {'score': '5'}}],
}

RUNNER = r"""
globalThis.DOMException = globalThis.DOMException || class extends Error {
  constructor(message, name) { super(message); this.name = name; }
};
const API = { headers() { return {}; } };
%(code)s
const realDelays = GRADE_RETRY_DELAYS.slice();
GRADE_RETRY_DELAYS.fill(1);   // 测试里不真等

const scenarios = %(scenarios)s;

function fakeFetch(script, calls) {
  return async (url, opts) => {
    const step = script[Math.min(calls.n, script.length - 1)];
    calls.n++;
    if (opts.signal && opts.signal.aborted) throw new DOMException('Aborted', 'AbortError');
    if (step.network) throw new TypeError('Failed to fetch');
    return {
      ok: step.status >= 200 && step.status < 300,
      status: step.status,
      json: async () => { if (step.html) throw new SyntaxError('Unexpected token <'); return step.body; },
    };
  };
}

(async () => {
  const out = { delays: realDelays, results: {} };
  for (const [name, script] of Object.entries(scenarios)) {
    const calls = { n: 0 };
    const retries = [];
    globalThis.fetch = fakeFetch(script, calls);
    try {
      const data = await postGrading('/api/x', { a: 1 }, { onRetry: (n, total) => retries.push([n, total]) });
      out.results[name] = { ok: true, data, calls: calls.n, retries };
    } catch (e) {
      out.results[name] = { ok: false, message: e.message, attempts: e.attempts, calls: calls.n, retries };
    }
  }

  // 等待重试期间被中止：不再发请求，抛 AbortError
  {
    const calls = { n: 0 };
    globalThis.fetch = fakeFetch([{ status: 504, body: { error: 'x' } }], calls);
    GRADE_RETRY_DELAYS.fill(200);
    const ctrl = new AbortController();
    const p = postGrading('/api/x', {}, { signal: ctrl.signal, onRetry: () => setTimeout(() => ctrl.abort(), 10) });
    let name = null;
    try { await p; } catch (e) { name = e.name; }
    await new Promise(r => setTimeout(r, 400));
    out.results.aborted_while_waiting = { error: name, calls: calls.n };
  }

  // 流式（传了 onPartial）：服务器回 SSE，事件可能被拆在任意字节处
  const enc = new TextEncoder();
  const ev = (e, d) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`;
  const bytesOf = (text, size) => {
    const all = enc.encode(text), parts = [];
    for (let i = 0; i < all.length; i += size) parts.push(all.slice(i, i + size));
    return parts;
  };
  const sse = parts => () => ({
    ok: true, status: 200,
    headers: { get: k => (k.toLowerCase() === 'content-type' ? 'text/event-stream; charset=utf-8' : null) },
    body: new ReadableStream({ start(c) { parts.forEach(p => c.enqueue(typeof p === 'string' ? enc.encode(p) : p)); c.close(); } }),
    json: async () => { throw new SyntaxError('not json'); },
  });
  const plainJson = data => () => ({
    ok: true, status: 200, headers: { get: () => 'application/json' }, body: null, json: async () => data,
  });
  const WHOLE = ev('partial', { score: '6.5' })
    + ev('partial', { score: '6.5', feedback_summary: '好的', grammar_corrections: [], corrections_done: true })
    + ev('done', { score: '6.5', feedback_summary: '好的' });
  const STREAMS = {
    split_bytes: [sse(bytesOf(WHOLE, 5))],
    error_then_ok: [sse([ev('partial', { score: '5.0' }), ev('error', { error: 'AI 服务超时，请重试' })]), sse([WHOLE])],
    cut_then_ok: [sse([ev('partial', { score: '5.0' })]), sse([WHOLE])],
    json_fallback: [plainJson({ score: '7.0' })],
    error_every_time: [sse([ev('error', { error: 'AI 服务超时，请重试' })])],
  };
  out.stream = {};
  GRADE_RETRY_DELAYS.fill(1);
  for (const [name, replies] of Object.entries(STREAMS)) {
    const calls = { n: 0, urls: [] }, partials = [], retries = [];
    globalThis.fetch = async url => { calls.urls.push(url); return replies[Math.min(calls.n++, replies.length - 1)](); };
    try {
      const data = await postGrading('/api/x', {}, { onPartial: p => partials.push(p), onRetry: (n, t) => retries.push([n, t]) });
      out.stream[name] = { ok: true, data, calls: calls.n, urls: calls.urls, partials, retries };
    } catch (e) {
      out.stream[name] = { ok: false, message: e.message, attempts: e.attempts, calls: calls.n, partials, retries };
    }
  }
  process.stdout.write(JSON.stringify(out));
})();
"""


@unittest.skipUnless(shutil.which('node'), 'node 不可用')
class PostGradingRetryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        js = RUNNER % {'code': _retry_js(), 'scenarios': json.dumps(SCENARIOS)}
        proc = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            raise AssertionError('node 跑失败：' + proc.stderr)
        cls.out = json.loads(proc.stdout)
        cls.r = cls.out['results']

    def test_backoff_is_one_two_four_seconds(self):
        self.assertEqual(self.out['delays'], [1000, 2000, 4000])

    def test_transient_failures_are_retried_until_success(self):
        r = self.r['two_504_then_ok']
        self.assertTrue(r['ok'])
        self.assertEqual(r['data'], {'score': '6.5'})
        self.assertEqual(r['calls'], 3)
        self.assertEqual(r['retries'], [[1, 3], [2, 3]])

    def test_gives_up_after_three_retries(self):
        r = self.r['html_every_time']
        self.assertFalse(r['ok'])
        self.assertEqual(r['calls'], 4)          # 第一次 + 重试 3 次
        self.assertEqual(r['attempts'], 4)
        self.assertEqual(r['message'], '服务器返回 524')

    def test_bad_ai_json_network_and_429_are_retried(self):
        for name in ('bad_json_then_ok', 'network_then_ok', 'rate_limited_then_ok'):
            with self.subTest(name=name):
                self.assertTrue(self.r[name]['ok'])
                self.assertEqual(self.r[name]['calls'], 2)

    def test_stream_reassembles_events_split_mid_character(self):
        r = self.out['stream']['split_bytes']
        self.assertTrue(r['ok'])
        self.assertEqual(r['urls'], ['/api/x?stream=1'])
        self.assertEqual(r['data'], {'score': '6.5', 'feedback_summary': '好的'})
        self.assertEqual([p.get('score') for p in r['partials']], ['6.5', '6.5'])
        self.assertEqual(r['partials'][1]['feedback_summary'], '好的')

    def test_stream_error_or_cut_retries_and_clears_preview(self):
        for name in ('error_then_ok', 'cut_then_ok'):
            with self.subTest(name=name):
                r = self.out['stream'][name]
                self.assertTrue(r['ok'])
                self.assertEqual(r['calls'], 2)
                self.assertEqual(r['retries'], [[1, 3]])
                self.assertEqual(r['partials'][:2], [{'score': '5.0'}, None])   # 重试前先清掉半截结果

    def test_stream_falls_back_to_plain_json(self):
        r = self.out['stream']['json_fallback']
        self.assertTrue(r['ok'])
        self.assertEqual(r['data'], {'score': '7.0'})

    def test_stream_gives_up_with_server_message(self):
        r = self.out['stream']['error_every_time']
        self.assertFalse(r['ok'])
        self.assertEqual(r['calls'], 4)
        self.assertEqual(r['message'], 'AI 服务超时，请重试')

    def test_client_errors_are_not_retried(self):
        for name, msg in (('unauthorized', '未登录'), ('bad_request', '翻译内容不能为空')):
            with self.subTest(name=name):
                r = self.r[name]
                self.assertFalse(r['ok'])
                self.assertEqual(r['calls'], 1)
                self.assertEqual(r['attempts'], 1)
                self.assertEqual(r['message'], msg)

    def test_abort_stops_retrying(self):
        r = self.r['aborted_while_waiting']
        self.assertEqual(r['error'], 'AbortError')
        self.assertEqual(r['calls'], 1)


class GradingWiringTest(unittest.TestCase):
    """三个实战页都走带重试和蒙版的批改，模板写作批改后锁定答案、可再试一次、可追问。"""

    @classmethod
    def setUpClass(cls):
        cls.html = _page()

    def test_all_three_practice_pages_use_retry_and_mask(self):
        for url, view in (('/api/writing/correct', 'practiceView'),
                          ('/api/writing/small/correct', 'smallPracticeView'),
                          ('/api/writing/template/correct', 'tplSmallPracticeView')):
            with self.subTest(url=url):
                self.assertIn(f"postGrading('{url}'", self.html)
                self.assertIn(f"'{view}'", self.html)
        self.assertNotIn("API.post('/api/writing/correct'", self.html)
        self.assertNotIn("API.post('/api/writing/small/correct'", self.html)
        self.assertNotIn("API.post('/api/writing/template/correct'", self.html)

    def test_leaving_the_view_abandons_grading(self):
        start = self.html.index('function switchView(view) {')
        self.assertIn('Grading.leave(view);', self.html[start:start + 200])

    def test_template_result_locks_answer_and_offers_retry_and_followup(self):
        start = self.html.index('var Tpl = {')
        tpl = self.html[start:]
        self.assertIn('id="tplAnswerLocked"', tpl)
        self.assertIn('onclick="Tpl.retrySentence()">再试一次</button>', tpl)
        self.assertIn('practiceFollowupHtml(fKey)', tpl)
        self.assertNotIn('改一遍再提交', tpl)

    def test_followups_are_stored_per_sentence_on_all_three_pages(self):
        # 三个实战页都把句子键和这次作答交给追问，记录才能按句子存、按作答分段
        for module in ('big', 'small', 'tpl'):
            with self.subTest(module=module):
                self.assertIn(f"store_key: followupStoreKey('{module}'", self.html)
        self.assertEqual(self.html.count('attempt: followupAttempt(res'), 3)
        # 批改时间是分段的依据，三处提交批改都要记
        self.assertEqual(self.html.count('_gradedAt = Date.now()'), 3)

    def test_locked_answers_are_escaped(self):
        self.assertNotIn('${res._userInput || \'\'}</div>', self.html)
        self.assertNotIn('${rec.user_translation || \'\'}</div>', self.html)


class FloatingButtonClearanceTest(unittest.TestCase):
    """页面底部留白要高过右下角那摞浮动按钮，否则最后一行（追问框的「发送」、下一句）滚到底也被压住。"""

    GAP = 12

    @classmethod
    def setUpClass(cls):
        html = _page()
        cls.css = html[html.index('<style>'):html.index('</style>')]
        cls.mobile = cls.css[cls.css.index('@media (max-width: 600px)'):]

    def num(self, pattern, text):
        m = re.search(pattern, text)
        self.assertIsNotNone(m, pattern)
        return int(m.group(1))

    def test_bottom_padding_clears_the_button_stack(self):
        fab_h = self.num(r'\.review-fab, \.ai-float-btn, \.np-fab \{[^}]*?height: (\d+)px', self.css)
        top_desktop = self.num(r'\.ai-float-btn \{[^}]*?bottom: (\d+)px', self.css) + fab_h
        top_mobile = self.num(r'\.ai-float-btn \{[^}]*?bottom: (\d+)px', self.mobile) + fab_h
        pad_desktop = self.num(r'\.main-panel-wrapper \{[^}]*?padding: 0 0 (\d+)px 0;', self.css)
        pad_tablet = self.num(r'\.main-panel-wrapper \{ width: 100%; padding: 0 16px (\d+)px 16px; \}', self.css)
        pad_mobile = self.num(r'\.main-panel-wrapper \{ padding-bottom: (\d+)px; \}', self.mobile)
        self.assertGreaterEqual(pad_desktop, top_desktop + self.GAP)
        self.assertGreaterEqual(pad_tablet, top_desktop + self.GAP)   # 601–768px 按钮还在桌面位置
        self.assertGreaterEqual(pad_mobile, top_mobile + self.GAP)


if __name__ == '__main__':
    unittest.main()
