# app/routers/task.py

from fastapi import APIRouter

from app.core.log import logger
from app.schemas.task_models import TaskSubmitRequest
from app.services.task_service import handler_task_submit

router = APIRouter(prefix="/guineapig-aiagent/task", tags=["tasks"])


@router.post("/submit")
def submit_task(request: TaskSubmitRequest):
    """
    提交 ASR→LLM→TTS 处理任务

    请求参数:
        sessionId (str): 会话 ID
        taskId (str): 任务 ID
        requestId (str): 请求 ID
        its (int): 时间戳
        objectKey (str): S3 音频路径，格式 audio/asr/{user_id}/{date}/{filename}
    """
    logger.info(
        f"收到任务提交请求: taskId={request.taskId}, objectKey={request.objectKey}"
    )
    return handler_task_submit(request.model_dump())
