# 内核 + 叠加 重构：可拦截扩展点 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 803 行的 `DAGExecutionEngine` 按"内核 + 叠加"重构：内核只负责拓扑序、事件流、重试、client 委托与状态记录；把参数解析、MCP 连接注入、未解析占位符拦截、输出截断、错误上报等横切逻辑抽成可插拔 `StepMiddleware`。外部 SSE 事件契约与现有单测行为**完全不变**。

**Architecture:** 新增 `app/agent/executor/middleware.py`（`StepContext` / `BlockResult` / `StepMiddleware` / `MiddlewareRunner` + 三个默认中间件）。

**Tech Stack:** Python 3.13, loguru, pytest + pytest-asyncio + pytest-mock。

**Spec:** `docs/design-docs/pi-agent-borrowable-ideas.md`（#6 内核+叠加、#10 可拦截扩展点）

## Global Constraints

- **行为零回归**：`test/executor_engine_test.py` 全部用例必须原样通过；SSE 事件名称与 `data` 字段不得改变。
- 中间件**不产出 SSE 事件**（事件由内核发出）：`before_step` 只返回放行/拦截决策，`after_step` 只返回结果转换，`on_step_error` 只做观测。
- 默认中间件顺序：`ParamResolutionMiddleware` → `McpConnectionMiddleware` → `UnresolvedRefGuardMiddleware`（与现有"先解析、再注入、后校验"语义等价）。
- 保持 `_resolve_params` / `_has_unresolved_refs` / `_match_mcp_server` / `_inject_conn_params` 方法不变，由中间件复用（不重写解析算法）。
- 不引入新依赖。
- 测试命令：`cd packages/guineapig-aiagent && uv run pytest -q`。

> **推荐执行顺序：** 先实施《错误即消息》与《工具输出截断》两个计划，再实施本计划——这样本计划可顺手把它们的内联逻辑迁移为中间件（Task 4/5）。本计划也可独立于二者实施（Task 4/5 可跳过）。

---

## File Structure

- **Create** `packages/guineapig-aiagent/app/agent/executor/middleware.py` — 中间件类型与默认实现。
- **Modify** `packages/guineapig-aiagent/app/agent/executor/engine.py` — 构造注入中间件、`_execute_step` 拆分改写。
- **Modify** `packages/guineapig-aiagent/app/agent/executor/__init__.py` — 导出 `StepMiddleware` / `StepContext` / `default_middlewares`（便于扩展方引用）。
- **Test** `packages/guineapig-aiagent/test/executor_middleware_test.py`

---

## Task 1: 中间件类型与运行器

**Files:**
- Create: `packages/guineapig-aiagent/app/agent/executor/middleware.py`
- Test: `packages/guineapig-aiagent/test/executor_middleware_test.py`

**Interfaces:**
- Produces:
  - `StepContext(step, params, resolved_params={}, result=None, error="", error_type="", error_suggestion="", attempt=0, inventory=None, session_id="", step_results={}, context={}, resolver=None, unresolved_checker=None, mcp_match=None, mcp_inject=None)`
  - `BlockResult(block: bool, reason: str = "")`
  - `StepMiddleware`（`async before_step(ctx) -> BlockResult|None`、`async after_step(ctx) -> dict|None`、`async on_step_error(ctx) -> None`）
  - `MiddlewareRunner(middlewares)`（`before_step` / `after_step` / `on_step_error`）
  - `ParamResolutionMiddleware` / `McpConnectionMiddleware` / `UnresolvedRefGuardMiddleware`
  - `default_middlewares() -> list[StepMiddleware]`

- [ ] **Step 1: 写失败测试**

Create `packages/guineapig-aiagent/test/executor_middleware_test.py`:

```python
"""执行中间件 — 内核 + 叠加 的可拦截扩展点。"""

import pytest

from app.agent.models import DAGStep, ExecutionLocation
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/guineapig-aiagent && uv run pytest test/executor_middleware_test.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agent.executor.middleware'`

- [ ] **Step 3: 实现 middleware.py**

Create `packages/guineapig-aiagent/app/agent/executor/middleware.py`:

```python
"""DAG 执行中间件 — 内核 + 叠加（可拦截扩展点）。

内核（engine）负责：拓扑序、SSE 事件流、重试、client 委托、状态记录。
叠加（middleware）负责：参数解析、MCP 连接注入、未解析占位符拦截、输出截断、
错误上报等横切逻辑。中间件不产出 SSE 事件，只做纯转换/决策。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.core.log import logger
from ..models import DAGStep, ExecutionLocation


@dataclass
class StepContext:
    step: DAGStep
    params: dict
    resolved_params: dict = field(default_factory=dict)
    result: Optional[dict] = None
    error: str = ""
    error_type: str = ""
    error_suggestion: str = ""
    attempt: int = 0
    inventory: Any = None
    session_id: str = ""
    step_results: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)
    # 引擎能力注入（供中间件复用内核解析逻辑，避免重复实现）
    resolver: Optional[Callable[[dict], dict]] = None
    unresolved_checker: Optional[Callable[[Any], bool]] = None
    mcp_match: Optional[Callable[[str], Any]] = None
    mcp_inject: Optional[Callable[[dict, Any], dict]] = None


@dataclass
class BlockResult:
    block: bool
    reason: str = ""


class StepMiddleware:
    """中间件基类 — 三个钩子默认全部放行/空操作。"""

    name = "middleware"

    async def before_step(self, ctx: StepContext) -> Optional[BlockResult]:
        return None

    async def after_step(self, ctx: StepContext) -> Optional[dict]:
        return None

    async def on_step_error(self, ctx: StepContext) -> None:
        return None


class MiddlewareRunner:
    def __init__(self, middlewares: list[StepMiddleware] | None = None):
        self.middlewares = list(middlewares or [])

    async def before_step(self, ctx: StepContext) -> Optional[BlockResult]:
        for mw in self.middlewares:
            res = await mw.before_step(ctx)
            if res is not None and res.block:
                logger.warning(
                    f"[Middleware:{mw.name}] 拦截步骤 {ctx.step.step_id}: {res.reason}"
                )
                return res
        return None

    async def after_step(self, ctx: StepContext) -> Optional[dict]:
        result = ctx.result
        for mw in self.middlewares:
            updated = await mw.after_step(ctx)
            if updated is not None:
                result = updated
                ctx.result = updated
        return result

    async def on_step_error(self, ctx: StepContext) -> None:
        for mw in self.middlewares:
            try:
                await mw.on_step_error(ctx)
            except Exception as e:
                logger.opt(exception=e).error(
                    f"[Middleware:{mw.name}] on_step_error 失败: {e}"
                )


class ParamResolutionMiddleware(StepMiddleware):
    """解析参数中的 {{step_id.output_key}} / {{output_key}} 引用。"""

    name = "param_resolution"

    async def before_step(self, ctx: StepContext) -> Optional[BlockResult]:
        if ctx.resolver is not None:
            ctx.resolved_params = ctx.resolver(ctx.params)
        else:
            ctx.resolved_params = dict(ctx.params)
        return None


class McpConnectionMiddleware(StepMiddleware):
    """为 MCP 步骤注入连接信息（URL/transport/headers/stdio 启动参数）。"""

    name = "mcp_connection"

    async def before_step(self, ctx: StepContext) -> Optional[BlockResult]:
        cap = ctx.step.capability
        if cap.startswith("mcp_") and ctx.mcp_match is not None and ctx.mcp_inject is not None:
            srv = ctx.mcp_match(cap)
            if srv is not None:
                ctx.resolved_params = ctx.mcp_inject(ctx.resolved_params, srv)
        return None


class UnresolvedRefGuardMiddleware(StepMiddleware):
    """参数中残留未解析占位符时拦截执行，避免把占位符当真实数据使用。"""

    name = "unresolved_ref_guard"

    async def before_step(self, ctx: StepContext) -> Optional[BlockResult]:
        if ctx.unresolved_checker is not None and ctx.unresolved_checker(ctx.resolved_params):
            loc = ctx.step.execution_location.value
            return BlockResult(
                block=True,
                reason=(
                    f"参数包含未解析的占位符，无法下发 {loc} 执行: "
                    f"params={ctx.resolved_params}"
                ),
            )
        return None


def default_middlewares() -> list[StepMiddleware]:
    """内核默认叠加层 — 复现重构前的参数解析/注入/校验行为。"""
    return [
        ParamResolutionMiddleware(),
        McpConnectionMiddleware(),
        UnresolvedRefGuardMiddleware(),
    ]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd packages/guineapig-aiagent && uv run pytest test/executor_middleware_test.py -q`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
git add packages/guineapig-aiagent/app/agent/executor/middleware.py packages/guineapig-aiagent/test/executor_middleware_test.py
git commit -m "feat(aiagent): add DAG step middleware framework (kernel + overlay)"
```

---

## Task 2: 引擎接入中间件（行为零回归）

**Files:**
- Modify: `packages/guineapig-aiagent/app/agent/executor/engine.py`
- Modify: `packages/guineapig-aiagent/app/agent/executor/__init__.py`
- Test: `packages/guineapig-aiagent/test/executor_engine_test.py`（既有，作为回归护栏）

**Interfaces:**
- Consumes: `MiddlewareRunner` / `StepContext` / `default_middlewares`
- Produces: `DAGExecutionEngine(dag, context=None, middlewares=None)`；`self._runner`

- [ ] **Step 1: 运行既有测试建立绿色基线**

Run: `cd packages/guineapig-aiagent && uv run pytest test/executor_engine_test.py -q`
Expected: PASS（全部通过）

- [ ] **Step 2: 修改 engine.py 构造与导入**

顶部导入：

```python
from .middleware import (
    BlockResult,
    MiddlewareRunner,
    StepContext,
    default_middlewares,
)
```

`__init__` 改为：

```python
    def __init__(
        self,
        dag: DAGDefinition,
        context: dict | None = None,
        middlewares=None,
    ):
        self.dag = dag
        self.context = context or {}
        self.step_results: dict[str, dict] = {}
        self.timeline: list[TimelineEntry] = []
        self._started_at = ""
        self.failed_steps: list = []
        self._runner = MiddlewareRunner(
            middlewares if middlewares is not None else default_middlewares()
        )
```

- [ ] **Step 3: 在 `_execute_step` 开头插入中间件前置钩子**

在 `_execute_step` 发出 `STEP_STARTED` 事件之后、`if step.execution_location == ExecutionLocation.CLIENT:` 之前插入：

```python
        ctx = StepContext(
            step=step,
            params=dict(step.params),
            inventory=inventory,
            session_id=self.context.get("session_id", ""),
            step_results=self.step_results,
            context=self.context,
            resolver=self._resolve_params,
            unresolved_checker=self._has_unresolved_refs,
            mcp_match=self._match_mcp_server,
            mcp_inject=self._inject_conn_params,
        )
        blocked = await self._runner.before_step(ctx)
        if blocked is not None:
            entry.status = "failed"
            entry.error = blocked.reason
            self.timeline.append(entry)
            self.step_results[step.step_id] = {
                "error": blocked.reason,
                "error_type": "unresolved_ref",
                "result": "",
            }
            logger.warning(
                f"[Engine] Step {step.step_id} 被中间件拦截: {blocked.reason}"
            )
            yield self._event(
                StreamEventType.STEP_FAILED,
                {
                    "step_id": step.step_id,
                    "error": blocked.reason,
                    "duration_ms": self._elapsed_ms_since(step_start),
                    "step": self._step_summary(step),
                },
            )
            return
        resolved_params = ctx.resolved_params
```

- [ ] **Step 4: 删除 client / server 路径中的内联参数逻辑**

**Client 路径**：把

```python
            client_params = self._inject_mcp_conn_params(step.params, step.capability)
            if self._has_unresolved_refs(client_params):
                err_msg = (...)
                ...
                return
```

整段替换为：

```python
            client_params = resolved_params
```

**Server 路径**：删除下列三段（已被中间件取代）：

```python
        resolved_params = self._resolve_params(step.params)
        logger.debug(f"[Engine] Step {step.step_id} 解析参数: {resolved_params}")

        if self._has_unresolved_refs(resolved_params):
            ... return

        if step.capability.startswith("mcp_"):
            matched_srv = self._match_mcp_server(step.capability)
            if matched_srv is not None:
                resolved_params = self._inject_conn_params(resolved_params, matched_srv)
```

保留其后的 `# 执行（带重试）` 段不变（`resolved_params` 已在 Step 3 中定义）。

- [ ] **Step 5: 在成功路径插入中间件后置钩子**

**Server 成功分支**：在 `self.step_results[step.step_id] = result` 之前插入：

```python
            ctx.result = result
            transformed = await self._runner.after_step(ctx)
            if transformed is not None:
                result = transformed
```

**Client 成功分支**：把

```python
                    result_data = delegate_result.get("result", {})
                    self.step_results[step.step_id] = result_data
```

改为：

```python
                    ctx.result = delegate_result.get("result", {}) or {}
                    transformed = await self._runner.after_step(ctx)
                    result_data = transformed if transformed is not None else ctx.result
                    self.step_results[step.step_id] = result_data
```

- [ ] **Step 6: 更新 `__init__.py` 导出**

```python
"""DAG 执行引擎 — 步骤执行 + SSE 事件流"""

from .engine import DAGExecutionEngine
from .handlers import CapabilityHandlers
from .middleware import (
    BlockResult,
    MiddlewareRunner,
    StepContext,
    StepMiddleware,
    default_middlewares,
)

__all__ = [
    "DAGExecutionEngine",
    "CapabilityHandlers",
    "BlockResult",
    "MiddlewareRunner",
    "StepContext",
    "StepMiddleware",
    "default_middlewares",
]
```

- [ ] **Step 7: 运行回归测试**

Run: `cd packages/guineapig-aiagent && uv run pytest test/executor_engine_test.py test/executor_middleware_test.py -q`
Expected: PASS（既有引擎测试全部通过，证明行为零回归）

- [ ] **Step 8: 提交**

```bash
git add packages/guineapig-aiagent/app/agent/executor/engine.py packages/guineapig-aiagent/app/agent/executor/__init__.py
git commit -m "refactor(aiagent): wire step middleware into engine (behavior-preserving)"
```

---

## Task 3: 中间件端到端测试（拦截 / 转换 / 观测）

**Files:**
- Test: `packages/guineapig-aiagent/test/executor_middleware_test.py`（追加）

**Interfaces:**
- Consumes: `DAGExecutionEngine(..., middlewares=[...])`

- [ ] **Step 1: 写测试**

追加：

```python
from app.agent.models import DAGDefinition, StreamEventType
from app.agent.executor.engine import DAGExecutionEngine


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
        steps=[DAGStep(step_id="s1", capability="rag", action="x", max_retries=0)],
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
```

- [ ] **Step 2: 运行测试**

Run: `cd packages/guineapig-aiagent && uv run pytest test/executor_middleware_test.py -q`
Expected: PASS（含新增 2 条）

- [ ] **Step 3: 提交**

```bash
git add packages/guineapig-aiagent/test/executor_middleware_test.py
git commit -m "test(aiagent): end-to-end middleware block/transform coverage"
```

---

## Task 4: 迁移「工具输出截断」为中间件（依赖《工具输出截断》计划）

**Files:**
- Modify: `packages/guineapig-aiagent/app/agent/executor/middleware.py`
- Modify: `packages/guineapig-aiagent/app/agent/executor/engine.py`（移除内联 `_truncate_result` 调用）
- Test: `packages/guineapig-aiagent/test/executor_middleware_test.py`（追加）

**Interfaces:**
- Consumes: `truncate_tool_result`、`settings.AGENT_TOOL_OUTPUT_*`
- Produces: `ToolOutputTruncationMiddleware`（在 `default_middlewares()` 末尾追加）

- [ ] **Step 1: 写失败测试**

追加：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/guineapig-aiagent && uv run pytest test/executor_middleware_test.py::test_truncation_middleware_in_default_chain -q`
Expected: FAIL（默认链未含截断中间件）

- [ ] **Step 3: 新增中间件并加入默认链**

在 `middleware.py` 追加：

```python
class ToolOutputTruncationMiddleware(StepMiddleware):
    """输出截断 — 防止单条超大结果撑爆后续 LLM 上下文。"""

    name = "tool_output_truncation"

    async def after_step(self, ctx: StepContext) -> Optional[dict]:
        from app.config import settings
        from .truncate import truncate_tool_result

        if ctx.result is None:
            return None
        return truncate_tool_result(
            ctx.result,
            ctx.step.capability,
            enabled=settings.AGENT_TOOL_OUTPUT_TRUNCATION_ENABLED,
            max_lines=settings.AGENT_TOOL_OUTPUT_MAX_LINES,
            max_bytes=settings.AGENT_TOOL_OUTPUT_MAX_BYTES,
        )
```

并把 `default_middlewares()` 改为：

```python
def default_middlewares() -> list[StepMiddleware]:
    return [
        ParamResolutionMiddleware(),
        McpConnectionMiddleware(),
        UnresolvedRefGuardMiddleware(),
        ToolOutputTruncationMiddleware(),
    ]
```

在 `engine.py` 中删除 Task（截断计划）加入的 `_truncate_result` 方法与两处调用（已由中间件统一处理）。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd packages/guineapig-aiagent && uv run pytest test/executor_middleware_test.py test/tool_output_truncation_test.py test/executor_engine_test.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add packages/guineapig-aiagent/app/agent/executor/middleware.py packages/guineapig-aiagent/app/agent/executor/engine.py packages/guineapig-aiagent/test/executor_middleware_test.py
git commit -m "refactor(aiagent): move tool output truncation into default middleware chain"
```

---

## Task 5: 暴露可拦截错误钩子（衔接「错误即消息」计划）

**Files:**
- Modify: `packages/guineapig-aiagent/app/agent/executor/engine.py`（失败路径调用 `on_step_error`）
- Test: `packages/guineapig-aiagent/test/executor_middleware_test.py`（追加）

**Interfaces:**
- Consumes: `MiddlewareRunner.on_step_error`
- Produces: 每次终态失败都会调用 `on_step_error(ctx)`（`ctx` 携带 `error`/`error_type`）

- [ ] **Step 1: 写失败测试**

追加：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/guineapig-aiagent && uv run pytest test/executor_middleware_test.py::test_on_step_error_observes_failure -q`
Expected: FAIL（`observed == []`）

- [ ] **Step 3: 在失败路径调用 `on_step_error`**

在 `_execute_step` 的 **server 失败分支**（追加 `step_results` 与 `logger.error` 之后）与 **client 失败分支**（`self.step_results[step.step_id] = {"error": err_msg}` 之后）各插入：

```python
            ctx.error = last_error
            ctx.error_type = last_error_type
            ctx.error_suggestion = last_error_suggestion
            await self._runner.on_step_error(ctx)
```

（client 分支用 `ctx.error = err_msg`、`ctx.error_type = "client_error"`。）

- [ ] **Step 4: 运行测试确认通过**

Run: `cd packages/guineapig-aiagent && uv run pytest test/executor_middleware_test.py test/executor_engine_test.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add packages/guineapig-aiagent/app/agent/executor/engine.py packages/guineapig-aiagent/test/executor_middleware_test.py
git commit -m "feat(aiagent): expose on_step_error middleware hook for failure observers"
```

---

## Self-Review

- **Spec coverage:** #6 内核+叠加 → Task 1/2（内核负责事件/重试/委托，叠加负责参数/连接/校验/截断）；#10 可拦截扩展点 → `before_step`（拦截）、`after_step`（转换）、`on_step_error`（观测）三钩子 + Task 3 端到端验证；可测试/可定制 → 自定义中间件注入测试。
- **Placeholder scan:** 无占位；middleware.py 全量给出，engine.py 以精确插入/删除位置 + 代码块描述。
- **Type consistency:** `StepContext` 字段在 middleware.py、engine 构造处、各测试一致；`BlockResult` / `StepMiddleware` 名称一致。
- **零回归保证:** Task 2 Step 7 以既有 `executor_engine_test.py` 为护栏；默认中间件顺序复现原"解析→注入→校验"语义。

## Open Questions

- [ ] `McpConnectionMiddleware` 对 client stdio 与 server remote 是否要区分注入字段？（当前统一注入，与原 `_inject_conn_params` 一致）
- [ ] 是否要把参数解析算法也移入中间件（当前复用引擎方法，未迁移）？
- [ ] 是否需要按请求动态装配中间件（如按用户/场景开关截断）？（当前构造期注入，已支持自定义 list）
