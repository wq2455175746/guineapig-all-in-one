"""
Agent 控制信号 HTTP 端点 — 接收 backend 转发的确认/取消/委托结果。

后端 (Go) 收到 client 的 WS 控制消息后，通过 HTTP POST 调用这些端点，
由 EventManager 设置异步事件解除 executor 的阻塞等待。

端点：
- POST /agent/chat/confirm          — 用户确认执行计划
- POST /agent/chat/cancel           — 用户取消执行
- POST /agent/chat/delegate-result  — 客户端回传 delegate 执行结果
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.log import logger
from app.agent.event_manager import AgentEventManager

router = APIRouter(prefix="/guineapig-aiagent/agent", tags=["agent_control"])


# ═══════════════════════════════════════════
# 请求模型
# ═══════════════════════════════════════════


class AgentSessionRequest(BaseModel):
    """带 session_id 的基础控制请求"""
    session_id: str = Field(..., description="会话 ID（如 conv_123）")


class AgentDelegateResultRequest(AgentSessionRequest):
    """delegate 结果回传请求"""
    step_id: str = Field(..., description="步骤 ID")
    capability: str = Field("", description="能力名称")
    result: dict = Field(default_factory=dict, description="执行结果")
    error: str = Field("", description="错误信息")


# ═══════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════


@router.post("/chat/confirm")
async def agent_confirm(request: AgentSessionRequest):
    """
    用户确认执行计划。

    Backend 收到 client 的 chat.agent_confirm WS 消息后，
    调用此端点通知 EventManager 解除 executor 的确认等待。
    """
    session_id = request.session_id
    logger.info(f"[AgentControl] 确认执行: session={session_id}")
    await AgentEventManager.confirm(session_id)
    return {"success": True, "session_id": session_id}


@router.post("/chat/cancel")
async def agent_cancel(request: AgentSessionRequest):
    """
    用户取消执行。

    Backend 收到 client 的 chat.agent_cancel WS 消息后，
    调用此端点通知 EventManager 终止执行。
    """
    session_id = request.session_id
    logger.info(f"[AgentControl] 取消执行: session={session_id}")
    await AgentEventManager.cancel(session_id)
    return {"success": True, "session_id": session_id}


@router.post("/chat/delegate-result")
async def agent_delegate_result(request: AgentDelegateResultRequest):
    """
    客户端回传 delegate 执行结果。

    Backend 收到 client 的 chat.agent_delegate_result WS 消息后，
    调用此端点将结果投递给 EventManager，解除 executor 的 delegate 等待。
    """
    session_id = request.session_id
    step_id = request.step_id
    logger.info(
        f"[AgentControl] 收到 delegate 结果: "
        f"session={session_id}, step={step_id}, "
        f"error={request.error[:50] if request.error else 'none'}"
    )

    result = {
        "result": request.result,
        "error": request.error,
    }
    success = await AgentEventManager.deliver_delegate(
        session_id, step_id, result
    )

    return {
        "success": success,
        "session_id": session_id,
        "step_id": step_id,
    }
