"""
任务编排服务 — 编排 ASR→LLM→TTS 完整管线
"""

import os
import traceback

from fastapi.responses import JSONResponse

from app.config import settings
from app.core.log import logger
from app.core.oss_wrapper_utils import download_file_from_s3
from app.schemas.base_models import success_response, error_response
from app.schemas.task_models import TaskSubmitResponse
from app.services.handle_asrservice import handle_asr
from app.services.handle_llmservice import get_llm_response
from app.services.handle_ttsservice import handle_tts, upload_tts_result


def handler_task_submit(request: dict) -> JSONResponse:
    """
    处理 ASR→LLM→TTS 任务提交。

    Args:
        request: 请求字典，包含 sessionId, taskId, requestId, its, objectKey

    Returns:
        JSONResponse: 成功或失败响应（通过 success_response / error_response 构建）
    """
    try:
        task_id = request.get("taskId", "")
        request_id = request.get("requestId", "")
        its = request.get("its", 0)
        object_key = request.get("objectKey", "")

        if not object_key:
            return error_response(message="objectKey 不能为空", code=400)

        logger.info(f"[Task] 开始处理任务: taskId={task_id}, objectKey={object_key}")

        # 解析 objectKey 获取 user_id/date/filename
        # 格式: audio/asr/{user_id}/{date}/{filename}
        parts = object_key.split("/")
        if len(parts) < 4:
            return error_response(
                message=f"objectKey 格式无效: {object_key}，预期: audio/asr/{{user_id}}/{{date}}/{{filename}}",
                code=400,
            )
        # objectKey = "audio/asr/1000000001/202600521/audio.mp3"
        # parts = ["audio", "asr", "1000000001", "202600521", "audio.mp3"]
        user_id = parts[-3]
        date_str = parts[-2]
        filename = parts[-1]

        # 计算本地路径
        base_dir = settings.DATA_DIR
        local_asr_dir = os.path.join(base_dir, "asr", user_id, date_str)
        local_tts_dir = os.path.join(base_dir, "tts", user_id, date_str)
        local_audio_path = os.path.join(local_asr_dir, filename)

        # Step 1: 下载音频
        os.makedirs(local_asr_dir, exist_ok=True)
        if not os.path.exists(local_audio_path):
            logger.info(f"[Task] Step 1: 从 S3 下载音频: {object_key}")
            if not download_file_from_s3(object_key, local_audio_path):
                return error_response(message=f"音频下载失败: {object_key}", code=500)
        else:
            logger.info(f"[Task] Step 1: 音频已存在本地: {local_audio_path}")

        # Step 2: ASR
        logger.info("[Task] Step 2: ASR 识别")
        asr_text = handle_asr(local_audio_path)

        # Step 3: LLM
        logger.info("[Task] Step 3: LLM 处理")
        llm_response = get_llm_response(asr_text)

        # Step 4: TTS — 确保参考音频存在
        logger.info("[Task] Step 4: TTS 合成")
        prompt_dir = os.path.dirname(settings.PROMPT_WAV_PATH)
        os.makedirs(prompt_dir, exist_ok=True)
        if not os.path.exists(settings.PROMPT_WAV_PATH):
            logger.info(f"[Task] 参考音频不存在，从 S3 下载: {settings.S3_PROMPT_KEY}")
            download_file_from_s3(settings.S3_PROMPT_KEY, settings.PROMPT_WAV_PATH)

        tts_mp3_path = handle_tts(llm_response, local_tts_dir, settings.PROMPT_WAV_PATH)

        # Step 5: 上传 TTS 结果到 S3
        logger.info("[Task] Step 5: 上传 TTS 结果")
        result_uri = upload_tts_result(tts_mp3_path, user_id, date_str)

        # 构建响应
        resp_data = TaskSubmitResponse(
            sessionId=request.get("sessionId", ""),
            taskId=task_id,
            requestId=request_id,
            its=its,
            objectKey=result_uri,
        )

        logger.info(f"[Task] 任务完成: {resp_data.model_dump()}")
        return success_response(data=resp_data.model_dump())

    except Exception as e:
        logger.error(f"[Task] 任务处理失败: {e}\n{traceback.format_exc()}")
        return error_response(message=str(e), code=500)
