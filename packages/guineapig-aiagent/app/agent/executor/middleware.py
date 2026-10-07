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
    """为 MCP 步骤注入连接信息（URL/transport/headers/stdio 启动参数）。

    必须排在 ParamResolutionMiddleware 之后：它消费 ctx.resolved_params。
    """

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
            if ctx.step.execution_location == ExecutionLocation.CLIENT:
                reason = (
                    f"参数包含未解析的占位符，无法下发 client 执行: "
                    f"params={ctx.resolved_params}"
                )
            else:
                reason = (
                    f"参数包含未解析的占位符，无法执行: "
                    f"params={ctx.resolved_params}"
                )
            return BlockResult(block=True, reason=reason)
        return None


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


def default_middlewares() -> list[StepMiddleware]:
    """内核默认叠加层 — 复现重构前的参数解析/注入/校验行为。"""
    return [
        ParamResolutionMiddleware(),
        McpConnectionMiddleware(),
        UnresolvedRefGuardMiddleware(),
        ToolOutputTruncationMiddleware(),
    ]
