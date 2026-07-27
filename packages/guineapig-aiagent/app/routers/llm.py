"""
LLM 流式 SSE 端点 — 使用 Pipeline 模式按序执行预处理器后调用 LLM 流式接口。
"""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.log import logger
from app.reporting.otel_metrics import report_chat_metrics
from app.schemas.llm_models import LLMStreamRequest
from app.services.langfuse_client import get_langfuse, is_langfuse_enabled
from langfuse import observe
from app.services.llm_pipeline import (
    Pipeline,
    PipelineContext,
    SkillSelectionProcessor,
    SkillContextProcessor,
    NetworkSearchProcessor,
    RAGRetrievalProcessor,
    DefaultSkillInjector,
    LLMStreamProcessor,
    CommandParsingProcessor,
)

router = APIRouter(prefix="/guineapig-aiagent/llm", tags=["llm"])

# 全局 Pipeline — Processors 均为无状态，可复用
_pipeline = Pipeline([
    SkillSelectionProcessor(),
    SkillContextProcessor(),
    NetworkSearchProcessor(),
    RAGRetrievalProcessor(),
    DefaultSkillInjector(),
    LLMStreamProcessor(),
    CommandParsingProcessor(),
])


def _estimate_tokens(text: str) -> int:
    """估算文本的 token 数。"""
    if not text:
        return 0
    chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other = len(text) - chinese
    return max(1, int(chinese / 1.5 + other / 4))


async def _stream_with_metrics(ctx: PipelineContext, session_id: str):
    """包装 Pipeline 流，结束后上报指标（含 token 计数）。"""
    # 统计输入 token：所有消息内容
    input_text = ""
    for msg in ctx.messages:
        content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
        if isinstance(content, list):
            content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
        input_text += str(content)
    input_tokens = _estimate_tokens(input_text)

    output_text = ""
    try:
        async for event in _pipeline.run_and_yield(ctx):
            yield event
            # 尝试从 SSE 事件中提取 content 文本用于计数
            if event.startswith("data: "):
                try:
                    payload = json.loads(event[6:].strip())
                    content = payload.get("content", "")
                    if content:
                        output_text += content
                except (json.JSONDecodeError, IndexError):
                    pass
    finally:
        output_tokens = _estimate_tokens(output_text)
        await report_chat_metrics(
            user_id=ctx.user_id or 0,
            session_id=session_id,
            input_token=input_tokens,
            output_token=output_tokens,
        )


@router.post("/chat/stream")
@observe(name="llm_chat_stream")
async def chat_stream(request: LLMStreamRequest):
    """
    SSE 流式 LLM 接口。

    接收完整消息上下文 + 可选模型参数，返回 SSE 流式内容块。
    每个事件格式: data: {"content":"..."}\n\n
    结束信号: data: {"done":true, "commands":[...]}\n\n
    """
    api_key = request.api_key
    base_url = request.base_url
    model_name = request.model

    if not api_key:
        logger.error("[LLM-Stream] api_key 为空")
        return StreamingResponse(
            iter([f"data: {json.dumps({'error': 'api_key is required'})}\n\n"]),
            media_type="text/event-stream",
        )

    if not model_name:
        logger.error("[LLM-Stream] model_name 为空")
        return StreamingResponse(
            iter([f"data: {json.dumps({'error': 'model is required'})}\n\n"]),
            media_type="text/event-stream",
        )

    logger.info(f"[LLM-Stream] 开始流式请求: model={model_name}, messages={len(request.messages)}")

    rag_context = None
    if request.rag_context is not None:
        rag_context = request.rag_context.model_dump()

    ctx = PipelineContext(
        messages=request.messages,
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
        temperature=request.temperature or 0.7,
        max_tokens=request.max_tokens or 2048,
        skills=request.skills,
        user_id=request.user_id,
        web_search_enabled=request.web_search_enabled,
        rag_context=rag_context,
    )

    return StreamingResponse(
        _stream_with_metrics(ctx, session_id=request.session_id or ""),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
