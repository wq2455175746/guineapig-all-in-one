"""记忆归纳路由"""

from fastapi import APIRouter

from app.core.log import logger
from app.schemas.base_models import success_response, error_response
from app.schemas.memory_models import MemorySummarizeRequest
from app.services.memory_summarize_service import process_memory_summarize

router = APIRouter(prefix="/guineapig-aiagent/memory", tags=["memory"])


@router.post("/summarize")
def summarize_memory(request: MemorySummarizeRequest):
    """
    记忆归纳 — 使用 LLM 将对话归纳为结构化记忆。
    由 guineapig-backend 异步调用。
    """
    logger.info(f"[Memory] 收到记忆归纳请求: memory_id={request.memory_id}")

    try:
        result = process_memory_summarize(request)
        return success_response(data=result)
    except ValueError as e:
        logger.error(f"[Memory] 参数错误: {e}")
        return error_response(message=str(e), code=400)
    except Exception as e:
        logger.error(f"[Memory] 处理异常: {e}")
        return error_response(message=f"处理失败: {str(e)}", code=500)
