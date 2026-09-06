"""
DAG 执行引擎 — 拓扑排序 → 数据流解析 → 逐步执行 → SSE 事件流。

工作方式：
1. 接收 DAGDefinition + CapabilityInventory + 执行上下文
2. 拓扑排序确定执行顺序
3. 逐步执行每个步骤，通过 handlers 调用对应能力
4. 每一步都产出 StreamEvent（SSE 友好）
5. 支持重试、降级、并行（相同深度的独立步骤）
"""

import asyncio
import re
from datetime import datetime, timezone
from typing import AsyncGenerator

from app.core.log import logger
from app.services.otel_service import otel_service

from ..models import (
    CapabilityInventory,
    DAGDefinition,
    DAGStep,
    ExecutionLocation,
    StreamEvent,
    StreamEventType,
    TimelineEntry,
    TimelineLog,
)
from .handlers import CapabilityHandlers
from ..event_manager import AgentEventManager


class DAGExecutionEngine:
    """DAG 执行引擎 — 步骤编排 + 事件流"""

    # 参数引用模式: {{step_id.output_key}} 或 {{step_id.output}}
    PARAM_REF_PATTERN = re.compile(r"\{\{(\w+)\.(\w+)\}\}")

    def __init__(self, dag: DAGDefinition, context: dict | None = None):
        """
        Args:
            dag: 待执行的 DAG
            context: 执行上下文（包含 user_id, session_id, 会话历史等）
        """
        self.dag = dag
        self.context = context or {}
        self.step_results: dict[str, dict] = {}  # step_id → execution result
        self.timeline: list[TimelineEntry] = []
        self._started_at = ""

    # ── 公共接口 ──

    async def execute(
        self,
        inventory: CapabilityInventory | None = None,
        session_id: str = "",
        wait_for_confirmation: bool = False,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        执行 DAG，逐个步骤产出 SSE 事件。

        Args:
            inventory: 当前能力清单（可选）
            session_id: 会话 ID，用于事件管理器的 session 追踪
            wait_for_confirmation: 是否等待用户确认后才开始执行。
                                  只有 True 时 executor 才会 yield
                                  AWAITING_CONFIRMATION 并阻塞等待。

        Yields:
            StreamEvent 事件
        """
        self._started_at = datetime.now(timezone.utc).isoformat()

        # 注册 session 到 EventManager（启用确认等待机制）
        if session_id:
            await AgentEventManager.register_session(session_id)

        # 1. 空 DAG 检查
        if not self.dag.steps:
            yield self._event(
                StreamEventType.ERROR,
                {
                    "message": "DAG 没有可执行的步骤",
                    "original_intent": self.dag.original_intent,
                },
            )
            if session_id:
                await AgentEventManager.cleanup(session_id)
            return

        # 2. 拓扑排序
        sorted_steps = self._topological_sort()
        if sorted_steps is None:
            yield self._event(
                StreamEventType.ERROR,
                {
                    "message": "DAG 存在循环依赖，无法执行",
                    "original_intent": self.dag.original_intent,
                },
            )
            yield self._event(
                StreamEventType.EXECUTION_COMPLETE,
                {
                    "status": "failed",
                    "reason": "循环依赖",
                    "total_steps": len(self.dag.steps),
                    "completed_steps": 0,
                },
            )
            if session_id:
                await AgentEventManager.cleanup(session_id)
            return

        # 3. 通知计划就绪 + 等待用户确认
        logger.info(f"[Engine] 发出 plan_ready 事件: {len(sorted_steps)} 个步骤")
        yield self._event(
            StreamEventType.PLAN_READY,
            {
                "original_intent": self.dag.original_intent,
                "total_steps": len(sorted_steps),
                "steps": [self._step_summary(s) for s in sorted_steps],
            },
        )

        if session_id:
            yield self._event(
                StreamEventType.AWAITING_CONFIRMATION,
                {
                    "original_intent": self.dag.original_intent,
                    "total_steps": len(sorted_steps),
                    "steps": [self._step_summary(s) for s in sorted_steps],
                },
            )

        if wait_for_confirmation:
            confirmed = await AgentEventManager.wait_for_confirmation(session_id)
            if not confirmed:
                yield self._event(
                    StreamEventType.EXECUTION_COMPLETE,
                    {
                        "status": "cancelled",
                        "reason": "用户取消或超时",
                        "total_steps": len(sorted_steps),
                        "completed_steps": 0,
                        "duration_ms": self._elapsed_ms(),
                    },
                )
                if session_id:
                    await AgentEventManager.cleanup(session_id)
                return

        # 4. 按拓扑顺序逐个执行
        completed = 0
        failed = False

        for step in sorted_steps:
            # 检查前置步骤是否全部完成
            if not self._dependencies_resolved(step):
                yield self._event(
                    StreamEventType.STEP_FAILED,
                    {
                        "step_id": step.step_id,
                        "error": "前置步骤未完成或已失败",
                        "step": self._step_summary(step),
                    },
                )
                failed = True
                break

            # 执行单个步骤
            async for event in self._execute_step(step, inventory):
                yield event
                if event.event == StreamEventType.STEP_FAILED.value:
                    # 检查是否要执行降级
                    step_result = self.step_results.get(step.step_id, {})
                    if step.fallback_action and step_result.get("error"):
                        logger.info(
                            f"[Engine] Step {step.step_id} failed, "
                            f"executing fallback: {step.fallback_action}"
                        )
                        async for fallback_event in self._execute_fallback(
                            step, step.fallback_action
                        ):
                            yield fallback_event

                    # 非致命失败—继续下一步骤
                    # 由调用方（SSE handler）决定是否终止

            completed += 1

        # 5. 执行完成
        total_duration = self._elapsed_ms()
        yield self._event(
            StreamEventType.EXECUTION_COMPLETE,
            {
                "status": "completed" if not failed else "completed_with_errors",
                "total_steps": len(sorted_steps),
                "completed_steps": completed,
                "duration_ms": total_duration,
                "timeline": [t.model_dump() for t in self.timeline],
                "summary": {
                    "original_intent": self.dag.original_intent,
                    "steps_completed": completed,
                    "steps_total": len(sorted_steps),
                    "duration_ms": total_duration,
                },
            },
        )

        # ── 上报可观察指标 ──
        try:
            user_id = self.context.get("user_id", 0)
            conversation_id = self._parse_conversation_id()

            # 统计各能力类型的使用次数
            web_search_count = 0
            rag_count = 0
            agent_mode_count = 0
            mcp_count = 0
            for step in self.dag.steps:
                cap = step.capability
                if cap == "web_search":
                    web_search_count += 1
                elif cap == "rag":
                    rag_count += 1
                elif cap.startswith("mcp_"):
                    mcp_count += 1

            # Agent 模式计为包含 mcp 或 web_search 或 rag 的复杂请求
            if web_search_count > 0 or rag_count > 0 or mcp_count > 0:
                agent_mode_count = 1

            await otel_service.report_metrics(
                user_id=user_id,
                conversation_id=conversation_id,
                request_count=1,
                input_token=self.context.get("pipeline_input_tokens", 0),
                output_token=self.context.get("pipeline_output_tokens", 0),
                agent_mode_count=agent_mode_count,
                web_search_count=web_search_count,
                rag_count=rag_count,
            )
        except Exception as e:
            logger.warning(f"[Engine] 指标上报异常: {e}")

        # 清理 session
        if session_id:
            await AgentEventManager.cleanup(session_id)

    # ── 步骤执行 ──

    async def _execute_step(
        self,
        step: DAGStep,
        inventory: CapabilityInventory | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """执行单个步骤"""
        step_start = datetime.now(timezone.utc).isoformat()
        entry = TimelineEntry(
            step_id=step.step_id,
            capability=step.capability,
            status="running",
            started_at=step_start,
            params=step.params,
        )

        # 通知步骤开始
        yield self._event(
            StreamEventType.STEP_STARTED,
            {
                "step_id": step.step_id,
                "capability": step.capability,
                "action": step.action,
                "step": self._step_summary(step),
            },
        )

        # Client 端能力 → 等待客户端执行
        if step.execution_location == ExecutionLocation.CLIENT:
            yield self._event(
                StreamEventType.STEP_AWAITING_CLIENT,
                {
                    "step_id": step.step_id,
                    "capability": step.capability,
                    "action": step.action,
                    "params": step.params,
                },
            )

            entry.status = "awaiting_client"
            self.timeline.append(entry)

            # 有 session_id 时等待 delegate 结果
            session_id = self.context.get("session_id", "")
            if session_id:
                logger.info(
                    f"[Engine] 等待 client delegate 结果: "
                    f"session={session_id}, step={step.step_id}"
                )
                delegate_result = await AgentEventManager.wait_for_delegate(
                    session_id, step.step_id
                )

                step_end = datetime.now(timezone.utc).isoformat()
                if delegate_result and not delegate_result.get("error"):
                    # 成功
                    result_data = delegate_result.get("result", {})
                    self.step_results[step.step_id] = result_data
                    entry.status = "completed"
                    entry.completed_at = step_end
                    entry.duration_ms = self._elapsed_ms_since(step_start)
                    entry.result_summary = self._summarize_result(result_data)
                    self.timeline = [
                        t if t.step_id != step.step_id else entry for t in self.timeline
                    ]

                    yield self._event(
                        StreamEventType.STEP_COMPLETED,
                        {
                            "step_id": step.step_id,
                            "result_summary": entry.result_summary,
                            "duration_ms": entry.duration_ms,
                            "output_key": step.output_key,
                        },
                    )

                    if step.output_key:
                        yield self._event(
                            StreamEventType.LOG,
                            {
                                "step_id": step.step_id,
                                "level": "info",
                                "message": f"输出 '{step.output_key}' 可供后续步骤引用",
                            },
                        )
                else:
                    # 失败或取消
                    err_msg = (
                        delegate_result.get("error", "")
                        if delegate_result
                        else "delegate 执行未返回结果"
                    )
                    entry.status = "failed"
                    entry.completed_at = step_end
                    entry.duration_ms = self._elapsed_ms_since(step_start)
                    entry.error = err_msg
                    self.timeline = [
                        t if t.step_id != step.step_id else entry for t in self.timeline
                    ]

                    logger.error(
                        f"[Engine] Client step {step.step_id} failed: {err_msg}"
                    )
                    yield self._event(
                        StreamEventType.STEP_FAILED,
                        {
                            "step_id": step.step_id,
                            "error": err_msg,
                            "duration_ms": entry.duration_ms,
                            "step": self._step_summary(step),
                        },
                    )

                    # 保存错误结果以便依赖检查
                    self.step_results[step.step_id] = {"error": err_msg}
            return

        # 解析参数中的引用
        resolved_params = self._resolve_params(step.params)

        # 对 MCP 步骤，从 context 注入连接信息（URL、transport_type、headers）
        if step.capability.startswith("mcp_"):
            matched_srv = self._match_mcp_server(step.capability)
            if matched_srv is not None:
                if isinstance(matched_srv, dict):
                    resolved_params.setdefault("mcp_url", matched_srv.get("mcp_url", ""))
                    resolved_params.setdefault(
                        "transport_type", matched_srv.get("transport_type", "")
                    )
                    resolved_params.setdefault("headers", matched_srv.get("headers", {}))
                else:
                    resolved_params.setdefault(
                        "mcp_url", getattr(matched_srv, "mcp_url", "")
                    )
                    resolved_params.setdefault(
                        "transport_type", getattr(matched_srv, "transport_type", "")
                    )
                    resolved_params.setdefault(
                        "headers", getattr(matched_srv, "headers", {})
                    )

        # 执行（带重试）
        result = None
        last_error = ""
        for attempt in range(max(1, step.max_retries + 1)):
            if attempt > 0:
                logger.info(
                    f"[Engine] Retry step {step.step_id} "
                    f"(attempt {attempt + 1}/{step.max_retries + 1})"
                )
                yield self._event(
                    StreamEventType.LOG,
                    {
                        "step_id": step.step_id,
                        "level": "warning",
                        "message": f"重试第 {attempt + 1} 次",
                    },
                )
                entry.logs.append(
                    TimelineLog(
                        ts=datetime.now(timezone.utc).isoformat(),
                        level="warning",
                        msg=f"重试第 {attempt + 1} 次",
                    )
                )

            try:
                result = await asyncio.wait_for(
                    CapabilityHandlers.execute(step.capability, resolved_params),
                    timeout=step.timeout_seconds,
                )
                if "error" in result:
                    last_error = result["error"]
                    continue  # 重试
                last_error = ""
                break  # 成功
            except asyncio.TimeoutError:
                last_error = f"执行超时 ({step.timeout_seconds}s)"
                continue
            except Exception as e:
                last_error = f"执行异常: {e}"
                continue

        step_end = datetime.now(timezone.utc).isoformat()

        if result and "error" not in result:
            # 成功
            self.step_results[step.step_id] = result
            entry.status = "completed"
            entry.completed_at = step_end
            entry.duration_ms = self._elapsed_ms_since(step_start)
            entry.result_summary = self._summarize_result(result)
            self.timeline.append(entry)

            yield self._event(
                StreamEventType.STEP_COMPLETED,
                {
                    "step_id": step.step_id,
                    "result_summary": entry.result_summary,
                    "duration_ms": entry.duration_ms,
                    "output_key": step.output_key,
                },
            )

            # 如果有 output_key，通知输出数据可用
            if step.output_key:
                yield self._event(
                    StreamEventType.LOG,
                    {
                        "step_id": step.step_id,
                        "level": "info",
                        "message": f"输出 '{step.output_key}' 可供后续步骤引用",
                    },
                )
        else:
            # 失败
            entry.status = "failed"
            entry.completed_at = step_end
            entry.duration_ms = self._elapsed_ms_since(step_start)
            entry.error = last_error
            self.timeline.append(entry)

            logger.error(f"[Engine] Step {step.step_id} failed: {last_error}")
            yield self._event(
                StreamEventType.STEP_FAILED,
                {
                    "step_id": step.step_id,
                    "error": last_error,
                    "duration_ms": entry.duration_ms,
                    "step": self._step_summary(step),
                },
            )

    async def _execute_fallback(
        self, failed_step: DAGStep, fallback_action: str
    ) -> AsyncGenerator[StreamEvent, None]:
        """执行降级操作"""
        logger.info(
            f"[Engine] Executing fallback for {failed_step.step_id}: {fallback_action}"
        )

        yield self._event(
            StreamEventType.LOG,
            {
                "step_id": failed_step.step_id,
                "level": "info",
                "message": f"执行降级操作: {fallback_action}",
            },
        )

        # 降级：如果 fallback_action 是 "skip" 则跳过
        if fallback_action == "skip":
            self.step_results[failed_step.step_id] = {
                "result": "(已跳过)",
                "fallback": True,
            }
            return

    # ── 拓扑排序 ──

    def _topological_sort(self) -> list[DAGStep] | None:
        """Kahn 拓扑排序"""
        step_map = {s.step_id: s for s in self.dag.steps}

        # 入度
        indegree: dict[str, int] = {s.step_id: 0 for s in self.dag.steps}
        for s in self.dag.steps:
            indegree[s.step_id] = len(s.depends_on)

        # 反向邻接表: 依赖 dep_id 的步骤列表
        dependents: dict[str, list[str]] = {s.step_id: [] for s in self.dag.steps}
        for s in self.dag.steps:
            for dep_id in s.depends_on:
                if dep_id in dependents:
                    dependents[dep_id].append(s.step_id)

        queue = [sid for sid, deg in indegree.items() if deg == 0]
        sorted_ids = []

        while queue:
            # 相同深度的步骤可以并行，按顺序出队
            sid = queue.pop(0)
            sorted_ids.append(sid)
            for dependent in dependents.get(sid, []):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    queue.append(dependent)

        if len(sorted_ids) != len(self.dag.steps):
            return None  # 存在循环

        return [step_map[sid] for sid in sorted_ids]

    def _dependencies_resolved(self, step: DAGStep) -> bool:
        """检查步骤的所有前置依赖是否已完成"""
        for dep_id in step.depends_on:
            if dep_id not in self.step_results:
                return False
            result = self.step_results[dep_id]
            if "error" in result:
                return False
        return True

    # ── 数据流 ──

    def _match_mcp_server(self, capability: str):
        """将 MCP 步骤 capability 定位到对应的 MCP server。

        LLM 生成的 capability 可能是 ``mcp_{server}``（如 ``mcp_amap``）或带工具后缀的
        ``mcp_{server}_{tool}``（如 ``mcp_amap_maps_weather``）。这里按
        ``mcp_{server_name}`` 前缀做最长前缀匹配，命中后由调用方注入 URL/transport/headers，
        避免臆造的 tool 后缀导致 MCP URL 匹配失败。
        """
        mcp_servers: list = self.context.get("mcp_servers", [])
        matched_srv = None
        matched_len = -1
        for srv in mcp_servers:
            if isinstance(srv, dict):
                srv_name = srv.get("server_name", "")
            else:
                srv_name = getattr(srv, "server_name", "")
            if not srv_name:
                continue
            prefix = "mcp_" + srv_name
            if capability.startswith(prefix) and len(prefix) > matched_len:
                matched_srv = srv
                matched_len = len(prefix)
        return matched_srv

    def _resolve_params(self, params: dict) -> dict:
        """解析参数中的 {{step_id.output_key}} 引用"""
        resolved = dict(params)

        for key, value in resolved.items():
            if isinstance(value, str):
                resolved[key] = self._resolve_string(value)
            elif isinstance(value, dict):
                resolved[key] = self._resolve_params(value)
            elif isinstance(value, list):
                resolved[key] = [
                    self._resolve_string(v) if isinstance(v, str) else v for v in value
                ]

        return resolved

    def _resolve_string(self, text: str) -> str:
        """替换字符串中的 {{step_id.key}} 引用"""

        def _replacer(m: re.Match) -> str:
            step_id = m.group(1)
            key = m.group(2)
            if step_id in self.step_results:
                result = self.step_results[step_id]
                return str(result.get(key, result.get("result", m.group(0))))
            return m.group(0)  # 保留原样

        return self.PARAM_REF_PATTERN.sub(_replacer, text)

    # ── 辅助方法 ──

    @staticmethod
    def _event(event_type: StreamEventType, data: dict) -> StreamEvent:
        """创建 StreamEvent"""
        return StreamEvent(
            event=event_type.value,
            data=data,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _step_summary(step: DAGStep) -> dict:
        """步骤的摘要信息"""
        return {
            "step_id": step.step_id,
            "capability": step.capability,
            "action": step.action,
            "execution_location": step.execution_location.value,
            "requires_confirmation": step.requires_confirmation,
            "depends_on": step.depends_on,
        }

    @staticmethod
    def _summarize_result(result: dict) -> str:
        """从执行结果中提取摘要"""
        if "result" in result:
            text = str(result["result"])
            if len(text) > 200:
                return text[:200] + "..."
            return text
        if "error" in result:
            return f"错误: {result['error']}"
        return str(result)[:200]

    @staticmethod
    def _elapsed_ms_since(start_iso: str) -> int:
        """计算从 start_iso 到现在的毫秒数"""
        try:
            start = datetime.fromisoformat(start_iso)
            now = datetime.now(timezone.utc)
            return int((now - start).total_seconds() * 1000)
        except Exception as e:
            logger.warning(f"[Engine] 解析 start_iso 失败，返回 0: {start_iso} ({e})")
            return 0

    def _elapsed_ms(self) -> int:
        """计算从引擎启动到现在的毫秒数"""
        if not self._started_at:
            return 0
        return self._elapsed_ms_since(self._started_at)

    def _parse_conversation_id(self) -> int:
        """从 context 的 session_id 解析 conversation_id。

        Backend 传的 session_id 格式: conv_{conversation_id}
        例如: conv_123 → 返回 123
        """
        session_id_str = self.context.get("session_id", "")
        if not session_id_str.startswith("conv_"):
            return 0
        parts = session_id_str.split("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            return int(parts[1])
        return 0
