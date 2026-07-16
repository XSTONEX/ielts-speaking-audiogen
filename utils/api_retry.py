"""出站 API 统一重试（tenacity）。

仅用于外部 HTTP/LLM 调用的瞬态失败；业务 4xx、本地逻辑错误不重试。
"""

from __future__ import annotations

import json
from typing import Callable, Optional

import requests
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

# 客户端/鉴权类错误：重试无意义
NON_RETRYABLE_STATUS = frozenset({400, 401, 403, 404, 413, 422})
# 明确可重试的 HTTP 状态
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


class RetryableAPIError(Exception):
    """可重试的出站 API 错误（5xx/429/空响应/格式异常等）。"""


class NonRetryableAPIError(Exception):
    """不可重试的出站 API 错误（4xx 等）。"""


def _openai_status_retryable(exc: BaseException) -> Optional[bool]:
    """识别 OpenAI SDK 异常是否可重试；非 OpenAI 异常返回 None。"""
    module = getattr(type(exc), '__module__', '') or ''
    if not module.startswith('openai'):
        return None
    name = type(exc).__name__
    if name in ('APITimeoutError', 'APIConnectionError', 'RateLimitError', 'InternalServerError'):
        return True
    status = getattr(exc, 'status_code', None)
    if status is None:
        # 其它 openai 错误默认不重试（避免把鉴权失败打满）
        return False
    if status in NON_RETRYABLE_STATUS:
        return False
    if status in RETRYABLE_STATUS or status >= 500:
        return True
    if 400 <= status < 500:
        return False
    return True


def is_retryable_exception(exc: BaseException) -> bool:
    """判断异常是否值得重试。"""
    if isinstance(exc, RetryableAPIError):
        return True
    if isinstance(exc, NonRetryableAPIError):
        return False
    if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return True
    if isinstance(exc, json.JSONDecodeError):
        return True
    openai_decision = _openai_status_retryable(exc)
    if openai_decision is not None:
        return openai_decision
    if isinstance(exc, requests.exceptions.HTTPError):
        resp = getattr(exc, 'response', None)
        if resp is not None:
            code = resp.status_code
            if code in NON_RETRYABLE_STATUS:
                return False
            if code in RETRYABLE_STATUS or code >= 500:
                return True
            # 其它 4xx 不重试
            if 400 <= code < 500:
                return False
        return True
    # 其它 RequestException（不含已处理的 HTTPError 子类路径）
    if isinstance(exc, requests.exceptions.RequestException):
        return not isinstance(exc, requests.exceptions.HTTPError)
    return False


def raise_for_status_retryable(response: requests.Response, preview: int = 200) -> None:
    """按状态码抛出可/不可重试异常；2xx 直接返回。"""
    if 200 <= response.status_code < 300:
        return

    body = (response.text or '')[:preview]
    msg = f'HTTP {response.status_code}: {body}'

    if response.status_code in NON_RETRYABLE_STATUS:
        raise NonRetryableAPIError(msg)
    if response.status_code in RETRYABLE_STATUS or response.status_code >= 500:
        raise RetryableAPIError(msg)
    if 400 <= response.status_code < 500:
        raise NonRetryableAPIError(msg)
    raise RetryableAPIError(msg)


def _log_before_sleep(retry_state: RetryCallState) -> None:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    fn = retry_state.fn
    name = getattr(fn, '__name__', repr(fn))
    print(
        f'[api_retry] {name} attempt {retry_state.attempt_number} failed: {exc!r}; '
        f'retrying in {retry_state.next_action.sleep:.1f}s...'
    )


def make_api_retry(
    attempts: int = 3,
    *,
    min_wait: float = 1,
    max_wait: float = 8,
    multiplier: float = 1,
) -> Callable:
    """构造 tenacity retry 装饰器（默认 3 次、指数退避）。"""
    return retry(
        reraise=True,
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=multiplier, min=min_wait, max=max_wait),
        retry=retry_if_exception(is_retryable_exception),
        before_sleep=_log_before_sleep,
    )


# 项目默认：最多 3 次，等待约 1s → 2s → 4s（上限 8s）
api_retry = make_api_retry(3)
