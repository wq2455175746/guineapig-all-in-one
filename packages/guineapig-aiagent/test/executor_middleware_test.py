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
        class Resolver:
            async def before_step(self, ctx):
                return None

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
