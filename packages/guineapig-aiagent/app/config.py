import json
import logging
import os
from typing import Annotated, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    SECRET_KEY: str = ""
    # 管理后台访问令牌：从环境变量读取（X-Admin-Token / Authorization: Bearer）。
    # 为空时鉴权中间件 fail-closed，拒绝除元数据白名单外的所有请求。
    ADMIN_TOKEN: str = ""
    # CORS 允许的来源：dev 默认 ["*"]，prod 必须通过环境变量 CORS_ORIGINS
    # （JSON 数组格式，如 '["https://a.com","https://b.com"]'）显式配置，不允许通配。
    # NoDecode 使环境变量以原始字符串交给 field_validator 处理，
    # 否则 pydantic-settings 会对空串做 JSON 解码直接抛 SettingsError 导致启动失败。
    CORS_ORIGINS: Annotated[List[str], NoDecode] = ["*"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _cors_origins_parse(cls, v):
        # 环境变量为空字符串（如 docker-compose 的 ${CORS_ORIGINS} 未设置）时视为未配置，
        # 走 fail-closed 分支；否则按 JSON 数组解析
        if v == "":
            return []
        if isinstance(v, str):
            return json.loads(v)
        return v

    # OSS对象存储配置
    OSS_AK: str = ""
    OSS_SK: str = ""
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
    # 回调 guineapig-backend 内部接口（/inner/api/v1/*）的共享 Token
    INNER_TOKEN: str = Field("", alias="INNER_TOKEN")

    # LLM (DeepSeek) 配置
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com"
    LLM_MODEL_NAME: str = "deepseek-chat"
    # LLM 调用有界重试：LLM_RETRY_ATTEMPTS 次重试 + 指数退避（LLM_RETRY_BACKOFF 秒起步）
    LLM_RETRY_ATTEMPTS: int = 2
    LLM_RETRY_BACKOFF: float = 1.0

    # 网络搜索配置
    SEARXNG_URL: str = "http://localhost:8484"

    # 是否主动调用 MCP list_tools() 刷新工具 schema（默认关闭）。
    # MCP tools 由 client 注册时同步到数据库（backend 透传含 input_schema 的快照），
    # 一般不会频繁变化，无需每次请求刷新。
    MCP_TOOLS_REFRESH: bool = False

    # RAG 注入上下文 token 预算（system + context 总和上限，超出裁剪/截断）
    RAG_CONTEXT_TOKEN_BUDGET: int = 8000

    # Redis 配置（用于 OtelService 指标上报）
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

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="forbid",
    )


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

# 凭据校验：检测未配置的敏感凭据，避免静默使用空值/占位值
if not settings.SECRET_KEY:
    logging.getLogger("app.config").warning(
        "SECRET_KEY 未配置，请通过环境变量或 .env 文件设置"
    )
if not settings.OSS_AK or not settings.OSS_SK:
    logging.getLogger("app.config").warning(
        "OSS_AK / OSS_SK 未配置，OSS 上传/下载功能将不可用"
    )

# 根据环境动态调整配置
if settings.ENV == "prod":
    settings.DEBUG = False
    settings.DOCS_ENABLED = False
    # prod 下 CORS 不允许通配 *：剥离混入列表的通配符；未显式配置任何来源时 fail-closed
    settings.CORS_ORIGINS = [
        origin for origin in settings.CORS_ORIGINS if origin != "*"
    ]
    if not settings.CORS_ORIGINS:
        logging.getLogger("app.config").critical(
            "prod 环境 CORS_ORIGINS 未配置，跨域访问将被拒绝（fail-closed）"
        )
    # prod 下 ADMIN_TOKEN 未配置 → 大声告警；鉴权中间件会对未配置的 token fail-closed，
    # 除元数据白名单外的所有接口将返回 401
    if not settings.ADMIN_TOKEN:
        logging.getLogger("app.config").critical(
            "ADMIN_TOKEN 未配置，生产环境除白名单外的所有接口将拒绝访问"
        )
