"""
base_url 自动补齐 /v1 前缀的回归测试。

OpenAI 客户端会把 base_url 与 "/chat/completions" 拼接，vLLM 等仅暴露
/v1/chat/completions 的服务会因缺少 /v1 返回 404。此处保证缺少 /v1 时自动补齐。
"""

from app.core.llm_clients import (
    clear_llm_clients,
    get_async_llm_client,
    get_llm_client,
)


class TestLlmBaseUrlNormalize:
    def test_appends_v1_when_missing(self):
        clear_llm_clients()
        try:
            c = get_llm_client("k", "http://llm.example:8201")
            assert str(c.base_url) == "http://llm.example:8201/v1/"
        finally:
            clear_llm_clients()

    def test_appends_v1_when_trailing_slash(self):
        clear_llm_clients()
        try:
            c = get_async_llm_client("k", "http://llm.example:8201/")
            assert str(c.base_url) == "http://llm.example:8201/v1/"
        finally:
            clear_llm_clients()

    def test_keeps_existing_v1(self):
        clear_llm_clients()
        try:
            c = get_llm_client("k", "https://api.deepseek.com/v1")
            assert str(c.base_url) == "https://api.deepseek.com/v1/"
        finally:
            clear_llm_clients()