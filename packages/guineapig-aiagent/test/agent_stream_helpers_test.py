"""
Task 5 回归测试 — agent.py 抽取的 _stream_llm_response 帮助函数。

验证：
1. SSE 事件序列与负载与重构前逐字节一致（event: content / event: error / fallback）
2. 三种失败模式：fallback 兜底、error 事件、仅日志
3. result 回传（text / input_tokens）
4. LLM 不可用时 fallback 路径
5. _direct_llm_stream 整体事件序列字节级一致
"""

import pytest

from app.routers.agent import _direct_llm_stream, _stream_llm_response


class _FakeDelta:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.delta = _FakeDelta(content)


class _FakeChunk:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)] if content else []


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        self._it = iter(self._chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _FakeCompletions:
    def __init__(self, chunks=None, exc=None):
        self._chunks = chunks or []
        self._exc = exc

    async def create(self, **kwargs):
        if self._exc is not None:
            raise self._exc
        return _FakeStream(self._chunks)


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeClient:
    def __init__(self, chunks=None, exc=None):
        self.chat = _FakeChat(_FakeCompletions(chunks, exc))


def _patch_client(mocker, chunks=None, exc=None):
    client = _FakeClient(chunks=chunks, exc=exc)
    mocker.patch(
        "app.routers.agent._get_llm_client",
        return_value=(client, "test-model"),
    )
    return client


def _patch_no_client(mocker, exc=ValueError("LLM_API_KEY not set")):
    mocker.patch("app.routers.agent._get_llm_client", side_effect=exc)


async def _collect(agen):
    return [ev async for ev in agen]


class TestStreamLlmResponse:
    """_stream_llm_response 三种模式 + 字节级事件一致"""

    @pytest.mark.asyncio
    async def test_success_content_events_byte_identical(self, mocker):
        """成功路径：event: content 逐块输出，内容与格式完全一致"""
        _patch_client(mocker, chunks=[_FakeChunk("你"), _FakeChunk("好"), _FakeChunk("")])
        result = {"text": "", "input_tokens": 0}

        events = await _collect(
            _stream_llm_response(
                "sys",
                "user msg",
                temperature=0.3,
                max_tokens=512,
                span_name="reject-llm-stream",
                span_input={"reject_reason": "x", "user_message": "m"},
                span_metadata={"source": "agent.reject_event_stream"},
                trace_id="t1",
                result=result,
            )
        )

        assert events == [
            'event: content\ndata: {"content":"你"}\n\n',
            'event: content\ndata: {"content":"好"}\n\n',
        ]
        assert result["text"] == "你好"
        assert result["input_tokens"] == 2  # _estimate_tokens("user msg") = 8/4 = 2

    @pytest.mark.asyncio
    async def test_fallback_mode_byte_identical(self, mocker):
        """fallback 模式：流式调用抛异常时输出兜底 content 事件（reject/dag-empty 路径）"""
        _patch_client(mocker, chunks=[_FakeChunk("部")], exc=RuntimeError("boom"))
        result = {"text": ""}

        events = await _collect(
            _stream_llm_response(
                "sys",
                "user",
                temperature=0.3,
                max_tokens=512,
                span_name="reject-llm-stream",
                span_input=None,
                span_metadata=None,
                trace_id=None,
                fallback_text="抱歉，我无法执行此任务。规则不允许",
                error_log_level="warning",
                error_log_prefix="[Agent] Reject LLM 失败: ",
                result=result,
            )
        )

        assert events == [
            'event: content\ndata: {"content":"抱歉，我无法执行此任务。规则不允许"}\n\n'
        ]
        assert result["text"] == "抱歉，我无法执行此任务。规则不允许"

    @pytest.mark.asyncio
    async def test_error_event_mode_byte_identical(self, mocker):
        """error 事件模式：直接回复路径失败时输出 event: error"""
        _patch_client(mocker, exc=RuntimeError("timeout"))
        result = {"text": ""}

        events = await _collect(
            _stream_llm_response(
                "sys",
                "user",
                temperature=0.7,
                max_tokens=2048,
                span_name="direct-llm-stream",
                span_input={"system": "sys", "user": "user"},
                span_metadata={"source": "agent._direct_llm_stream"},
                trace_id=None,
                error_event_message="LLM 调用失败: {error}",
                error_log_level="error",
                error_log_prefix="[Agent-LLM] 直接回复流式调用失败: ",
                result=result,
            )
        )

        assert events == ['event: error\ndata: {"message":"LLM 调用失败: timeout"}\n\n']
        assert result["text"] == ""

    @pytest.mark.asyncio
    async def test_log_only_mode(self, mocker):
        """仅日志模式：总结路径失败时不产出任何事件"""
        _patch_client(mocker, exc=RuntimeError("oops"))
        result = {"text": ""}

        events = await _collect(
            _stream_llm_response(
                "sys",
                "user",
                temperature=0.3,
                max_tokens=2048,
                span_name="stream-execution-summary",
                span_input={"system": "sys", "user": "user"},
                span_metadata={"source": "agent._stream_execution_summary"},
                trace_id=None,
                error_log_level="error",
                error_log_prefix="[Agent-Summary] LLM 流式调用失败: ",
                result=result,
            )
        )

        assert events == []
        assert result["text"] == ""

    @pytest.mark.asyncio
    async def test_client_unavailable_fallback(self, mocker):
        """LLM 不可用时（_get_llm_client 抛 ValueError）→ 走 fallback（不再使用未定义的 model_name）"""
        _patch_no_client(mocker)
        result = {"text": ""}

        events = await _collect(
            _stream_llm_response(
                "sys",
                "user",
                temperature=0.3,
                max_tokens=512,
                span_name="reject-llm-stream",
                span_input=None,
                span_metadata=None,
                trace_id="t1",
                fallback_text="抱歉，我无法执行此任务。",
                error_log_level="warning",
                error_log_prefix="[Agent] Reject LLM 失败: ",
                result=result,
            )
        )

        # reject 路径：LLM 不可用时输出兜底 content 事件
        assert events == ['event: content\ndata: {"content":"抱歉，我无法执行此任务。"}\n\n']
        assert result["text"] == "抱歉，我无法执行此任务。"

    @pytest.mark.asyncio
    async def test_input_tokens_not_set_when_client_unavailable(self, mocker):
        """LLM 不可用时 result["input_tokens"] 不被设置（保持默认 0，与 dag-empty 原逻辑一致）"""
        _patch_no_client(mocker)
        result = {"text": "", "input_tokens": 0}

        await _collect(
            _stream_llm_response(
                "sys",
                "user",
                temperature=0.3,
                max_tokens=1024,
                span_name="dag-empty-llm-stream",
                span_input=None,
                span_metadata=None,
                trace_id=None,
                fallback_text="fallback",
                error_log_level="warning",
                error_log_prefix="[Agent-Stream] DAG-empty LLM 流式调用失败: ",
                result=result,
            )
        )

        assert result["input_tokens"] == 0
        assert result["text"] == "fallback"


class TestDirectLlmStream:
    """_direct_llm_stream 整体事件序列字节级一致"""

    @pytest.mark.asyncio
    async def test_success_sequence_byte_identical(self, mocker):
        """成功：content 事件 + execution_complete(completed)"""
        _patch_client(mocker, chunks=[_FakeChunk("你好"), _FakeChunk("！")])
        mocker.patch("app.routers.agent.report_chat_metrics")

        events = await _collect(
            _direct_llm_stream(
                "你好",
                user_id=1,
                session_id="s1",
                scene_memory=[{"type": "pref", "content": "喜欢简洁"}],
                trace_id="t1",
            )
        )

        assert events == [
            'event: content\ndata: {"content":"你好"}\n\n',
            'event: content\ndata: {"content":"！"}\n\n',
            'event: execution_complete\ndata: {"status":"completed","summary":{"steps_completed":0,"steps_total":0}}\n\n',
        ]

    @pytest.mark.asyncio
    async def test_stream_failure_sequence_byte_identical(self, mocker):
        """流式失败：error 事件 + execution_complete(completed)"""
        _patch_client(mocker, exc=RuntimeError("boom"))
        mocker.patch("app.routers.agent.report_chat_metrics")

        events = await _collect(
            _direct_llm_stream("你好", user_id=1, session_id="s1", trace_id="t1")
        )

        assert events == [
            'event: error\ndata: {"message":"LLM 调用失败: boom"}\n\n',
            'event: execution_complete\ndata: {"status":"completed","summary":{"steps_completed":0,"steps_total":0}}\n\n',
        ]

    @pytest.mark.asyncio
    async def test_client_unavailable_sequence_byte_identical(self, mocker):
        """LLM 不可用：error + execution_complete(failed)"""
        _patch_no_client(mocker)
        mocker.patch("app.routers.agent.report_chat_metrics")

        events = await _collect(
            _direct_llm_stream("你好", user_id=1, session_id="s1", trace_id="t1")
        )

        assert events == [
            'event: error\ndata: {"message":"LLM 不可用"}\n\n',
            'event: execution_complete\ndata: {"status":"failed","reason":"LLM 不可用"}\n\n',
        ]