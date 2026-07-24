"""
可观测指标上报 — 通用接口，所有请求类型共享。

使用方法:
    await report_chat_metrics(
        user_id=user_id,
        session_id=session_id,
        request_count=1,
        agent_mode_count=...,
    )
"""

from app.core.log import logger
from app.services.otel_service import otel_service


async def report_chat_metrics(
    user_id: int,
    session_id: str = "",
    *,
    input_token: int = 0,
    output_token: int = 0,
    request_count: int = 1,
    **extra_metrics,
) -> None:
    """上报聊天指标（所有对话类型通用）。

    Args:
        user_id: 用户 ID
        session_id: 会话 ID，Backend 格式为 conv_{conversation_id}
        input_token: LLM 输入 token 数
        output_token: LLM 输出 token 数
        request_count: 请求计数（默认 1）
        **extra_metrics: 额外指标（agent_mode_count, web_search_count 等）
    """
    if user_id <= 0:
        return

    # 从 session_id 解析 conversation_id（Backend 格式: conv_{conversation_id}）
    conversation_id = 0
    if session_id.startswith("conv_"):
        parts = session_id.split("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            conversation_id = int(parts[1])

    try:
        await otel_service.report_metrics(
            user_id=user_id,
            conversation_id=conversation_id,
            input_token=input_token,
            output_token=output_token,
            request_count=request_count,
            **extra_metrics,
        )
    except Exception as e:
        logger.warning(f"[ReportMetrics] 指标上报异常: {e}")
