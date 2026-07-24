"""
ASR 原子能力 — 将音频文件发送到 ASR HTTP API 转为文本
"""

import os

import requests

from app.config import settings
from app.core.log import logger


def handle_asr(audio_path: str) -> str:
    """
    将音频文件发送到 ASR HTTP API，返回识别出的文本。

    Args:
        audio_path: 本地音频文件路径

    Returns:
        识别出的文本

    Raises:
        RuntimeError: ASR API 返回非 200 状态码
        FileNotFoundError: 音频文件不存在
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"ASR 输入音频文件不存在: {audio_path}")

    logger.info(f"[ASR] 请求: {settings.ASR_API_URL}, 文件: {audio_path}")

    with open(audio_path, "rb") as f:
        resp = requests.post(
            settings.ASR_API_URL,
            files={"file": (os.path.basename(audio_path), f, "audio/mpeg")},
        )

    if resp.status_code != 200:
        raise RuntimeError(f"ASR API 返回 {resp.status_code}: {resp.text}")

    data = resp.json()
    text = data.get("text", "")
    logger.info(f"[ASR] 识别结果: {text}")
    return text
