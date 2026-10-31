"""流式批改：半截 JSON 的解析、两家 SSE 的读取与重试、?stream=1 接口推出的事件。

模型调用全部打桩，不发任何网络请求，用的也是假 key。
"""

import itertools
import json
import os
import sys
import unittest
from unittest import mock

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core  # noqa: E402
from test_auth_guard import AppTestBase  # noqa: E402

FULL = json.dumps({
    'score': '6.0',
    'feedback_summary': '有一处 "主谓一致" 错误',
    'grammar_corrections': [
        {'original': 'allow', 'corrected': 'allows', 'type': '主谓一致', 'reason': '主语 it 是单数'},
        {'original': 'travels', 'corrected': 'travel', 'type': '单复数', 'reason': '出行不可数'},
    ],
    'vocabulary_upgrade': [{'original': 'reduce', 'replacement': 'cut down on', 'reason': '更地道'}],
    'native_standard': '',
    'native_optimized': 'It allows them to cut down on travel.',
}, ensure_ascii=False, indent=2)


def chunks(text, size=17):
    return [text[i:i + size] for i in range(0, len(text), size)]


def fake_stream(pieces):
    """替身 stream_llm：和真的一样是生成器（_grade_stream 用完会 close 它）。"""
    def gen(cfg, messages):
        yield from pieces
    return gen


class PartialFeedbackTest(unittest.TestCase):
    def setUp(self):
        from routers import writing_logic
        self.partial = writing_logic._partial_feedback

    def test_fields_appear_in_order_and_only_when_complete(self):
        seen = []
        for end in range(1, len(FULL) + 1):
            p = self.partial(FULL[:end])
            if not seen or p != seen[-1]:
                seen.append(p)
        # 分数没写完（"6" 还可能是 "6.5"）之前不报
        self.assertEqual(self.partial('{\n  "score": "6'), {})
        self.assertEqual(self.partial('{\n  "score": "6.0"'), {})
        self.assertEqual(self.partial('{\n  "score": "6.0",')['score'], '6.0')
        counts = [len(p.get('grammar_corrections', [])) for p in seen]
        self.assertEqual(counts, sorted(counts))       # 改错只增不减
        self.assertEqual(counts[-1], 2)
        self.assertTrue(seen[-1]['corrections_done'])
        self.assertEqual(seen[-1]['feedback_summary'], '有一处 "主谓一致" 错误')
        self.assertNotIn('vocabulary_upgrade', seen[-1])

    def test_unclosed_correction_is_held_back(self):
        cut = FULL.index('"travels"')
        p = self.partial(FULL[:cut])
        self.assertEqual([c['original'] for c in p['grammar_corrections']], ['allow'])
        self.assertFalse(p['corrections_done'])

    def test_empty_corrections_close_immediately(self):
        p = self.partial('{"score": "7.0", "feedback_summary": "很好", "grammar_corrections": [], "voc')
        self.assertEqual(p['grammar_corrections'], [])
        self.assertTrue(p['corrections_done'])


class FakeStreamResp:
    def __init__(self, lines, status=200, fail_after=None):
        self.lines, self.status_code, self.fail_after = lines, status, fail_after

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(response=self)

    def iter_lines(self, chunk_size=None):
        for i, line in enumerate(self.lines):
            if self.fail_after is not None and i == self.fail_after:
                raise requests.exceptions.ChunkedEncodingError('cut')
            yield line


def gemini_sse(pieces, thought=None):
    lines = []
    if thought:
        lines += [b'data: ' + json.dumps({'candidates': [{'content': {'parts': [{'text': thought, 'thought': True}]}}]}).encode(), b'']
    for p in pieces:
        lines += [b'data: ' + json.dumps({'candidates': [{'content': {'parts': [{'text': p}]}}]}).encode(), b'']
    return lines


def deepseek_sse(pieces):
    lines = [b'data: ' + json.dumps({'choices': [{'delta': {'role': 'assistant', 'content': ''}}]}).encode(), b'']
    for p in pieces:
        lines += [b'data: ' + json.dumps({'choices': [{'delta': {'content': p}}]}).encode(), b'']
    return lines + [b'data: [DONE]', b'']


MESSAGES = [{'role': 'system', 'content': 'sys'}, {'role': 'user', 'content': 'q'}]


class StreamLlmTest(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-ds', 'WILDAPI_API_KEY': 'test-wild'})
        env.start()
        self.addCleanup(env.stop)
        sleep = mock.patch.object(core.time, 'sleep')
        sleep.start()
        self.addCleanup(sleep.stop)

    def test_gemini_sse_pieces_in_order_and_thoughts_skipped(self):
        with mock.patch.object(core.requests, 'post',
                               return_value=FakeStreamResp(gemini_sse(['ab', 'cd'], thought='hmm'))) as post:
            out = list(core.stream_llm({'model': 'gemini-3.8-flash', 'timeout': 40}, MESSAGES))
        self.assertEqual(out, ['ab', 'cd'])
        self.assertTrue(post.call_args.args[0].endswith(':streamGenerateContent?alt=sse'))
        self.assertTrue(post.call_args.kwargs['stream'])

    def test_deepseek_sse_stops_at_done(self):
        with mock.patch.object(core.requests, 'post', return_value=FakeStreamResp(deepseek_sse(['x', 'y']))) as post:
            out = list(core.stream_llm({'model': 'deepseek-flash'}, MESSAGES))
        self.assertEqual(out, ['x', 'y'])
        self.assertTrue(post.call_args.kwargs['json']['stream'])
        self.assertEqual(post.call_args.args[0], 'https://api.deepseek.com/chat/completions')

    def test_failure_before_first_piece_is_retried(self):
        replies = [requests.exceptions.ConnectTimeout(), FakeStreamResp(gemini_sse(['ok']))]
        with mock.patch.object(core.requests, 'post', side_effect=replies) as post:
            self.assertEqual(list(core.stream_llm({'model': 'gemini-3.8-flash'}, MESSAGES)), ['ok'])
        self.assertEqual(post.call_count, 2)

    def test_failure_after_first_piece_is_raised_not_retried(self):
        resp = FakeStreamResp(gemini_sse(['a', 'b']), fail_after=2)
        with mock.patch.object(core.requests, 'post', return_value=resp) as post:
            got = []
            with self.assertRaises(requests.exceptions.ChunkedEncodingError):
                for piece in core.stream_llm({'model': 'gemini-3.8-flash'}, MESSAGES):
                    got.append(piece)
        self.assertEqual(got, ['a'])
        self.assertEqual(post.call_count, 1)

    def test_stall_after_first_piece_times_out_even_with_heartbeats(self):
        # 每读一次时钟走 10 秒：收到 'a' 之后只有心跳，第二个心跳时已经 20 秒没有新内容
        lines = gemini_sse(['a'])[:1] + [b'', b': ping', b': ping'] + gemini_sse(['late'])
        clock = mock.patch.object(core.time, 'monotonic', side_effect=itertools.count(0, 10))
        with clock, mock.patch.object(core.requests, 'post', return_value=FakeStreamResp(lines)) as post:
            got = []
            with self.assertRaises(requests.exceptions.ReadTimeout):
                for piece in core.stream_llm({'model': 'gemini-3.8-flash', 'timeout': 40}, MESSAGES):
                    got.append(piece)
        self.assertEqual(got, ['a'])
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs['timeout'], (40, core.STREAM_STALL_SECONDS))

    def test_stall_before_first_piece_is_retried(self):
        replies = [FakeStreamResp([b': ping', b': ping', b': ping']), FakeStreamResp(gemini_sse(['ok']))]
        clock = mock.patch.object(core.time, 'monotonic', side_effect=itertools.count(0, 10))
        with clock, mock.patch.object(core.requests, 'post', side_effect=replies) as post:
            self.assertEqual(list(core.stream_llm({'model': 'gemini-3.8-flash'}, MESSAGES)), ['ok'])
        self.assertEqual(post.call_count, 2)

    def test_4xx_not_retried(self):
        with mock.patch.object(core.requests, 'post', return_value=FakeStreamResp([], status=401)) as post:
            with self.assertRaises(requests.exceptions.HTTPError):
                list(core.stream_llm({'model': 'deepseek-flash'}, MESSAGES))
        self.assertEqual(post.call_count, 1)


def parse_sse(body):
    events = []
    for block in body.split('\n\n'):
        if not block.strip():
            continue
        lines = dict(line.split(': ', 1) for line in block.split('\n'))
        events.append((lines['event'], json.loads(lines['data'])))
    return events


class GradeStreamRouteTest(AppTestBase):
    def setUp(self):
        super().setUp()
        self.writing = sys.modules['routers.writing_logic']

    def post(self, url, body, gzip=False):
        headers = self.auth()
        if gzip:
            headers['Accept-Encoding'] = 'gzip'
        return self.client.post(url, json=body, headers=headers)

    def test_stream_pushes_partials_then_normalized_result(self):
        self._patch(self.writing, 'stream_llm', fake_stream(chunks(FULL)))
        r = self.post('/api/writing/correct?stream=1',
                      {'question_text': 'Q', 'target_chinese': '中', 'user_translation': 'It allow travels.',
                       'standard_reference': 'Ref sentence.'}, gzip=True)
        self.assertEqual(r.mimetype, 'text/event-stream')
        self.assertEqual(r.headers.get('X-Accel-Buffering'), 'no')
        self.assertIsNone(r.headers.get('Content-Encoding'))   # gzip 会把流攒成一整块
        events = parse_sse(r.get_data(as_text=True))
        kinds = [e for e, _ in events]
        self.assertEqual(kinds[-1], 'done')
        self.assertGreaterEqual(kinds.count('partial'), 3)
        self.assertEqual(events[0][1], {'score': '6.0'})
        done = events[-1][1]
        self.assertEqual(len(done['grammar_corrections']), 2)
        self.assertTrue(done['native_version'].startswith('1. 标准答案：Ref sentence.\n'))

    def test_stream_failure_becomes_error_event(self):
        def broken(cfg, messages):
            yield '{"score": "6.0",'
            raise requests.exceptions.ReadTimeout()
        self._patch(self.writing, 'stream_llm', broken)
        r = self.post('/api/writing/small/correct?stream=1',
                      {'question_text': 'Q', 'target_chinese': '中', 'user_translation': 'x'})
        events = parse_sse(r.get_data(as_text=True))
        self.assertEqual(events[-1], ('error', {'error': 'AI 服务超时，请重试'}))

    def test_done_sent_as_soon_as_json_closes(self):
        # 内容发完了上游还不断开：不该再等，直接出结果并把上游关掉
        closed = []

        def lingering(cfg, messages):
            try:
                yield from chunks(FULL)
                raise AssertionError('JSON 已经闭合，不该再读上游')
            finally:
                closed.append(True)
        self._patch(self.writing, 'stream_llm', lingering)
        r = self.post('/api/writing/small/correct?stream=1',
                      {'question_text': 'Q', 'target_chinese': '中', 'user_translation': 'It allow travels.'})
        events = parse_sse(r.get_data(as_text=True))
        self.assertEqual(events[-1][0], 'done')
        self.assertEqual(events[-1][1]['score'], '6.0')
        self.assertEqual(closed, [True])

    def test_dropped_connection_mid_stream_becomes_retryable_error(self):
        def dropped(cfg, messages):
            yield '{"score": "6.0",'
            raise requests.exceptions.ConnectionError('Read timed out.')
        self._patch(self.writing, 'stream_llm', dropped)
        r = self.post('/api/writing/small/correct?stream=1',
                      {'question_text': 'Q', 'target_chinese': '中', 'user_translation': 'x'})
        events = parse_sse(r.get_data(as_text=True))
        self.assertEqual(events[-1], ('error', {'error': 'AI 服务超时，请重试'}))

    def test_template_route_streams_too(self):
        self._patch(self.writing, 'stream_llm', fake_stream([FULL]))
        r = self.post('/api/writing/template/correct?stream=1',
                      {'task': 'task2', 'user_translation': 'It allow travels.', 'reference': 'Ref.'})
        events = parse_sse(r.get_data(as_text=True))
        self.assertEqual(events[-1][0], 'done')
        self.assertTrue(events[-1][1]['native_version'].startswith('1. 标准答案：Ref.\n'))

    def test_without_stream_flag_returns_plain_json(self):
        self._patch(self.writing, 'call_llm', lambda cfg, messages: FULL)
        r = self.post('/api/writing/correct',
                      {'question_text': 'Q', 'target_chinese': '中', 'user_translation': 'It allow travels.',
                       'standard_reference': 'Ref.'})
        self.assertEqual(r.mimetype, 'application/json')
        self.assertEqual(r.get_json()['score'], '6.0')


if __name__ == '__main__':
    unittest.main()
