"""
LLM 客户端复用 — 进程内缓存 OpenAI / AsyncOpenAI 实例。

每次调用都新建客户端会重复建立 TCP 连接、重复 TLS 握手，
这里按 (sync/async, api_key, base_url, timeout) 缓存，同一配置只初始化一次。

线程安全：用锁保护缓存的创建与读取。
"""

import asyncio
import threading
import time

from openai import (
    AsyncOpenAI,
    OpenAI,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
)

from app.config import settings
from app.core.log import logger

_cache: dict[tuple, object] = {}
_cache_lock = threading.Lock()

# 不重试的确定性错误（鉴权/参数/资源不存在，重试无意义）
_NON_RETRYABLE_EXC = (
    AuthenticationError,
    PermissionDeniedError,
    BadRequestError,
    NotFoundError,
)


def get_llm_client(api_key: str, base_url: str, timeout: float = 120.0) -> OpenAI:
    """获取（缓存的）同步 OpenAI 客户端。"""
    return _get_client(is_async=False, api_key=api_key, base_url=base_url, timeout=timeout)


def get_async_llm_client(
    api_key: str, base_url: str, timeout: float = 120.0
) -> AsyncOpenAI:
    """获取（缓存的）异步 AsyncOpenAI 客户端。"""
    return _get_client(is_async=True, api_key=api_key, base_url=base_url, timeout=timeout)


def _get_client(is_async: bool, api_key: str, base_url: str, timeout: float):
    key = (is_async, api_key, base_url, timeout)
    with _cache_lock:
        client = _cache.get(key)
        if client is None:
            if is_async:
                client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
            else:
                client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
            _cache[key] = client
    return client


def clear_llm_clients() -> None:
    """清空客户端缓存（主要用于测试隔离）。"""
    with _cache_lock:
        _cache.clear()


def _should_retry(exc: Exception) -> bool:
    """判断异常是否值得重试（鉴权/参数类错误直接抛出）。"""
    return not isinstance(exc, _NON_RETRYABLE_EXC)


def call_with_retry(fn, *args, **kwargs):
    """
    有界重试封装（同步）：LLM 调用失败时按 LLM_RETRY_ATTEMPTS 次指数退避重试。
    最终仍失败则抛出最后一次异常，由调用方的 fallback 逻辑兜底。
    """
    retries = max(0, settings.LLM_RETRY_ATTEMPTS)
    attempt = 0
    while True:
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt >= retries or not _should_retry(e):
                raise
            attempt += 1
            delay = settings.LLM_RETRY_BACKOFF * (2 ** (attempt - 1))
            logger.warning(f"[LLM-Retry] 调用失败，{attempt}/{retries} 次重试（{delay:.1f}s 后）: {e}")
            time.sleep(delay)


async def call_with_retry_async(fn, *args, **kwargs):
    """
    有界重试封装（异步）：同上，供 async 路径使用。
    """
    retries = max(0, settings.LLM_RETRY_ATTEMPTS)
    attempt = 0
    while True:
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            if attempt >= retries or not _should_retry(e):
                raise
            attempt += 1
            delay = settings.LLM_RETRY_BACKOFF * (2 ** (attempt - 1))
            logger.warning(f"[LLM-Retry] 调用失败，{attempt}/{retries} 次重试（{delay:.1f}s 后）: {e}")
            await asyncio.sleep(delay)
