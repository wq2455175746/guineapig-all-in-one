# app/middleware.py

import hmac
import time

from fastapi import Response, Request
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, Gauge
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.core.log import logger

# 1. 定义进阶Prometheus指标
# 计数器：总请求数
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests received by FastAPI",
    ["endpoint", "method", "status_code"]
)

# 直方图：请求处理耗时分布（自动划分区间，便于Prometheus统计分位数）
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "Histogram of HTTP request processing time in seconds",
    ["endpoint", "method"]
)

# 服务健康状态指标
service_up = Gauge(
    "service_up",
    "Service health status (1=up, 0=down)"
)

class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """Prometheus指标收集中间件"""

    async def dispatch(self, request: Request, call_next):
        # 设置服务健康状态为1（正常运行）
        service_up.set(1)
        
        # 提取请求元数据
        endpoint = str(request.url.path)
        method = request.method
        start_time = time.time()
        status_code = 200
        
        # 调用后续接口处理逻辑
        try:
            response: Response = await call_next(request)
            status_code = str(response.status_code)
        except Exception as e:
            # 捕获异常，标记状态码为500
            status_code = "500"
            raise e
        finally:
            # 计算处理耗时
            processing_time = time.time() - start_time
            # 自动更新指标
            http_requests_total.labels(endpoint=endpoint, method=method, status_code=status_code).inc()
            http_request_duration_seconds.labels(endpoint=endpoint, method=method).observe(processing_time)
        
        return response


class AdminTokenAuthMiddleware(BaseHTTPMiddleware):
    """Token 鉴权中间件 — 保护除元数据白名单外的所有接口。

    - 从 `X-Admin-Token` 或 `Authorization: Bearer <token>` 读取访问令牌
    - 与 `settings.ADMIN_TOKEN` 做常量时间比较（hmac.compare_digest），不匹配返回 401
    - `settings.ADMIN_TOKEN` 为空时 fail-closed：拒绝所有非白名单请求，
      避免"未配置即裸奔"。生产环境启动时 config.py 会输出 CRITICAL 告警。
    - dev 下同样生效：开发者需在 .env 中配置 ADMIN_TOKEN 才能调用接口
    """

    # 元数据端点白名单（无需鉴权，供健康检查 / API 文档使用）
    ALLOWLIST_PATHS = {"/docs", "/openapi.json", "/redoc", "/health"}

    async def dispatch(self, request: Request, call_next):
        # 放行元数据端点（健康检查、API 文档）
        if request.url.path in self.ALLOWLIST_PATHS:
            return await call_next(request)

        # 从 X-Admin-Token 或 Authorization: Bearer 读取 token
        token = request.headers.get("X-Admin-Token", "")
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[len("Bearer "):].strip()

        expected = settings.ADMIN_TOKEN
        # 未配置 token 或 token 不匹配 → 401（fail-closed）
        if not expected or not token or not hmac.compare_digest(
            token.encode("utf-8"), expected.encode("utf-8")
        ):
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized", "message": "无效或缺失的访问令牌"},
            )

        return await call_next(request)


class ProcessTimeMiddleware(BaseHTTPMiddleware):
    """计算请求处理时间的中间件"""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        # 处理请求
        response = await call_next(request)
        # 计算处理时间
        process_time = time.time() - start_time
        # 添加自定义响应头
        response.headers["X-Process-Time"] = f"{process_time:.3f}s"
        # 记录慢请求
        if process_time > 1.0:
            logger.warning(
                f"SLOW REQUEST: {request.method} {request.url.path} "
                f"TIME_CONSUME: {process_time:.3f}s | "
                f"CLIENT: {request.client.host if request.client else 'unknown'}"
            )
        # 记录所有请求（可选）
        logger.info(
            f"REQUEST: {request.method} {request.url.path} "
            f"STATUS: {response.status_code} TIME_CONSUME: {process_time:.3f}s"
        )
        return response
