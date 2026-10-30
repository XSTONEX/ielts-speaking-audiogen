"""写作出站模型的路由：deepseek-* 走 DeepSeek 官方 API，其余走 WildAPI 的 Gemini。

requests.post 全部打桩，不发任何网络请求，用的也是假 key。
"""

import os
import unittest
from unittest import mock

import requests

import core


class FakeResp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(response=self)

    def json(self):
        return self._data


DEEPSEEK_OK = {'choices': [{'message': {'content': '{"score": "6.5"}'}, 'finish_reason': 'stop'}]}
GEMINI_OK = {'candidates': [{'content': {'parts': [{'text': 'hi'}]}, 'finishReason': 'STOP'}]}
MESSAGES = [{'role': 'system', 'content': 'sys'}, {'role': 'user', 'content': 'q'}]


class LlmRoutingTest(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-ds', 'WILDAPI_API_KEY': 'test-wild'})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop('DEEPSEEK_BASE_URL', None)
        os.environ.pop('WRITING_LLM_MODEL', None)
        sleep = mock.patch.object(core.time, 'sleep')
        sleep.start()
        self.addCleanup(sleep.stop)

    def test_deepseek_request_shape(self):
        with mock.patch.object(core.requests, 'post', return_value=FakeResp(DEEPSEEK_OK)) as post:
            text = core.call_llm({'model': 'deepseek-flash', 'temperature': 0.2,
                                  'response_format': 'json_object', 'timeout': 40}, MESSAGES)
        self.assertEqual(text, '{"score": "6.5"}')
        url = post.call_args.args[0]
        kw = post.call_args.kwargs
        self.assertEqual(url, 'https://api.deepseek.com/chat/completions')
        self.assertEqual(kw['headers']['Authorization'], 'Bearer test-ds')
        self.assertEqual(kw['json']['model'], 'deepseek-flash')
        self.assertEqual(kw['json']['messages'], MESSAGES)
        self.assertEqual(kw['json']['thinking'], {'type': 'disabled'})
        self.assertEqual(kw['json']['response_format'], {'type': 'json_object'})
        self.assertEqual(kw['timeout'], 40)

    def test_gemini_still_default(self):
        with mock.patch.object(core.requests, 'post', return_value=FakeResp(GEMINI_OK)) as post:
            self.assertEqual(core.call_llm({'model': 'gemini-3.8-flash'}, MESSAGES), 'hi')
        self.assertIn('/v1beta/models/gemini-3.8-flash:generateContent', post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs['headers']['x-goog-api-key'], 'test-wild')

    def test_deepseek_retries_timeout_once(self):
        replies = [requests.exceptions.ReadTimeout(), FakeResp(DEEPSEEK_OK)]
        with mock.patch.object(core.requests, 'post', side_effect=replies) as post:
            core.call_llm({'model': 'deepseek-flash'}, MESSAGES)
        self.assertEqual(post.call_count, 2)

    def test_deepseek_4xx_not_retried(self):
        with mock.patch.object(core.requests, 'post', return_value=FakeResp({}, 401)) as post:
            with self.assertRaises(requests.exceptions.HTTPError):
                core.call_llm({'model': 'deepseek-flash'}, MESSAGES)
        self.assertEqual(post.call_count, 1)

    def test_writing_model_env_override(self):
        from routers import writing_logic
        with mock.patch.dict(os.environ, {'WRITING_LLM_MODEL': 'deepseek-flash'}), \
                mock.patch.object(writing_logic, 'call_llm', return_value='ok') as call:
            writing_logic._writing_llm({'model': 'gemini-3.8-flash', 'temperature': 0.2}, MESSAGES)
        self.assertEqual(call.call_args.args[0]['model'], 'deepseek-flash')

        with mock.patch.object(writing_logic, 'call_llm', return_value='ok') as call:
            writing_logic._writing_llm({'model': 'gemini-3.8-flash'}, MESSAGES)
        self.assertEqual(call.call_args.args[0]['model'], 'gemini-3.8-flash')


if __name__ == '__main__':
    unittest.main()
