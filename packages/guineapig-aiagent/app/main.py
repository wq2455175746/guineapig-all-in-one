from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, Request
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.log import logger
from app.core.oss_wrapper_utils import cleanup_oss_client

# 导入事件监听器以注册信号监听
from app.middleware import (
    AdminTokenAuthMiddleware,
    ProcessTimeMiddleware,
    PrometheusMetricsMiddleware,
    RequestIDMiddleware,
)
from app.services.memory_scheduler_service import memory_scheduler
from app.services.langfuse_client import init_langfuse, close_langfuse
from app.services.otel_service import otel_service
from app.services.rag_retrieval_service import MilvusSearcher
from app.schemas.base_models import error_response

from app.exceptions.common_exception import CommonException
from app.exceptions.error_code import ConstantCodeEnum

from app.routers import asr, llm, memory, rag, skill, task, agent, agent_control


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 应用启动时初始化资源（可选）
    logger.info("应用启动，初始化资源...")

    # 初始化 Langfuse 可观测性
    init_langfuse()

    # 启动内存监控定时任务（每5分钟执行一次）
    memory_scheduler.start_memory_monitoring(interval_minutes=1)

    # 加载 Milvus 集合到内存，确保 RAG 查询可用
    logger.info("正在加载 Milvus 集合到内存...")
    MilvusSearcher.load_all_collections(
        host=settings.MILVUS_HOST,
        port=settings.MILVUS_PORT,
    )

    yield  # 应用运行期间

    # 应用关闭时（shutdown），手动释放所有资源
    logger.info("应用关闭，清理资源...")

    # 1. 停止内存监控定时任务
    memory_scheduler.stop_memory_monitoring()

    # 2. 清理OSS客户端，避免信号量泄漏
    cleanup_oss_client()

    # 3. 关闭 Langfuse 客户端（flush + 清理）
    close_langfuse()

    # 4. 关闭可观察指标 Redis 连接
    await otel_service.close()

    # 5. 取消未完成的 RAG 后台嵌入任务
    rag.cancel_pending_embedding_tasks()


# 创建FastAPI应用
app = FastAPI(
    title="Guineapig-Aiagent API",
    description="guineapig-aiagent服务API接口",
    version="1.0.0",
    lifespan=lifespan,
)

# 添加中间件（后添加者位于外层，即请求先经过）。
# 请求流：RequestID → CORS → Auth → Metrics → ProcessTime → 路由
# RequestID 置于最外层，确保 request_id 覆盖所有请求/响应（含 401、异常响应）
app.add_middleware(ProcessTimeMiddleware)
app.add_middleware(PrometheusMetricsMiddleware)
app.add_middleware(AdminTokenAuthMiddleware)
# CORS：dev 默认 ["*"]，prod 由 CORS_ORIGINS 环境变量（JSON 数组）收紧配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)

# 注册路由
app.include_router(task.router)
app.include_router(asr.router)
app.include_router(llm.router)
app.include_router(skill.router)
app.include_router(rag.router)
app.include_router(memory.router)
app.include_router(agent.router)
app.include_router(agent_control.router)


@app.get("/")
async def root():
    """根路径，返回服务信息"""
    return {
        "message": "OpenAlex Data2Store Service",
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"up": 1}


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# 处理自定义业务异常
@app.exception_handler(CommonException)
async def d2s_exception_handler(request: Request, e: CommonException):
    logger.error(e)
    return error_response(message=e.message, code=e.code, data=e.data)


# 全局异常处理器
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, e: Exception):
    # 生产环境建议隐藏具体异常信息，只返回通用提示
    logger.error(e)
    return error_response(
        message=ConstantCodeEnum.SERVER_ERROR.cn_name,
        code=ConstantCodeEnum.SERVER_ERROR.val,
    )
