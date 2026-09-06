"""
TTS 原子能力 — 将文本发送到 TTS HTTP API 合成语音，转为 MP3 并上传 S3
"""

import os
import subprocess

import requests

from app.config import settings
from app.core.log import logger
from app.core.oss_wrapper_utils import upload_doc_to_s3_and_get_path


def handle_tts(text: str, tts_dir: str, prompt_wav: str) -> str:
    """
    将文本发送到 TTS HTTP API，合成语音并转为 MP3。

    Args:
        text: 要合成的文本（LLM 回复）
        tts_dir: TTS 输出目录
        prompt_wav: Zero-shot 参考音频路径

    Returns:
        MP3 文件路径

    Raises:
        RuntimeError: TTS API 或 ffmpeg 转换失败
    """
    # 确保参考音频存在
    if not os.path.exists(prompt_wav):
        raise FileNotFoundError(f"TTS 参考音频不存在: {prompt_wav}")

    logger.info(f"[TTS] 请求: {settings.TTS_API_URL}")

    # 调用 TTS HTTP API
    with open(prompt_wav, "rb") as f:
        resp = requests.post(
            settings.TTS_API_URL,
            files={
                "tts_text": (None, text),
                "prompt_text": (None, settings.TTS_PROMPT_TEXT),
                "prompt_wav": ("prompt.wav", f, "audio/wav"),
            },
            timeout=(5, 60),
        )

    if resp.status_code != 200:
        raise RuntimeError(f"TTS API 返回 {resp.status_code}: {resp.text}")

    # 保存 Raw 音频
    os.makedirs(tts_dir, exist_ok=True)
    raw_path = os.path.join(tts_dir, "speech.raw")
    with open(raw_path, "wb") as f:
        f.write(resp.content)
    logger.info(f"[TTS] Raw 音频已保存: {raw_path}")

    # ffmpeg 转 MP3
    mp3_path = os.path.join(tts_dir, "output.mp3")
    cmd = [
        "ffmpeg", "-y",
        "-f", "s16le",
        "-ar", "16000",
        "-ac", "1",
        "-i", raw_path,
        mp3_path,
    ]
    logger.info(f"[TTS] ffmpeg 转换: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"[TTS] ffmpeg 失败: {result.stderr}")
        raise RuntimeError(f"ffmpeg 转换失败: {result.stderr}")

    logger.info(f"[TTS] MP3 已保存: {mp3_path}")
    return mp3_path


def upload_tts_result(mp3_path: str, user_id: str, date: str) -> str:
    """
    将 TTS 生成的结果 MP3 上传到 S3。

    Args:
        mp3_path: 本地 MP3 文件路径
        user_id: 用户 ID
        date: 日期字符串

    Returns:
        S3 远程路径
    """
    logger.info(f"[TTS] 上传到 S3: {mp3_path}")
    remote_path = upload_doc_to_s3_and_get_path(
        file_obj_or_path=mp3_path,
        project_id="audio/tts",
        file_path=f"{user_id}/{date}",
        filename=os.path.basename(mp3_path),
    )
    logger.info(f"[TTS] 上传成功: {remote_path}")
    return remote_path
