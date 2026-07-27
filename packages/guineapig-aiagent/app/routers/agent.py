"""
Agent 入口路由 — 完整意图识别 Pipeline (Phase 0-3) + DAG 生成 + SSE 流式执行。

端点：
- POST /agent/chat          — 同步非流式，返回意图识别 + DAG 生成结果
- POST /agent/chat/stream   — SSE 流式，在 chat 的基础上执行 DAG 并流式推送进度

流程：
1. Phase 0: QuickFilter → trivial / simple / complex
2. Phase 1: IntentScanner → keyword-based candidates
3. Phase 2: DeepAnalyzer → LLM 深度分析
4. Phase 3: IntentDecision → 综合判定
5. DAG 生成: LLM 生成步骤计划
6. [仅 stream] DAG 执行引擎 → SSE 事件流
"""

import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel, Field

from app.config import settings
from app.core.log import logger
from app.schemas.base_models import success_response, error_response
from app.services.langfuse_client import get_langfuse, is_langfuse_enabled
from app.agent.models import (
    IntentDecisionResult,
    MCPToolInfo,
    QuickFilterResult,
    StreamEventType,
)
from app.agent.capability_registry import CapabilityRegistry
from app.agent.intent import QuickFilter, IntentScanner, DeepAnalyzer, IntentDecision
from app.agent.dag import DAGGenerator
from app.agent.executor import DAGExecutionEngine
from app.reporting.otel_metrics import report_chat_metrics
from langfuse import observe

# 惰性初始化的 LLM 客户端
_llm_client: OpenAI | None = None
_llm_model: str = "deepseek-chat"


def _get_llm_client() -> tuple[OpenAI, str]:
    global _llm_client, _llm_model
    if _llm_client is None:
        if not settings.LLM_API_KEY:
            raise ValueError("LLM_API_KEY not set")
        _llm_client = OpenAI(
            api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL
        )
        _llm_model = settings.LLM_MODEL_NAME
    return _llm_client, _llm_model


router = APIRouter(prefix="/guineapig-aiagent/agent", tags=["agent"])


_COMPACT_JSON = {"separators": (",", ":")}


def _json_compact(obj) -> str:
    """紧凑 JSON 序列化，移除 `: ` 后的多余空格和冗余的紧凑格式处理。"""
    return json.dumps(obj, ensure_ascii=False, **_COMPACT_JSON)


def _estimate_tokens(text: str) -> int:
    """
    估算文本的 token 数。

    中文字符 ~1 token / 1.5 字符，英文字符 ~1 token / 4 字符。
    避免引入 tiktoken 依赖，纯字符级估算。
    """
    if not text:
        return 0
    chinese = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other = len(text) - chinese
    return max(1, int(chinese / 1.5 + other / 4))


# ═══════════════════════════════════════════════════
# 请求 / 响应 模型
# ═══════════════════════════════════════════════════


class MCPToolSchema(BaseModel):
    """调用方传入的 MCP 工具信息"""

    server_name: str = Field(..., description="MCP server 名称")
    transport_type: str = Field(
        ..., description="传输协议: stdio | sse | streamable_http"
    )
    mcp_url: str = Field(
        "", description="MCP server URL（仅 sse/streamable_http 使用）"
    )
    headers: dict = Field(default_factory=dict, description="MCP 请求头")
    tools: list[dict] = Field(
        default_factory=list, description="工具列表，每项含 name/description"
    )


class AgentChatRequest(BaseModel):
    """Agent 聊天请求"""

    message: str = Field(..., description="用户消息")
    user_id: int = Field(0, description="用户 ID")
    session_id: str = Field("", description="会话 ID")
    conversation_history: list[dict] = Field(
        default_factory=list, description="对话历史（工作记忆）"
    )
    mcp_servers: list[MCPToolSchema] = Field(
        default_factory=list, description="已注册 MCP 服务"
    )
    skills: list[dict] = Field(default_factory=list, description="用户已开启的技能列表")
    rag_context: dict | None = Field(None, description="RAG 知识库配置（语言记忆）")
    scene_memory: list[dict] = Field(
        default_factory=list, description="场景记忆（chat_memory 摘要记录）"
    )


# ═══════════════════════════════════════════════════
# 共享 Pipeline（Phase 0-3 + DAG 生成）
# ═══════════════════════════════════════════════════


async def _run_intent_pipeline(request: AgentChatRequest) -> dict:
    """
    执行完整意图识别 Pipeline (Phase 0-3) + DAG 生成。
    集成 Langfuse Trace：整个 Pipeline 作为一条 Trace 追踪。

    Returns:
        dict 包含所有阶段的结果:
        - quick_result, candidates, deep_analysis, decision, dag, inventory,
          capabilities_formatted, mcp_tool_infos
    """
    message = request.message.strip()

    # Phase 0: 快速筛选
    quick_result = QuickFilter.classify(message, request.conversation_history)
    logger.info(f"[Agent] Phase 0 筛选结果: {quick_result}")

    # TRIVIAL: 提前返回，跳过 CapabilityRegistry.scan() 和后续所有阶段
    if quick_result == QuickFilterResult.TRIVIAL:
        return {
            "quick_result": quick_result,
            "candidates": [],
            "deep_analysis": None,
            "decision": IntentDecisionResult(
                action="fallback",
                primary_intent=None,
                candidates=[],
                confidence=1.0,
                reason="问候或简单应答，走普通对话",
            ),
            "dag": None,
            "inventory": None,
            "capabilities_formatted": "",
            "mcp_tool_infos": [],
            "pipeline_input_tokens": 0,
            "pipeline_output_tokens": 0,
        }

    # 扫描能力清单
    mcp_tool_infos = [
        MCPToolInfo(
            server_name=s.server_name,
            transport_type=s.transport_type,
            mcp_url=s.mcp_url,
            headers=s.headers,
            tools=s.tools,
        )
        for s in request.mcp_servers
    ]
    inventory = await CapabilityRegistry.scan(
        mcp_servers=mcp_tool_infos,
        skills=request.skills,
        rag_context=request.rag_context,
    )
    capabilities_formatted = CapabilityRegistry.format_for_llm(inventory)

    candidates: list = []
    deep_analysis = None
    decision = None
    dag = None
    pipeline_input_tokens = 0
    pipeline_output_tokens = 0

    # Phase 1: 关键词扫描（仅 simple）
    if quick_result == QuickFilterResult.SIMPLE:
        candidates = IntentScanner.scan(message)

    # Phase 2: LLM 深度分析
    needs_deep_analysis = (
        quick_result == QuickFilterResult.COMPLEX
        or (quick_result == QuickFilterResult.SIMPLE and not candidates)
        or (candidates and candidates[0].confidence < 0.5)
    )
    if needs_deep_analysis:
        logger.info(
            f"[Agent] 触发 Phase 2 LLM 深度分析: "
            f"complex={quick_result == QuickFilterResult.COMPLEX}, "
            f"candidates={len(candidates)}"
        )
        deep_analysis = DeepAnalyzer.analyze(
            user_message=message,
            capability_inventory=inventory,
            conversation_history=request.conversation_history,
            capabilities_formatted=capabilities_formatted,
        )
        # 估算 DeepAnalyzer LLM 调用 token
        analysis_input = capabilities_formatted + " " + message
        if request.conversation_history:
            for msg in request.conversation_history[-8:]:
                c = msg.get("content", "")
                if isinstance(c, list):
                    c = " ".join(p.get("text", "") for p in c if isinstance(p, dict))
                analysis_input += " " + str(c)
        pipeline_input_tokens += (
            _estimate_tokens(analysis_input) + 200
        )  # + system prompt
        if deep_analysis:
            pipeline_output_tokens += _estimate_tokens(
                json.dumps(deep_analysis.model_dump())
            )

    # Phase 3: 综合判定
    decision = IntentDecision.decide(
        quick_result=quick_result,
        candidates=candidates,
        deep_analysis=deep_analysis,
    )
    logger.info(
        f"[Agent] Phase 3 综合判定: action={decision.action}, "
        f"confidence={decision.confidence}"
    )

    # DAG 生成
    if decision.action == "proceed" and deep_analysis and deep_analysis.feasible:
        logger.info("[Agent] 触发 DAG 生成")
        dag = DAGGenerator.generate(
            deep_analysis=deep_analysis,
            capability_inventory=inventory,
            capabilities_formatted=capabilities_formatted,
        )
        # 估算 DAGGenerator LLM 调用 token
        dag_input = (
            capabilities_formatted + " " + json.dumps(deep_analysis.model_dump())
        )
        pipeline_input_tokens += _estimate_tokens(dag_input) + 250  # + system prompt
        if dag:
            pipeline_output_tokens += _estimate_tokens(json.dumps(dag.model_dump()))

    return {
        "quick_result": quick_result,
        "candidates": candidates,
        "deep_analysis": deep_analysis,
        "decision": decision,
        "dag": dag,
        "inventory": inventory,
        "capabilities_formatted": capabilities_formatted,
        "mcp_tool_infos": mcp_tool_infos,
        "pipeline_input_tokens": pipeline_input_tokens,
        "pipeline_output_tokens": pipeline_output_tokens,
    }


def _build_phase_response(
    pipeline_result: dict,
) -> dict:
    """将 Pipeline 结果构建为标准 JSON 响应 data"""
    quick_result = pipeline_result["quick_result"]
    candidates = pipeline_result["candidates"]
    deep_analysis = pipeline_result["deep_analysis"]
    decision = pipeline_result["decision"]
    dag = pipeline_result["dag"]
    inventory = pipeline_result["inventory"]
    capabilities_formatted = pipeline_result["capabilities_formatted"]

    if quick_result == QuickFilterResult.TRIVIAL:
        return {
            "action": "fallback_to_chat",
            "quick_filter": quick_result.value,
            "reason": "问候或简单应答，走普通对话",
            "candidates": [],
            "deep_analysis": None,
            "decision": None,
            "dag": None,
            "capabilities": {},
        }

    return {
        "action": decision.action,
        "quick_filter": quick_result.value,
        "reason": decision.reason,
        "candidates": [c.model_dump() for c in candidates],
        "deep_analysis": deep_analysis.model_dump() if deep_analysis else None,
        "decision": {
            "action": decision.action,
            "confidence": decision.confidence,
            "reason": decision.reason,
        },
        "dag": dag.model_dump() if dag else None,
        "capabilities": {
            "available": [c.name for c in inventory.capabilities if c.enabled],
            "formatted": capabilities_formatted,
        },
    }


async def _stream_execution_summary(
    user_message: str,
    step_results: dict[str, dict],
    dag_original_intent: str = "",
    user_id: int = 0,
    session_id: str = "",
    scene_memory: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """
    DAG 执行完成后，调用 LLM 生成自然语言总结，以 content SSE 事件流式输出。

    Yields:
        格式化的 SSE content 事件字符串
    """
    try:
        client, model_name = _get_llm_client()
    except ValueError as e:
        logger.warning(f"[Agent-Summary] LLM 不可用: {e}")
        return

    # 构建结果描述
    results_desc = []
    for step_id, result in step_results.items():
        result_str = json.dumps(result, ensure_ascii=False, indent=2)[:1000]
        results_desc.append(f"步骤 {step_id}:\n{result_str}")

    scene_text = _build_scene_memory_text(scene_memory or [])
    system_prompt = (
        "你是一个 AI 助手。用户请求你执行了一个任务，以下是任务的执行结果。\n"
        "请根据执行结果，用自然语言向用户总结完成了什么，结果是什么。\n"
        "语言与用户消息一致，简洁清晰。\n"
        "如果结果中有错误，如实告知用户。"
        "\n回答要求：紧凑排版，不要有多余空行和空格。使用 markdown 格式但避免不必要的空白字符。"
        + scene_text
    )

    human_prompt = (
        f"用户消息: {user_message}\n\n"
        f"任务描述: {dag_original_intent or user_message}\n\n"
        f"执行结果:\n" + "\n".join(results_desc) + "\n\n"
        "请根据以上执行结果，生成对用户的回复。"
    )

    summary_input = system_prompt + human_prompt
    input_tokens = _estimate_tokens(summary_input)
    output_text = ""

    # ── Langfuse Generation Span (SDK v4: start_observation) ──
    langfuse_gen = None
    if is_langfuse_enabled():
        langfuse = get_langfuse()
        langfuse_gen = langfuse.start_observation(
            name="stream-execution-summary",
            as_type="generation",
            model=model_name,
            input={"system": system_prompt[:200], "user": human_prompt[:500]},
            metadata={"source": "agent._stream_execution_summary"},
        )

    try:
        stream = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": human_prompt},
            ],
            temperature=0.3,
            max_tokens=2048,
            stream=True,
        )

        for chunk in stream:
            if (
                chunk.choices
                and chunk.choices[0].delta
                and chunk.choices[0].delta.content
            ):
                content = chunk.choices[0].delta.content
                output_text += content
                data = _json_compact({"content": content})
                yield f"event: content\ndata: {data}\n\n"
    except Exception as e:
        logger.error(f"[Agent-Summary] LLM 流式调用失败: {e}")
    finally:
        if langfuse_gen:
            langfuse_gen.update(output=output_text)
            langfuse_gen.end()

    # 上报总结 LLM 的 token 指标
    output_tokens = _estimate_tokens(output_text)
    if user_id > 0:
        await report_chat_metrics(
            user_id=user_id,
            session_id=session_id,
            input_token=input_tokens,
            output_token=output_tokens,
            request_count=0,  # 不计为新请求
        )


def _build_scene_memory_text(scene_memory: list[dict]) -> str:
    """将场景记忆列表格式化为 system prompt 文本"""
    if not scene_memory:
        return ""
    lines = ["\n\n## 关于用户的重要记忆"]
    for mem in scene_memory:
        mem_type = mem.get("type", "unknown")
        content = mem.get("content", "")
        if content:
            lines.append(f"- [{mem_type}] {content}")
    return "\n".join(lines)


async def _direct_llm_stream(
    user_message: str,
    user_id: int = 0,
    session_id: str = "",
    extra_input_tokens: int = 0,
    extra_output_tokens: int = 0,
    scene_memory: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """无需 DAG 执行时，直接调用 LLM 流式回复并输出 SSE 事件。

    内部计数 token 数并在流结束后上报指标。

    Args:
        extra_input_tokens: 管道中此前 LLM 调用（如 DeepAnalyzer）消耗的额外输入 token
        extra_output_tokens: 管道中此前 LLM 调用产生的额外输出 token
        scene_memory: 场景记忆列表，注入 system prompt
    """
    input_tokens = _estimate_tokens(user_message) + extra_input_tokens
    output_text = ""

    # 构建系统提示词（包含场景记忆）
    scene_text = _build_scene_memory_text(scene_memory or [])
    system_prompt = "你是一个友好的 AI 助手。" + scene_text

    try:
        client, model_name = _get_llm_client()
    except ValueError as e:
        logger.warning(f"[Agent-LLM] LLM 不可用: {e}")
        yield f"event: error\ndata: {_json_compact({'message': 'LLM 不可用'})}\n\n"
        yield f"event: execution_complete\ndata: {_json_compact({'status': 'failed', 'reason': 'LLM 不可用'})}\n\n"
        if user_id > 0:
            await report_chat_metrics(
                user_id=user_id,
                session_id=session_id,
                input_token=input_tokens,
                output_token=0,
            )
        return

    # ── Langfuse Generation Span (流式) ──
    langfuse_gen = None
    if is_langfuse_enabled():
        langfuse = get_langfuse()
        langfuse_gen = langfuse.start_observation(
            name="direct-llm-stream",
            as_type="generation",
            model=model_name,
            input={"system": system_prompt[:200], "user": user_message[:500]},
            metadata={"source": "agent._direct_llm_stream"},
        )

    try:
        stream = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
            max_tokens=2048,
            stream=True,
        )
        for chunk in stream:
            if (
                chunk.choices
                and chunk.choices[0].delta
                and chunk.choices[0].delta.content
            ):
                content = chunk.choices[0].delta.content
                output_text += content
                data = _json_compact({"content": content})
                yield f"event: content\ndata: {data}\n\n"
    except Exception as e:
        logger.error(f"[Agent-LLM] 直接回复流式调用失败: {e}")
        error_data = _json_compact({"message": f"LLM 调用失败: {e}"})
        yield f"event: error\ndata: {error_data}\n\n"
    finally:
        if langfuse_gen:
            langfuse_gen.update(output=output_text)
            langfuse_gen.end()

    # 流结束后上报指标（不在 finally 中，避免 GeneratorExit 时 yield 异常）
    output_tokens = _estimate_tokens(output_text)
    complete_data = _json_compact(
        {"status": "completed", "summary": {"steps_completed": 0, "steps_total": 0}}
    )
    yield f"event: execution_complete\ndata: {complete_data}\n\n"

    if user_id > 0:
        await report_chat_metrics(
            user_id=user_id,
            session_id=session_id,
            input_token=input_tokens,
            output_token=output_tokens + extra_output_tokens,
        )


# ═══════════════════════════════════════════════════
# 端点 1: 同步非流式
# ═══════════════════════════════════════════════════


@router.post("/chat")
@observe(name="agent_chat")
async def agent_chat(request: AgentChatRequest):
    """
    Agent 非流式入口 — 返回意图识别 + DAG 生成的结构化 JSON。
    """
    try:
        message = request.message.strip()
        if not message:
            return error_response(message="消息不能为空", code=400)

        logger.info(
            f"[Agent] POST /chat: user_id={request.user_id}, "
            f"message='{message[:50]}...'"
        )

        pipeline_result = await _run_intent_pipeline(request)
        response_data = _build_phase_response(pipeline_result)

        await report_chat_metrics(
            user_id=request.user_id,
            session_id=request.session_id,
            input_token=pipeline_result.get("pipeline_input_tokens", 0),
            output_token=pipeline_result.get("pipeline_output_tokens", 0),
        )
        return success_response(data=response_data)

    except ValueError as e:
        logger.error(f"[Agent] 请求参数错误: {e}")
        return error_response(message=str(e), code=400)
    except Exception as e:
        logger.error(f"[Agent] 处理异常: {e}")
        return error_response(message=f"处理失败: {str(e)}", code=500)


# ═══════════════════════════════════════════════════
# 端点 2: SSE 流式（含 DAG 执行）
# ═══════════════════════════════════════════════════


@router.post("/chat/stream")
@observe(name="agent_chat_stream")
async def agent_chat_stream(request: AgentChatRequest):
    """
    Agent SSE 流式入口 — 执行完整 Pipeline 并流式推送执行进度。

    如果任务需要客户端执行（cli/skill/mcp_stdio），
    流中会发送 step_awaiting_client 事件，由 backend 转发给 client。
    Client 执行完成后通过 WebSocket 回传结果，继续后续步骤。

    SSE 事件类型:
    - plan_ready: DAG 计划就绪
    - step_started: 步骤开始
    - step_completed: 步骤完成
    - step_failed: 步骤失败
    - step_awaiting_client: 等待客户端执行
    - awaiting_confirmation: 等待用户确认
    - execution_complete: 全部完成
    - error: 致命错误
    - log: 日志消息
    """
    try:
        message = request.message.strip()
        if not message:
            return error_response(message="消息不能为空", code=400)

        logger.info(
            f"[Agent] POST /chat/stream: user_id={request.user_id}, "
            f"message='{message[:50]}...'"
        )

        # ── Phase 0-3: 意图识别 + DAG 生成 ──
        pipeline_result = await _run_intent_pipeline(request)
        quick_result = pipeline_result["quick_result"]
        decision = pipeline_result["decision"]
        dag = pipeline_result["dag"]
        inventory = pipeline_result["inventory"]
        deep_analysis = pipeline_result.get("deep_analysis")

        # Trivial → SSE LLM 流式回复（跳过 DAG 执行）
        if quick_result == QuickFilterResult.TRIVIAL:
            return StreamingResponse(
                _direct_llm_stream(
                    message,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    scene_memory=request.scene_memory,
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # reject → SSE 流式返回 LLM 拒绝说明
        if decision.action == "reject":
            logger.info(f"[Agent] 任务被拒绝: {decision.reason}")

            reject_input = f"用户消息: {message}\n\n无法执行原因: {decision.reason}"
            reject_input_tokens = _estimate_tokens(reject_input)

            async def reject_event_stream():
                output_text = ""

                # 1. rejected 事件（通知前端关闭 HITL）
                rejected_data = _json_compact(
                    {"reason": decision.reason or "无法执行此任务", "original_intent": message}
                )
                yield f"event: rejected\ndata: {rejected_data}\n\n"

                # 2. LLM 生成自然语言拒绝说明
                langfuse_gen = None
                if is_langfuse_enabled():
                    langfuse = get_langfuse()
                    langfuse_gen = langfuse.start_observation(
                        name="reject-llm-stream",
                        as_type="generation",
                        model=model_name,
                        input={"reject_reason": decision.reason, "user_message": message},
                        metadata={"source": "agent.reject_event_stream"},
                    )
                try:
                    client, model_name = _get_llm_client()
                    stream = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {
                                "role": "system",
                                "content": "你是一个 AI 助手。用户请求你执行一项任务，但你无法完成。请用自然语言、友好的语气告诉用户为什么无法执行。回答紧凑简洁，不要有多余空行和空格。",
                            },
                            {"role": "user", "content": reject_input},
                        ],
                        temperature=0.3,
                        max_tokens=512,
                        stream=True,
                    )
                    for chunk in stream:
                        if (
                            chunk.choices
                            and chunk.choices[0].delta
                            and chunk.choices[0].delta.content
                        ):
                            content = chunk.choices[0].delta.content
                            output_text += content
                            data = _json_compact({"content": content})
                            yield f"event: content\ndata: {data}\n\n"
                except Exception as e:
                    logger.warning(f"[Agent] Reject LLM 失败: {e}")
                    fallback = f"抱歉，我无法执行此任务。{decision.reason}"
                    output_text = fallback
                    data = _json_compact({"content": fallback})
                    yield f"event: content\ndata: {data}\n\n"
                finally:
                    if langfuse_gen:
                        langfuse_gen.update(output=output_text)
                        langfuse_gen.end()

                # 3. execution_complete
                complete_data = _json_compact(
                    {"status": "rejected", "reason": decision.reason, "summary": {"original_intent": message, "steps_completed": 0, "steps_total": 0}}
                )
                yield f"event: execution_complete\ndata: {complete_data}\n\n"

                # 4. 上报指标
                output_tokens = _estimate_tokens(output_text)
                await report_chat_metrics(
                    user_id=request.user_id,
                    session_id=request.session_id,
                    input_token=reject_input_tokens
                    + pipeline_result.get("pipeline_input_tokens", 0),
                    output_token=output_tokens
                    + pipeline_result.get("pipeline_output_tokens", 0),
                )

            return StreamingResponse(
                reject_event_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # fallback/clarify → SSE LLM 流式回复（无 DAG 可执行）
        if decision.action != "proceed":
            return StreamingResponse(
                _direct_llm_stream(
                    message,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    extra_input_tokens=pipeline_result.get("pipeline_input_tokens", 0),
                    extra_output_tokens=pipeline_result.get(
                        "pipeline_output_tokens", 0
                    ),
                    scene_memory=request.scene_memory,
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # proceed 但 DAG 为空（生成/验证失败）→ SSE 流通知客户端，同时 LLM 生成回复
        if not dag or not dag.steps:
            logger.warning(
                f"[Agent-Stream] DAG 为空但仍收到 proceed: "
                f"message='{message[:60]}', "
                f"intent={deep_analysis.intent_type if deep_analysis else 'unknown'}"
            )

            async def dag_empty_stream():
                output_text = ""
                dag_input_tokens = pipeline_result.get("pipeline_input_tokens", 0)
                dag_output_tokens = pipeline_result.get("pipeline_output_tokens", 0)
                llm_input_tokens = 0

                # 1. log 事件（告知客户端 DAG 为空但不视为错误，后续有 LLM 回复）
                log_data = _json_compact(
                    {"message": "无法生成执行计划，将由 LLM 直接回复", "original_intent": message}
                )
                yield f"event: log\ndata: {log_data}\n\n"

                # 2. LLM 生成自然语言回复（让用户得到有意义的回应而不是空内容）
                scene_text = _build_scene_memory_text(request.scene_memory)
                system_prompt = (
                    "你是一个 AI 助手。用户请求你执行一项任务，但系统无法为这个请求生成自动化的执行计划。请用自然语言、友好的语气给用户一个简单的回应，说明你无法自动执行这个请求，但仍然可以提供一般性的帮助或信息。保持回答紧凑简洁，不要有多余空行和空格。"
                    + scene_text
                )

                langfuse_gen = None
                if is_langfuse_enabled():
                    langfuse = get_langfuse()
                    langfuse_gen = langfuse.start_observation(
                        name="dag-empty-llm-stream",
                        as_type="generation",
                        model=model_name,
                        input={"system": system_prompt[:200], "user_message": message},
                        metadata={"source": "agent.dag_empty_stream"},
                    )
                try:
                    client, model_name = _get_llm_client()
                    llm_input_tokens = _estimate_tokens(message)
                    stream = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": message},
                        ],
                        temperature=0.3,
                        max_tokens=1024,
                        stream=True,
                    )
                    for chunk in stream:
                        if (
                            chunk.choices
                            and chunk.choices[0].delta
                            and chunk.choices[0].delta.content
                        ):
                            content = chunk.choices[0].delta.content
                            output_text += content
                            data = _json_compact({"content": content})
                            yield f"event: content\ndata: {data}\n\n"
                except Exception as e:
                    logger.warning(f"[Agent-Stream] DAG-empty LLM 流式调用失败: {e}")
                    # LLM 不可用时，用固定文案兜底
                    fallback = "抱歉，我无法为你的请求生成自动化执行计划，但我可以尝试以普通对话方式回答你的问题。请重发一次消息，取消 Agent 模式即可。"
                    output_text = fallback
                    data = _json_compact({"content": fallback})
                    yield f"event: content\ndata: {data}\n\n"
                finally:
                    if langfuse_gen:
                        langfuse_gen.update(output=output_text)
                        langfuse_gen.end()

                # 3. execution_complete
                complete_data = _json_compact(
                    {"status": "dag_generation_failed", "reason": "DAG 计划生成失败（可能请求的能力不可用）", "total_steps": 0, "completed_steps": 0, "summary": {"original_intent": message, "steps_completed": 0, "steps_total": 0}}
                )
                yield f"event: execution_complete\ndata: {complete_data}\n\n"

                # 4. 上报指标（包含 LLM 回复 token）
                output_tokens = _estimate_tokens(output_text)
                await report_chat_metrics(
                    user_id=request.user_id,
                    session_id=request.session_id,
                    input_token=dag_input_tokens + llm_input_tokens,
                    output_token=output_tokens + dag_output_tokens,
                )

            return StreamingResponse(
                dag_empty_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # ── SSE 流式执行 ──
        session_id = (
            request.session_id or f"conv_{request.user_id}_{uuid.uuid4().hex[:8]}"
        )
        context = {
            "user_id": request.user_id,
            "session_id": session_id,
            "mcp_servers": pipeline_result["mcp_tool_infos"],
            "pipeline_input_tokens": pipeline_result.get("pipeline_input_tokens", 0),
            "pipeline_output_tokens": pipeline_result.get("pipeline_output_tokens", 0),
        }

        engine = DAGExecutionEngine(dag=dag, context=context)

        async def event_stream():
            try:
                execution_status = None
                async for event in engine.execute(
                    inventory=inventory,
                    session_id=session_id,
                    wait_for_confirmation=True,
                ):
                    if event.event == StreamEventType.EXECUTION_COMPLETE.value:
                        execution_status = event.data.get("status")
                    yield f"event: {event.event}\ndata: {_json_compact(event.data)}\n\n"

                # ── 执行完成后，用 LLM 生成自然语言总结回复 ──
                if execution_status and execution_status.startswith("completed"):
                    logger.info("[Agent-Stream] DAG 执行完成，生成回复总结")
                    async for content_chunk in _stream_execution_summary(
                        user_message=message,
                        step_results=engine.step_results,
                        dag_original_intent=dag.original_intent,
                        user_id=request.user_id,
                        session_id=session_id,
                        scene_memory=request.scene_memory,
                    ):
                        yield content_chunk
            except Exception as e:
                logger.error(f"[Agent-Stream] 执行异常: {e}")
                error_data = _json_compact(
                    {"message": f"执行异常: {e}"}
                )
                yield f"event: error\ndata: {error_data}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except ValueError as e:
        logger.error(f"[Agent] 请求参数错误: {e}")
        return error_response(message=str(e), code=400)
    except Exception as e:
        logger.error(f"[Agent] 处理异常: {e}")
        return error_response(message=f"处理失败: {str(e)}", code=500)
