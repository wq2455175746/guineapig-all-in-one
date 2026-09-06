"""
Milvus 客户端复用 — 按线程缓存 MilvusClient 实例。

MilvusClient 并非严格线程安全，且频繁新建客户端会重复握手建立连接。
这里使用 threading.local 按线程缓存（默认线程池的 worker 会被复用），
每个线程至多一个 client，天然线程安全。
"""

import threading

_milvus_local = threading.local()


def get_milvus_client(host: str, port: str, db_name: str):
    """返回当前线程缓存的 MilvusClient（按 host/port/db_name 区分）。"""
    from pymilvus import MilvusClient

    cache = getattr(_milvus_local, "clients", None)
    if cache is None:
        cache = {}
        _milvus_local.clients = cache
    key = (host, port, db_name)
    client = cache.get(key)
    if client is None:
        client = MilvusClient(uri=f"http://{host}:{port}", db_name=db_name)
        cache[key] = client
    return client


def clear_milvus_clients() -> None:
    """清空当前线程的客户端缓存（主要用于测试隔离）。"""
    _milvus_local.clients = {}
