"""
ASR 独立服务 — 从 S3 下载音频后调用 ASR 原子能力
"""

import os

from app.config import settings
from app.core.log import logger
from app.core.oss_wrapper_utils import download_file_from_s3
from app.services.handle_asrservice import handle_asr


def handle_asr_task(object_key: str) -> str:
    """
    从 S3 下载音频文件，执行 ASR 识别，返回文本结果。

    Args:
        object_key: S3 对象键，格式 audio/asr/{user_id}/{date}/{filename}

    Returns:
        识别出的文本

    Raises:
        ValueError: objectKey 格式无效
        RuntimeError: ASR 识别失败
    """
    # 解析 objectKey 获取 user_id/date/filename
    # 格式: audio/asr/{user_id}/{date}/{filename}
    parts = object_key.split("/")
    if len(parts) < 4:
        raise ValueError(
            f"objectKey 格式无效: {object_key}，预期: audio/asr/{{user_id}}/{{date}}/{{filename}}"
        )

    user_id = parts[-3]
    date_str = parts[-2]
    filename = parts[-1]

    # 计算本地路径
    base_dir = settings.DATA_DIR
    local_asr_dir = os.path.join(base_dir, "asr", user_id, date_str)
    local_audio_path = os.path.join(local_asr_dir, filename)

    # Step 1: 下载音频
    os.makedirs(local_asr_dir, exist_ok=True)
    logger.info(f"[ASR Task] 从 S3 下载音频: {object_key}")
    success = download_file_from_s3(object_key, local_audio_path)
    if not success:
        raise RuntimeError(f"音频下载失败: {object_key}")

    # Step 2: ASR 识别
    logger.info(f"[ASR Task] 开始 ASR 识别: {local_audio_path}")
    text = handle_asr(local_audio_path)

    logger.info(f"[ASR Task] 识别完成: text={text}")
    return text
