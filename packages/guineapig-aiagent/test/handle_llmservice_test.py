"""
LLM 原子能力单元测试
"""

import os
import sys

import pytest

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def _patch_llm_settings(mocker, api_key="test_key", base_url="https://test.api.com/v1", model_name="test-model"):
    """辅助：patch settings 中的 LLM 配置字段"""
    mocker.patch("app.config.settings.LLM_API_KEY", api_key)
    mocker.patch("app.config.settings.LLM_BASE_URL", base_url)
    mocker.patch("app.config.settings.LLM_MODEL_NAME", model_name)


def _reset_llm_state():
    """清空共享 LLM 客户端缓存与 handle_llmservice 模块级缓存"""
    import app.core.llm_clients as llm_clients
    import app.services.handle_llmservice as llm_service

    llm_clients.clear_llm_clients()
    llm_service._llm_client = None
    llm_service._model_name = None


class TestGetLlmResponse:
    """get_llm_response 单元测试"""

    def test_success(self, mocker):
        """正常 LLM 调用应返回回复文本"""
        mock_choice = mocker.MagicMock()
        mock_choice.message.content = "这是一个测试回复"

        mock_completion = mocker.MagicMock()
        mock_completion.choices = [mock_choice]

        mock_client = mocker.MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion

        mocker.patch("app.core.llm_clients.OpenAI", return_value=mock_client)

        import app.services.handle_llmservice as llm_service
        _reset_llm_state()

        _patch_llm_settings(mocker)

        result = llm_service.get_llm_response("你好")

        assert result == "这是一个测试回复"
        mock_client.chat.completions.create.assert_called_once()

    def test_missing_api_key(self, mocker):
        """缺少 LLM_API_KEY 时应抛出 ValueError"""
        import app.services.handle_llmservice as llm_service
        _reset_llm_state()

        # LLM_API_KEY 为空（默认值）
        mocker.patch("app.config.settings.LLM_API_KEY", "")

        with pytest.raises(ValueError, match="LLM_API_KEY not set in .env"):
            llm_service.get_llm_response("你好")

    def test_includes_system_messages(self, mocker):
        """LLM 请求应包含 system 和 assistant 预设消息"""
        mock_choice = mocker.MagicMock()
        mock_choice.message.content = "回复"

        mock_completion = mocker.MagicMock()
        mock_completion.choices = [mock_choice]

        mock_client = mocker.MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion

        mocker.patch("app.core.llm_clients.OpenAI", return_value=mock_client)

        import app.services.handle_llmservice as llm_service
        _reset_llm_state()

        _patch_llm_settings(mocker, api_key="test_key")

        llm_service.get_llm_response("测试文本")

        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        assert len(messages) == 4
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[2]["role"] == "assistant"
        assert messages[3]["role"] == "user"
        assert messages[3]["content"] == "测试文本"

    def test_client_lazy_loading(self, mocker):
        """LLM 客户端应惰性加载（多次调用重用同一 client）"""
        mock_client = mocker.MagicMock()
        mock_client.chat.completions.create.return_value.choices[0].message.content = "ok"

        mock_openai_cls = mocker.patch("app.core.llm_clients.OpenAI", return_value=mock_client)

        import app.services.handle_llmservice as llm_service
        _reset_llm_state()

        _patch_llm_settings(mocker, api_key="test_key")

        # 第一次调用
        llm_service.get_llm_response("你好")
        assert mock_openai_cls.call_count == 1

        # 第二次调用（应复用 client）
        mock_openai_cls.reset_mock()
        llm_service.get_llm_response("再问一次")
        assert mock_openai_cls.call_count == 0  # 不应再次初始化
