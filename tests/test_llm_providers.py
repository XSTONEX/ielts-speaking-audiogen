"""写作用的几条模型路由：wild/<模型>（WildAPI 的 OpenAI 兼容接口）、aihubmix/<模型>[@思考档位]、
写作默认模型和后备模型的设置、主模型失败时退回后备、思考模型首字前的等待。

requests.post 全部打桩，不发任何网络请求，用的也是假 key。
"""

import json
import os
import sys
import unittest
from unittest import mock

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core  # noqa: E402
from test_auth_guard import AppTestBase  # noqa: E402
from test_writing_stream import FULL, FakeStreamResp, chunks, deepseek_sse, gemini_sse, parse_sse  # noqa: E402

MESSAGES = [{'role': 'system', 'content': 'sys'}, {'role': 'user', 'content': 'q'}]
AHM_URL = 'https://aihubmix.com/v1/chat/completions'
WILD_CHAT_URL = 'https://api.gptsapi.net/v1/chat/completions'
HYDROGEN = 'aihubmix/gemini-4-hydrogen'
SONNET = 'wild/claude-sonnet-5-5'
ENV = {'AIHUBMIX_API_KEY': 'test-ahm', 'WILDAPI_API_KEY': 'test-wild', 'DEEPSEEK_API_KEY': 'test-ds'}


class FakeResp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(response=self)

    def json(self):
        return self._data


def chat_ok(text):
    return {'choices': [{'message': {'role': 'assistant', 'content': text}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 30,
                      'completion_tokens_details': {'reasoning_tokens': 25}}}


GEMINI_OK = {'candidates': [{'content': {'parts': [{'text': 'from wild'}]}, 'finishReason': 'STOP'}]}
QUOTA_403 = {'error': {'message': 'Your account balance is insufficient.', 'code': 'insufficient_user_quota'}}


def aihubmix_sse(pieces):
    """和实测一样：先是只有心跳的思考阶段，最后一块只带 usage、choices 为空。"""
    lines = [b': keep-alive', b'', b': keep-alive', b'']
    for p in pieces:
        lines += [b'data: ' + json.dumps({'choices': [{'index': 0, 'delta': {'content': p}}]}).encode(), b'']
    lines += [b'data: ' + json.dumps({'choices': [], 'usage': {'completion_tokens': 9}}).encode(), b'']
    return lines + [b'data: [DONE]', b'']


class HeartbeatClock:
    """假时钟：只有读到心跳行（: keep-alive）才走 step 秒，内容行不耗时，像真的思考阶段。"""

    def __init__(self, step=10):
        self.now, self.step = 0.0, step

    def __call__(self):
        return self.now

    def resp(self, lines, **kw):
        clock = self

        class Timed(FakeStreamResp):
            def iter_lines(self, chunk_size=None):
                for line in super().iter_lines(chunk_size):
                    if line.startswith(b':'):
                        clock.now += clock.step
                    yield line
        return Timed(lines, **kw)

    def patch(self):
        return mock.patch.object(core.time, 'monotonic', side_effect=self)


def thinking_then(pieces, heartbeats):
    return [b': keep-alive'] * heartbeats + aihubmix_sse(pieces)[4:]


class Base(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, ENV)
        env.start()
        self.addCleanup(env.stop)
        for name in ('AIHUBMIX_BASE_URL', 'WILDAPI_BASE_URL', 'WRITING_LLM_MODEL'):
            os.environ.pop(name, None)
        sleep = mock.patch.object(core.time, 'sleep')
        sleep.start()
        self.addCleanup(sleep.stop)

    def post(self, **kw):
        return mock.patch.object(core.requests, 'post', **kw)


class AihubmixRequestTest(Base):
    def test_request_shape(self):
        cfg = {'model': HYDROGEN + '@medium', 'temperature': 0.2, 'thinking_budget': 0,
               'response_format': 'json_object', 'timeout': 40}
        with self.post(return_value=FakeResp(chat_ok('{"score": "6.5"}'))) as post:
            self.assertEqual(core.call_llm(cfg, MESSAGES), '{"score": "6.5"}')
        self.assertEqual(post.call_args.args[0], AHM_URL)
        kw = post.call_args.kwargs
        self.assertEqual(kw['headers']['Authorization'], 'Bearer test-ahm')
        self.assertEqual(kw['timeout'], 40)
        self.assertEqual(kw['json'], {
            'model': 'gemini-4-hydrogen',          # 前缀和 @档位 都不发给上游
            'messages': MESSAGES,
            'reasoning_effort': 'medium',
            'response_format': {'type': 'json_object'},
        })                                          # temperature / thinking 不发：hydrogen 忽略或直接 400

    def test_effort_defaults(self):
        with self.post(return_value=FakeResp(chat_ok('x'))) as post:
            core.call_llm({'model': HYDROGEN}, MESSAGES)
            self.assertEqual(post.call_args.kwargs['json']['reasoning_effort'], 'low')
            core.call_llm({'model': HYDROGEN, 'reasoning_effort': 'high'}, MESSAGES)
            self.assertEqual(post.call_args.kwargs['json']['reasoning_effort'], 'high')
            core.call_llm({'model': HYDROGEN + '@medium', 'reasoning_effort': 'high'}, MESSAGES)
            self.assertEqual(post.call_args.kwargs['json']['reasoning_effort'], 'medium')

    def test_max_output_tokens_and_base_url(self):
        with mock.patch.dict(os.environ, {'AIHUBMIX_BASE_URL': 'https://proxy.test/v1/'}), \
                self.post(return_value=FakeResp(chat_ok('x'))) as post:
            core.call_llm({'model': HYDROGEN, 'max_output_tokens': 4096}, MESSAGES)
        self.assertEqual(post.call_args.args[0], 'https://proxy.test/v1/chat/completions')
        self.assertEqual(post.call_args.kwargs['json']['max_completion_tokens'], 4096)

    def test_other_models_unchanged(self):
        with self.post(return_value=FakeResp(GEMINI_OK)) as post:
            core.call_llm({'model': 'gemini-3.8-flash'}, MESSAGES)
        self.assertIn('/v1beta/models/gemini-3.8-flash:generateContent', post.call_args.args[0])


class WildChatRequestTest(Base):
    def test_request_shape(self):
        cfg = {'model': SONNET, 'temperature': 0.2, 'response_format': 'json_object', 'timeout': 40}
        with self.post(return_value=FakeStreamResp(deepseek_sse(['{"score": ', '"6.0"}']))) as post:
            self.assertEqual(core.call_llm(cfg, MESSAGES), '{"score": "6.0"}')
        self.assertEqual(post.call_args.args[0], WILD_CHAT_URL)
        kw = post.call_args.kwargs
        self.assertEqual(kw['headers']['Authorization'], 'Bearer test-wild')
        # 不发 response_format：Claude 走这条路不一定认，认不了就 400、每次都掉到后备。
        # 非流式调用也走流式：Wild 的非流式回复会把 Claude 的正文弄丢
        self.assertEqual(kw['json'], {'model': 'claude-sonnet-5-5', 'messages': MESSAGES,
                                      'temperature': 0.2, 'stream': True})
        self.assertEqual(kw['timeout'], (40, core.STREAM_STALL_SECONDS))

    def test_empty_reply_retries_then_falls_back(self):
        # Wild 回了 200 却一个字都没有（实测过的毛病）：重试一次，还是空就退回后备模型
        replies = [FakeStreamResp(deepseek_sse([])), FakeStreamResp(deepseek_sse([])), FakeResp(GEMINI_OK)]
        with self.post(side_effect=replies) as post:
            text = core.call_llm({'model': SONNET, 'fallback_model': 'gemini-3.8-flash'}, MESSAGES)
        self.assertEqual(text, 'from wild')
        self.assertEqual(post.call_count, 3)

    def test_stream_and_base_url(self):
        with mock.patch.dict(os.environ, {'WILDAPI_BASE_URL': 'https://wild.test/v1'}), \
                self.post(return_value=FakeStreamResp(deepseek_sse(['{"a"', ': 1}']))) as post:
            out = list(core.stream_llm({'model': SONNET, 'timeout': 40}, MESSAGES))
        self.assertEqual(out, ['{"a"', ': 1}'])
        self.assertEqual(post.call_args.args[0], 'https://wild.test/v1/chat/completions')
        self.assertTrue(post.call_args.kwargs['json']['stream'])
        self.assertEqual(post.call_args.kwargs['timeout'], (40, core.STREAM_STALL_SECONDS))

    def test_bare_gemini_names_still_use_native_api(self):
        with self.post(return_value=FakeResp(GEMINI_OK)) as post:
            core.call_llm({'model': 'gemini-3.8-flash'}, MESSAGES)
        self.assertEqual(post.call_args.kwargs['headers']['x-goog-api-key'], 'test-wild')
        self.assertIn('/v1beta/models/gemini-3.8-flash:generateContent', post.call_args.args[0])


class FallbackTest(Base):
    def test_quota_403_falls_back_without_retrying(self):
        replies = [FakeResp(QUOTA_403, 403), FakeResp(GEMINI_OK)]
        with self.post(side_effect=replies) as post:
            text = core.call_llm({'model': HYDROGEN, 'fallback_model': 'gemini-3.8-flash'}, MESSAGES)
        self.assertEqual(text, 'from wild')
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[0].args[0], AHM_URL)
        self.assertIn('/models/gemini-3.8-flash:generateContent', post.call_args_list[1].args[0])

    def test_timeouts_retry_then_fall_back(self):
        replies = [requests.exceptions.ReadTimeout(), requests.exceptions.ReadTimeout(), FakeResp(GEMINI_OK)]
        with self.post(side_effect=replies) as post:
            text = core.call_llm({'model': HYDROGEN, 'fallback_model': 'gemini-3.8-flash'}, MESSAGES)
        self.assertEqual(text, 'from wild')
        self.assertEqual(post.call_count, 3)

    def test_no_fallback_configured_raises(self):
        with self.post(return_value=FakeResp(QUOTA_403, 403)) as post:
            with self.assertRaises(requests.exceptions.HTTPError):
                core.call_llm({'model': HYDROGEN}, MESSAGES)
        self.assertEqual(post.call_count, 1)

    def test_fallback_failing_too_raises_its_error(self):
        replies = [FakeResp(QUOTA_403, 403), FakeResp({}, 401)]
        with self.post(side_effect=replies) as post:
            with self.assertRaises(requests.exceptions.HTTPError) as ctx:
                core.call_llm({'model': HYDROGEN, 'fallback_model': 'gemini-3.8-flash'}, MESSAGES)
        self.assertEqual(ctx.exception.response.status_code, 401)
        self.assertEqual(post.call_count, 2)        # 后备只试一轮，不会再退回去

    def test_stream_falls_back_before_first_piece(self):
        replies = [FakeStreamResp([], status=403), FakeStreamResp(gemini_sse(['a', 'b']))]
        with self.post(side_effect=replies) as post:
            out = list(core.stream_llm({'model': HYDROGEN, 'fallback_model': 'gemini-3.8-flash'}, MESSAGES))
        self.assertEqual(out, ['a', 'b'])
        self.assertTrue(post.call_args_list[1].args[0].endswith(':streamGenerateContent?alt=sse'))

    def test_stream_does_not_fall_back_after_first_piece(self):
        resp = FakeStreamResp(aihubmix_sse(['a', 'b']), fail_after=5)
        with self.post(return_value=resp) as post:
            got = []
            with self.assertRaises(requests.exceptions.ChunkedEncodingError):
                for piece in core.stream_llm({'model': HYDROGEN, 'fallback_model': 'gemini-3.8-flash'}, MESSAGES):
                    got.append(piece)
        self.assertEqual(got, ['a'])
        self.assertEqual(post.call_count, 1)        # 半截内容没法和后备的结果拼起来，交给调用方整条重来


class AihubmixStreamTest(Base):
    def test_sse_pieces_skip_heartbeats_and_usage_chunk(self):
        with self.post(return_value=FakeStreamResp(aihubmix_sse(['{"sc', 'ore": 1}']))) as post:
            out = list(core.stream_llm({'model': HYDROGEN, 'response_format': 'json_object', 'timeout': 40}, MESSAGES))
        self.assertEqual(out, ['{"sc', 'ore": 1}'])
        self.assertEqual(post.call_args.args[0], AHM_URL)
        self.assertTrue(post.call_args.kwargs['json']['stream'])
        self.assertEqual(post.call_args.kwargs['timeout'], (40, 40))

    def test_long_thinking_before_first_piece_is_not_a_stall(self):
        # 想了 30 秒才出第一个字：超过 15 秒，但没到这次的 timeout 40 秒
        clock = HeartbeatClock()
        with clock.patch(), self.post(return_value=clock.resp(thinking_then(['o', 'k'], 3))) as post:
            out = list(core.stream_llm({'model': HYDROGEN, 'timeout': 40}, MESSAGES))
        self.assertEqual(out, ['o', 'k'])
        self.assertEqual(post.call_count, 1)

    def test_thinking_past_timeout_is_retried(self):
        clock = HeartbeatClock()
        replies = [clock.resp([b': keep-alive'] * 5), clock.resp(thinking_then(['ok'], 1))]
        with clock.patch(), self.post(side_effect=replies) as post:
            self.assertEqual(list(core.stream_llm({'model': HYDROGEN, 'timeout': 40}, MESSAGES)), ['ok'])
        self.assertEqual(post.call_count, 2)

    def test_stall_after_first_piece_still_15_seconds(self):
        clock = HeartbeatClock()
        lines = thinking_then(['a'], 0)[:2] + [b': keep-alive'] * 2 + thinking_then(['late'], 0)
        with clock.patch(), self.post(return_value=clock.resp(lines)) as post:
            got = []
            with self.assertRaises(requests.exceptions.ReadTimeout):
                for piece in core.stream_llm({'model': HYDROGEN, 'fallback_model': 'gemini-3.8-flash',
                                              'timeout': 40}, MESSAGES):
                    got.append(piece)
        self.assertEqual(got, ['a'])
        self.assertEqual(post.call_count, 1)

    def test_gemini_first_piece_limit_still_15_seconds(self):
        clock = HeartbeatClock()
        replies = [clock.resp([b': ping'] * 2 + gemini_sse(['late'])), clock.resp(gemini_sse(['ok']))]
        with clock.patch(), self.post(side_effect=replies) as post:
            self.assertEqual(list(core.stream_llm({'model': 'gemini-3.8-flash', 'timeout': 40}, MESSAGES)), ['ok'])
        self.assertEqual(post.call_count, 2)

    def test_gemini_keeps_15_second_first_piece_limit(self):
        with self.post(return_value=FakeStreamResp(gemini_sse(['x']))) as post:
            list(core.stream_llm({'model': 'gemini-3.8-flash', 'timeout': 40}, MESSAGES))
        self.assertEqual(post.call_args.kwargs['timeout'], (40, core.STREAM_STALL_SECONDS))

    def test_closing_early_closes_upstream(self):
        closed = []

        class Tracked(FakeStreamResp):
            def __exit__(self, *exc):
                closed.append(True)
                return False

        with self.post(return_value=Tracked(deepseek_sse(['a', 'b', 'c']))):
            gen = core.stream_llm({'model': 'deepseek-flash'}, MESSAGES)
            self.assertEqual(next(gen), 'a')
            gen.close()
        self.assertEqual(closed, [True])


class WritingCfgTest(Base):
    def setUp(self):
        super().setUp()
        os.environ.pop('WRITING_LLM_FALLBACK', None)
        from routers import writing_logic
        self.w = writing_logic

    def test_default_model_and_fallback(self):
        cfg = self.w._writing_cfg({'temperature': 0.2, 'timeout': 40})
        self.assertEqual(cfg, {'temperature': 0.2, 'timeout': 40,
                               'model': self.w.WRITING_MODEL, 'fallback_model': self.w.WRITING_FALLBACK_MODEL})
        self.assertEqual(self.w.WRITING_MODEL, SONNET)
        self.assertEqual(self.w.WRITING_FALLBACK_MODEL, 'gemini-3.8-flash')

    def test_env_overrides(self):
        with mock.patch.dict(os.environ, {'WRITING_LLM_MODEL': HYDROGEN + '@low', 'WRITING_LLM_FALLBACK': 'deepseek-flash'}):
            cfg = self.w._writing_cfg({'model': 'stale-yaml-model'})
        self.assertEqual(cfg['model'], HYDROGEN + '@low')
        self.assertEqual(cfg['fallback_model'], 'deepseek-flash')

    def test_same_model_means_no_fallback(self):
        with mock.patch.dict(os.environ, {'WRITING_LLM_MODEL': 'gemini-3.8-flash'}):
            self.assertNotIn('fallback_model', self.w._writing_cfg({}))

    def test_writing_prompts_no_longer_name_a_model(self):
        # 模型只在 WRITING_MODEL 一处设；yaml 里再写一份就又成了「改一处漏一处」
        for name in ('writing_correct', 'writing_small_correct', 'writing_ai_chat_global', 'writing_ai_chat_practice'):
            self.assertNotIn('model', core.load_prompt(name), name)


def route_upstream(aihubmix_reply=None, wild_chat_reply=None, gemini_reply=None):
    """按 URL 分发打桩：AIHubMix、WildAPI 的 OpenAI 兼容接口、WildAPI 的 Gemini 原生接口各一份，
    顺带记下依次打到了哪。"""
    calls = []

    def post(url, **kw):
        calls.append(url)
        if url.startswith('https://aihubmix.com/'):
            return aihubmix_reply()
        if url == WILD_CHAT_URL:
            return wild_chat_reply()
        return gemini_reply()
    return post, calls


class WritingRoutesTest(AppTestBase):
    """真走 Flask 路由 + 真的 core.stream_llm / call_llm，只把最底下的 HTTP 打桩。"""

    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {**ENV, 'WRITING_LLM_MODEL': HYDROGEN + '@low'})
        env.start()
        self.addCleanup(env.stop)
        sleep = mock.patch.object(core.time, 'sleep')
        sleep.start()
        self.addCleanup(sleep.stop)
        self.body = {'question_text': 'Q', 'target_chinese': '中', 'user_translation': 'It allow travels.',
                     'standard_reference': 'Ref sentence.'}

    def grade(self, post):
        with mock.patch.object(core.requests, 'post', side_effect=post):
            r = self.client.post('/api/writing/correct?stream=1', json=self.body, headers=self.auth())
            return parse_sse(r.get_data(as_text=True))

    def default_model(self):
        """不设 WRITING_LLM_MODEL：用代码里的默认（wild/claude-sonnet-5-5）。"""
        os.environ.pop('WRITING_LLM_MODEL', None)
        os.environ.pop('WRITING_LLM_FALLBACK', None)

    def test_default_grading_streams_from_wild_chat(self):
        self.default_model()
        post, calls = route_upstream(wild_chat_reply=lambda: FakeStreamResp(deepseek_sse(chunks(FULL))))
        events = self.grade(post)
        self.assertEqual(events[-1][0], 'done')
        self.assertEqual(events[-1][1]['score'], '6.0')
        self.assertEqual(len(events[-1][1]['grammar_corrections']), 2)
        self.assertEqual(calls, [WILD_CHAT_URL])

    def test_default_grading_falls_back_to_gemini_when_wild_chat_is_down(self):
        self.default_model()
        post, calls = route_upstream(wild_chat_reply=lambda: FakeStreamResp([], status=502),
                                     gemini_reply=lambda: FakeStreamResp(gemini_sse(chunks(FULL))))
        events = self.grade(post)
        self.assertEqual(events[-1][0], 'done')
        self.assertEqual(events[-1][1]['score'], '6.0')
        self.assertEqual(calls[:2], [WILD_CHAT_URL, WILD_CHAT_URL])     # 5xx 先照常重试一次
        self.assertIn('/models/gemini-3.8-flash:streamGenerateContent', calls[2])

    def test_default_followup_chat(self):
        self.default_model()
        body = {'context': {'target_chinese': '中', 'user_translation': 'x'}, 'user_query': '为什么？'}
        post, calls = route_upstream(wild_chat_reply=lambda: FakeStreamResp(deepseek_sse(['因为', '……'])))
        with mock.patch.object(core.requests, 'post', side_effect=post):
            r = self.client.post('/api/writing/ai_chat/practice', json=body, headers=self.auth())
        self.assertEqual(r.get_json()['content'], '因为……')
        self.assertEqual(calls, [WILD_CHAT_URL])

    def test_env_switch_to_aihubmix_grading(self):
        post, calls = route_upstream(aihubmix_reply=lambda: FakeStreamResp(aihubmix_sse(chunks(FULL))))
        events = self.grade(post)
        self.assertEqual(events[-1][0], 'done')
        self.assertEqual(events[-1][1]['score'], '6.0')
        self.assertEqual(calls, [AHM_URL])

    def test_aihubmix_out_of_balance_falls_back(self):
        post, calls = route_upstream(aihubmix_reply=lambda: FakeStreamResp([], status=403),
                                     gemini_reply=lambda: FakeStreamResp(gemini_sse(chunks(FULL))))
        events = self.grade(post)
        self.assertEqual(events[-1][0], 'done')
        self.assertEqual(calls[0], AHM_URL)
        self.assertIn('/models/gemini-3.8-flash:streamGenerateContent', calls[1])

        post, calls = route_upstream(aihubmix_reply=lambda: FakeResp(QUOTA_403, 403),
                                     gemini_reply=lambda: FakeResp(GEMINI_OK))
        with mock.patch.object(core.requests, 'post', side_effect=post):
            r = self.client.post('/api/writing/ai_chat/global', json={'user_query': '你好'}, headers=self.auth())
        self.assertEqual(r.get_json()['content'], 'from wild')
        self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
