import os
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置，支持环境变量和.env文件"""

    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 1

    # 基础配置
    ENV: str = "prod"
    DEBUG: bool = False
    DOCS_ENABLED: bool = False
    PROJ_LOG_LEVEL: str = "INFO"
    SYNC_THREAD_COUNT: int | None = None
    # 安全配置
    SECRET_KEY: str = "your-secret-key-change-in-production"
    CORS_ORIGINS: List[str] = ["*"]

    # OSS对象存储配置
    OSS_AK: str = "xxxx"
    OSS_SK: str = "xxxx"
    OSS_ENDPOINT: str = "http://localhost:29000"
    OSS_BUCKET: str = "guineapig"
    OSS_IS_ADDRESSING_STYLE: bool = False

    # API配置
    API_V1_STR: str = "/api/v1"

    # ASR HTTP API 配置
    ASR_API_URL: str = "http://localhost:9991/v1/audio/transcriptions"

    # TTS HTTP API 配置
    TTS_API_URL: str = "http://localhost:9992/inference_zero_shot"
    TTS_PROMPT_TEXT: str = "希望你以后能够做的比我还好哟"

    # RAG / Milvus 嵌入配置
    MILVUS_HOST: str = Field("localhost", alias="MILVUS_HOST")
    MILVUS_PORT: str = Field("19530", alias="MILVUS_PORT")
    BACKEND_BASE_URL: str = Field(
        "http://guineapig-backend:6880", alias="BACKEND_BASE_URL"
    )

    # LLM (DeepSeek) 配置
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_MODEL_NAME: str = "deepseek-chat"

    # 网络搜索配置
    SEARXNG_URL: str = "http://localhost:8484"

    # Redis 配置（用于 PipelineSession 分布式状态管理）
    REDIS_HOST: str = Field("localhost", alias="REDIS_HOST")
    REDIS_PORT: int = Field(6379, alias="REDIS_PORT")
    REDIS_DB: int = Field(0, alias="REDIS_DB")
    REDIS_PASSWORD: str = Field("", alias="REDIS_PASSWORD")

    # 本地资产 & S3 路径
    PROMPT_WAV_PATH: str = ""  # 为空时自动计算
    S3_PROMPT_KEY: str = "audio/tts/prompt/prompt.wav"
    DATA_DIR: str = ""  # 本地数据目录，为空时自动计算

    # Langfuse 可观测性配置
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_BASE_URL: str = ""
    LANGFUSE_ENABLE: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"


# 全局配置实例
settings = Settings()

# 计算 PROMPT_WAV_PATH 默认值（相对于 app/ 目录的上级 asset/ 目录）
if not settings.PROMPT_WAV_PATH:
    _app_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(_app_dir)
    settings.PROMPT_WAV_PATH = os.path.join(
        _project_root, "asset", "zero_shot_prompt.wav"
    )
else:
    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 计算 DATA_DIR 默认值
if not settings.DATA_DIR:
    settings.DATA_DIR = os.path.join(_project_root, "data")

# 确定线程数量
import multiprocessing

if settings.SYNC_THREAD_COUNT is None:
    # 自动确定线程数量，取CPU核心数和32的较小值
    settings.SYNC_THREAD_COUNT = min(multiprocessing.cpu_count(), 32)
else:
    # 使用用户指定的线程数，但不超过32
    settings.SYNC_THREAD_COUNT = min(int(settings.SYNC_THREAD_COUNT), 32)

# 根据环境动态调整配置
if settings.ENV == "prod":
    settings.DEBUG = False
    settings.DOCS_ENABLED = False
    settings.CORS_ORIGINS = [
        "https://wanghg11.fastapidemo.local",
    ]
