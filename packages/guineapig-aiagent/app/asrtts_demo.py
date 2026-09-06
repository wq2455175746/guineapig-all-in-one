"""
ASR -> LLM -> TTS Demo Pipeline (HTTP API 版本)

核心流程:
  a) 从 S3 下载音频到本地（如本地不存在）
  b) ASR (HTTP API) 将音频转为文本
  c) LLM (DeepSeek) 处理文本并返回回复
  d) TTS (HTTP API) 将 LLM 回复转为 Raw 音频，再用 ffmpeg 转 MP3
  e) 上传 MP3 到 S3

使用方法:
  python -m app.asrtts_demo

依赖:
  - requests, subprocess (ffmpeg)
  - openai (DeepSeek API)
  - boto3 (S3)
"""

import os
import subprocess
import sys

from dotenv import load_dotenv
import requests

# 确保项目根目录在 sys.path 中
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 显式加载 .env 文件到环境变量，使 os.getenv() 能读取到
load_dotenv(os.path.join(_project_root, ".env"))

from openai import OpenAI

from app.core.log import logger
from app.core.oss_wrapper_utils import get_oss_client, upload_doc_to_s3_and_get_path,download_file_from_s3

# ============================================================================
# 配置参数 — 可按需修改
# ============================================================================
USER_ID = "1000000001"
DATE = "20260525"  # YYYYMMDD

# 本地数据目录 (项目根/data)
BASE_DIR = os.path.join(_project_root, "data")
LOCAL_ASR_DIR = os.path.join(BASE_DIR, "asr", USER_ID, DATE)
LOCAL_TTS_DIR = os.path.join(BASE_DIR, "tts", USER_ID, DATE)

# S3 路径
S3_ASR_KEY = f"audio/asr/{USER_ID}/{DATE}/audio.mp3"
S3_TTS_KEY = f"audio/tts/{USER_ID}/{DATE}/output.mp3"

# TTS zero-shot 参考音频 (本地路径)
LOCAL_PROMPT_WAV = os.path.join(_project_root, "asset", "zero_shot_prompt.wav")
S3_PROMPT_KEY = "audio/tts/prompt/prompt.wav"
PROMPT_TEXT = "希望你以后能够做的比我还好哟"

# ASR HTTP API
ASR_API_URL = "http://localhost:9991/v1/audio/transcriptions"

# TTS HTTP API
TTS_API_URL = "http://localhost:9992/inference_zero_shot"

# ============================================================================
# LLM 客户端 (惰性加载)
# ============================================================================
_llm_client = None
_model_name = None


def _get_llm_client():
    global _llm_client, _model_name
    if _llm_client is None:
        api_key = os.getenv("LLM_API_KEY", "")
        base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
        _model_name = os.getenv("LLM_MODEL_NAME", "deepseek-chat")
        if not api_key:
            raise ValueError("API_KEY not set in .env")
        _llm_client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)
        logger.info(f"LLM client ready: model={_model_name}")
    return _llm_client, _model_name


# ============================================================================
# Pipeline 各步骤
# ============================================================================

def step1_download_audio():
    """
    检查本地 data/asr/{user_id}/{date}/ 是否有 audio.mp3，
    如果没有则从 S3 下载。
    """
    os.makedirs(LOCAL_ASR_DIR, exist_ok=True)
    local_path = os.path.join(LOCAL_ASR_DIR, "audio.mp3")

    if os.path.exists(local_path):
        logger.info(f"[Step 1] 音频已存在本地: {local_path}")
        return local_path

    logger.info(f"[Step 1] 从 S3 下载: {S3_ASR_KEY}")
    download_file_from_s3(S3_ASR_KEY, LOCAL_ASR_DIR)
    logger.info(f"[Step 1] 下载完成: {local_path}")
    return local_path


def step2_asr(audio_path: str) -> str:
    """
    使用 ASR HTTP API 将音频文件转为文本，保存 asr_result.txt。
    返回解析出的文本。
    """
    logger.info(f"[Step 2] ASR 请求: {ASR_API_URL}")

    with open(audio_path, "rb") as f:
        resp = requests.post(
            ASR_API_URL,
            files={"file": (os.path.basename(audio_path), f, "audio/mpeg")},
            timeout=(5, 60),
        )

    if resp.status_code != 200:
        raise RuntimeError(f"ASR API 返回 {resp.status_code}: {resp.text}")

    data = resp.json()
    text = data.get("text", "")

    # 保存结果
    result_path = os.path.join(LOCAL_ASR_DIR, "asr_result.txt")
    with open(result_path, "w", encoding="utf-8") as f:
        f.write(text)
    logger.info(f"[Step 2] ASR 结果已保存: {result_path}")
    logger.info(f"[Step 2] 识别文本: {text}")
    return text


def step3_llm(text: str) -> str:
    """
    将 ASR 文本发给 DeepSeek，返回回复文本，保存 llm_response.txt。
    """
    logger.info("[Step 3] LLM 处理中...")
    client, model_name = _get_llm_client()

    messages = [
        {"role": "system", "content": "你是一个有用的语音助手。"},
        {
            "role": "user",
            "content": (
                "你的回复将会用 TTS 模型转为中文语音，请把回答控制在 100 字以内。"
                "标点符号仅包含逗号和句号，将数字转为文字回答。"
                "请用自然的口语化方式回答。"
            ),
        },
        {"role": "assistant", "content": "好的，我会用口语化的方式回答，控制在 100 字以内。"},
    ]

    completion = client.chat.completions.create(
        model=model_name,
        messages=messages + [{"role": "user", "content": text}],
    )
    response_text = completion.choices[0].message.content

    # 保存结果
    os.makedirs(LOCAL_TTS_DIR, exist_ok=True)
    response_path = os.path.join(LOCAL_TTS_DIR, "llm_response.txt")
    with open(response_path, "w", encoding="utf-8") as f:
        f.write(response_text)
    logger.info(f"[Step 3] LLM 回复已保存: {response_path}")
    logger.info(f"[Step 3] 回复文本: {response_text}")
    return response_text


def step4_tts(text: str) -> str:
    """
    使用 TTS HTTP API (zero-shot) 将文本转为语音。
    返回 MP3 文件路径。
    """
    logger.info(f"[Step 4] TTS 请求: {TTS_API_URL}")

    # 确保参考音频存在
    prompt_dir = os.path.dirname(LOCAL_PROMPT_WAV)
    os.makedirs(prompt_dir, exist_ok=True)

    if not os.path.exists(LOCAL_PROMPT_WAV):
        logger.info(f"[Step 4] 参考音频不存在，尝试从 S3 下载...")
        try:
            get_oss_client().download_oss(S3_PROMPT_KEY, prompt_dir)
            logger.info(f"[Step 4] 参考音频已下载: {LOCAL_PROMPT_WAV}")
        except Exception:
            logger.error(f"[Step 4] 无法获取参考音频!")
            logger.error(f"  请将参考 WAV 上传至 S3: {S3_PROMPT_KEY}")
            logger.error(f"  或直接放入: {LOCAL_PROMPT_WAV}")
            raise FileNotFoundError(
                f"TTS 参考音频缺失。请放置于: {LOCAL_PROMPT_WAV}"
            )

    # 调用 TTS HTTP API
    with open(LOCAL_PROMPT_WAV, "rb") as f:
        resp = requests.post(
            TTS_API_URL,
            files={
                "tts_text": (None, text),
                "prompt_text": (None, PROMPT_TEXT),
                "prompt_wav": ("prompt.wav", f, "audio/wav"),
            },
            timeout=(5, 60),
        )

    if resp.status_code != 200:
        raise RuntimeError(f"TTS API 返回 {resp.status_code}: {resp.text}")

    # 保存 Raw 音频
    os.makedirs(LOCAL_TTS_DIR, exist_ok=True)
    raw_path = os.path.join(LOCAL_TTS_DIR, "speech.raw")
    with open(raw_path, "wb") as f:
        f.write(resp.content)
    logger.info(f"[Step 4] Raw 音频已保存: {raw_path}")

    # ffmpeg 转 MP3
    mp3_path = os.path.join(LOCAL_TTS_DIR, "output.mp3")
    cmd = [
        "ffmpeg", "-y",
        "-f", "s16le",
        "-ar", "16000",
        "-ac", "1",
        "-i", raw_path,
        mp3_path,
    ]
    logger.info(f"[Step 4] ffmpeg 转换: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"[Step 4] ffmpeg 失败: {result.stderr}")
        raise RuntimeError(f"ffmpeg 转换失败: {result.stderr}")

    logger.info(f"[Step 4] MP3 已保存: {mp3_path}")
    return mp3_path


def step5_upload_tts(audio_path: str) -> str:
    """
    将 TTS 生成的音频文件上传到 S3。
    """
    logger.info("[Step 5] 上传到 S3...")

    filename = os.path.basename(audio_path)
    remote_path = upload_doc_to_s3_and_get_path(
        file_obj_or_path=audio_path,
        project_id="audio/tts",
        file_path=f"{USER_ID}/{DATE}",
        filename=filename,
    )
    logger.info(f"[Step 5] 上传成功: {remote_path}")
    return remote_path


# ============================================================================
# 主入口
# ============================================================================

def run_pipeline():
    """执行完整 ASR → LLM → TTS 管线"""
    logger.info("=" * 60)
    logger.info("  ASR → LLM → TTS Demo Pipeline (HTTP API)")
    logger.info(f"  USER_ID={USER_ID}  DATE={DATE}")
    logger.info("=" * 60)

    # Step 1: 下载音频
    audio_path = step1_download_audio()

    # Step 2: ASR 识别 (HTTP API)
    asr_text = step2_asr(audio_path)

    # Step 3: LLM 处理
    llm_response = step3_llm(asr_text)

    # Step 4: TTS 合成 (HTTP API + ffmpeg)
    tts_audio_path = step4_tts(llm_response)

    # Step 5: 上传到 S3
    s3_path = step5_upload_tts(tts_audio_path)

    logger.info("=" * 60)
    logger.info("  管线执行完成!")
    logger.info(f"  ASR 输入  : {audio_path}")
    logger.info(f"  ASR 文本  : {asr_text}")
    logger.info(f"  LLM 回复  : {llm_response}")
    logger.info(f"  TTS 输出  : {tts_audio_path}")
    logger.info(f"  S3  路径  : {s3_path}")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_pipeline()
