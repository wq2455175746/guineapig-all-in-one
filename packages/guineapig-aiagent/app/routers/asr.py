# app/routers/asr.py

from fastapi import APIRouter

from app.core.log import logger
from app.schemas.asr_models import AsrRequest, AsrResponse
from app.schemas.base_models import success_response, error_response
from app.services.handle_asr_task import handle_asr_task

router = APIRouter(prefix="/guineapig-aiagent/asr", tags=["asr"])


@router.post("/transcribe")
def transcribe_audio(request: AsrRequest):
    """
    传入 S3 音频文件路径，执行 ASR 识别并返回文本。

    请求参数:
        objectKey (str): S3 音频路径，格式 audio/asr/{user_id}/{date}/{filename}
    """
    logger.info(f"收到 ASR 识别请求: objectKey={request.objectKey}")

    try:
        text = handle_asr_task(request.objectKey)
        resp_data = AsrResponse(text=text)
        return success_response(data=resp_data.model_dump())
    except Exception as e:
        logger.error(f"ASR 识别失败: {e}")
        return error_response(message=str(e), code=500)
