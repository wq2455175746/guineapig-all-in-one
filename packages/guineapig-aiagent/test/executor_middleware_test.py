"""执行中间件 — 内核 + 叠加 的可拦截扩展点。"""

import pytest

from app.agent.models import (
    DAGDefinition,
    DAGStep,
    ExecutionLocation,
    StreamEventType,
)
from app.agent.executor.engine import DAGExecutionEngine
from app.agent.executor.middleware import (
    BlockResult,
    MiddlewareRunner,
    StepContext,
    StepMiddleware,
    default_middlewares,
)


def _step(capability="web_search"):
    return DAGStep(step_id="s1", capability=capability, action="x")


class TestRunner:
    @pytest.mark.asyncio
    async def test_before_step_block_short_circuits(self):
        class Blocker(StepMiddleware):
            name = "blocker"

            async def before_step(self, ctx):
                return BlockResult(block=True, reason="危险操作")

        class NeverReached(StepMiddleware):
            async def before_step(self, ctx):
                raise AssertionError("不应被调用")

        runner = MiddlewareRunner([Blocker(), NeverReached()])
        ctx = StepContext(step=_step(), params={})
        res = await runner.before_step(ctx)
        assert res is not None and res.block
        assert res.reason == "危险操作"

    @pytest.mark.asyncio
    async def test_after_step_chains_transforms(self):
        class A(StepMiddleware):
            async def after_step(self, ctx):
                return {"result": ctx.result["result"] + "-A"}

        class B(StepMiddleware):
            async def after_step(self, ctx):
                return {"result": ctx.result["result"] + "-B"}

        runner = MiddlewareRunner([A(), B()])
        ctx = StepContext(step=_step(), params={}, result={"result": "x"})
        out = await runner.after_step(ctx)
        assert out["result"] == "x-A-B"
        assert ctx.result["result"] == "x-A-B"

    @pytest.mark.asyncio
    async def test_on_step_error_isolates_exceptions(self):
        class Boom(StepMiddleware):
            async def on_step_error(self, ctx):
                raise RuntimeError("boom")

        runner = MiddlewareRunner([Boom()])
        # 不应抛出
        await runner.on_step_error(StepContext(step=_step(), params={}, error="e"))


class TestDefaultMiddlewares:
    @pytest.mark.asyncio
    async def test_param_resolution_uses_resolver(self):
        runner = MiddlewareRunner(default_middlewares())
        ctx = StepContext(
            step=_step(),
            params={"q": "{{s0.result}}"},
            resolver=lambda p: {"q": "resolved"},
        )
        await runner.before_step(ctx)
        assert ctx.resolved_params == {"q": "resolved"}

    @pytest.mark.asyncio
    async def test_unresolved_guard_blocks(self):
        runner = MiddlewareRunner(default_middlewares())
        ctx = StepContext(
            step=_step(),
            params={"q": "{{s0.result}}"},
            resolver=lambda p: dict(p),
            unresolved_checker=lambda p: True,
        )
        res = await runner.before_step(ctx)
        assert res is not None and res.block

    @pytest.mark.asyncio
    async def test_mcp_injection_applies(self):
        runner = MiddlewareRunner(default_middlewares())
        ctx = StepContext(
            step=_step("mcp_amap"),
            params={"tool": "weather"},
            resolver=lambda p: dict(p),
            unresolved_checker=lambda p: False,
            mcp_match=lambda cap: {"server_name": "amap"},
            mcp_inject=lambda params, srv: {**params, "mcp_url": "http://x"},
        )
        await runner.before_step(ctx)
        assert ctx.resolved_params["mcp_url"] == "http://x"


class _BlockDelete(StepMiddleware):
    name = "block_delete"

    async def before_step(self, ctx):
        if ctx.step.capability == "cli":
            return BlockResult(block=True, reason="禁止执行 CLI")
        return None


class _TagResult(StepMiddleware):
    name = "tag_result"

    async def after_step(self, ctx):
        if ctx.result and "result" in ctx.result:
            return {**ctx.result, "result": ctx.result["result"] + "[tagged]"}
        return None


@pytest.mark.asyncio
async def test_custom_middleware_blocks_step():
    dag = DAGDefinition(
        steps=[DAGStep(step_id="s1", capability="cli", action="x", max_retries=0)],
        original_intent="t",
    )
    engine = DAGExecutionEngine(dag, middlewares=[_BlockDelete()])
    events = [e async for e in engine.execute()]
    assert any(e.event == StreamEventType.STEP_FAILED.value for e in events)
    assert engine.step_results["s1"]["error_type"] == "unresolved_ref"


@pytest.mark.asyncio
async def test_custom_middleware_transforms_result(mocker):
    from app.agent.executor import handlers as handlers_mod

    async def ok(capability, params):
        return {"result": "answer"}

    mocker.patch.object(handlers_mod.CapabilityHandlers, "execute", side_effect=ok)
    dag = DAGDefinition(
        steps=[DAGStep(step_id="s1", capability="rag", action="x", max_retries=0)],
        original_intent="t",
    )
    engine = DAGExecutionEngine(dag, middlewares=[_TagResult()])
    _ = [e async for e in engine.execute()]
    assert engine.step_results["s1"]["result"] == "answer[tagged]"


@pytest.mark.asyncio
async def test_truncation_middleware_in_default_chain(mocker):
    from app.agent.executor import handlers as handlers_mod

    async def huge(capability, params):
        return {"result": "line\n" * 100000}

    mocker.patch.object(handlers_mod.CapabilityHandlers, "execute", side_effect=huge)
    dag = DAGDefinition(
        steps=[DAGStep(step_id="s1", capability="rag", action="x", max_retries=0)],
        original_intent="t",
    )
    engine = DAGExecutionEngine(dag)  # 默认中间件
    _ = [e async for e in engine.execute()]
    assert engine.step_results["s1"].get("truncated") is True


@pytest.mark.asyncio
async def test_on_step_error_observes_failure(mocker):
    from app.agent.executor import handlers as handlers_mod

    observed = []

    class Observer(StepMiddleware):
        name = "observer"

        async def on_step_error(self, ctx):
            observed.append((ctx.step.step_id, ctx.error))

    async def fail(capability, params):
        return {"error": "boom", "error_type": "tool_error", "result": ""}

    mocker.patch.object(handlers_mod.CapabilityHandlers, "execute", side_effect=fail)
    dag = DAGDefinition(
        steps=[DAGStep(step_id="s1", capability="rag", action="x", max_retries=0)],
        original_intent="t",
    )
    engine = DAGExecutionEngine(dag, middlewares=[Observer()])
    _ = [e async for e in engine.execute()]
    assert observed == [("s1", "boom")]


@pytest.mark.asyncio
async def test_blocked_step_triggers_on_step_error():
    """被中间件拦截的步骤属终态失败，应先于 STEP_FAILED 通知 on_step_error。"""
    observed = []
    order = []

    class Observer(StepMiddleware):
        name = "observer"

        async def on_step_error(self, ctx):
            observed.append((ctx.step.step_id, ctx.error, ctx.error_type))
            order.append("error")

    dag = DAGDefinition(
        steps=[DAGStep(step_id="s1", capability="cli", action="x", max_retries=0)],
        original_intent="t",
    )
    engine = DAGExecutionEngine(dag, middlewares=[_BlockDelete(), Observer()])
    async for e in engine.execute():
        if e.event == StreamEventType.STEP_FAILED.value:
            order.append("failed")

    assert observed == [("s1", "禁止执行 CLI", "unresolved_ref")]
    assert order == ["error", "failed"]


@pytest.mark.asyncio
async def test_guard_legacy_message_server():
    """server 步骤未解析占位符时保留旧消息文案（无法执行）。"""
    dag = DAGDefinition(
        steps=[
            DAGStep(
                step_id="s1",
                capability="llm_chat",
                action="x",
                params={"prompt": "{{missing.ref}}"},
            )
        ],
        original_intent="t",
    )
    engine = DAGExecutionEngine(dag)
    events = [e async for e in engine.execute()]
    failed = [e for e in events if e.event == StreamEventType.STEP_FAILED.value]
    assert failed
    assert "无法执行" in failed[0].data["error"]
    assert "无法下发" not in failed[0].data["error"]


@pytest.mark.asyncio
async def test_guard_legacy_message_client():
    """client 步骤未解析占位符时保留旧消息文案（无法下发 client 执行）。"""
    dag = DAGDefinition(
        steps=[
            DAGStep(
                step_id="s1",
                capability="cli",
                action="x",
                execution_location=ExecutionLocation.CLIENT,
                params={"command": "echo {{missing.ref}}"},
            )
        ],
        original_intent="t",
    )
    engine = DAGExecutionEngine(dag)
    events = [e async for e in engine.execute()]
    failed = [e for e in events if e.event == StreamEventType.STEP_FAILED.value]
    assert failed
    assert "无法下发 client 执行" in failed[0].data["error"]


@pytest.mark.asyncio
async def test_client_delegate_failure_triggers_on_step_error(mocker):
    """client 委托失败应先于 STEP_FAILED 以 error_type=client_error 通知观察者。"""
    from app.agent.event_manager import AgentEventManager

    observed = []
    order = []

    class Observer(StepMiddleware):
        name = "observer"

        async def on_step_error(self, ctx):
            observed.append((ctx.step.step_id, ctx.error, ctx.error_type))
            order.append("error")

    async def fake_wait(session_id, step_id, timeout=600):
        return {"error": "boom"}

    mocker.patch.object(
        AgentEventManager, "wait_for_delegate", side_effect=fake_wait
    )

    dag = DAGDefinition(
        steps=[
            DAGStep(
                step_id="s1",
                capability="cli",
                action="x",
                execution_location=ExecutionLocation.CLIENT,
                params={"command": "ls"},
            )
        ],
        original_intent="t",
    )
    engine = DAGExecutionEngine(
        dag, middlewares=[Observer()], context={"session_id": "conv_1"}
    )
    async for e in engine.execute():
        if e.event == StreamEventType.STEP_FAILED.value:
            order.append("failed")

    assert observed == [("s1", "boom", "client_error")]
    assert order == ["error", "failed"]
