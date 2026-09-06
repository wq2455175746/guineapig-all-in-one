"""
LLM 客户端复用 — 进程内缓存 OpenAI / AsyncOpenAI 实例。

每次调用都新建客户端会重复建立 TCP 连接、重复 TLS 握手，
这里按 (sync/async, api_key, base_url, timeout) 缓存，同一配置只初始化一次。

线程安全：用锁保护缓存的创建与读取。
"""

import threading

from openai import AsyncOpenAI, OpenAI

_cache: dict[tuple, object] = {}
_cache_lock = threading.Lock()


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
