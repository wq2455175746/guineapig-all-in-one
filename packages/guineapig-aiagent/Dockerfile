# ============================================================
# GuineaPig AI Agent — Multi-stage Docker Build
# ============================================================
# Stage 1: Python dependencies
FROM python:3.13-slim AS builder

WORKDIR /build
COPY requirements.txt ./

ENV TZ=Asia/Shanghai \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime
FROM python:3.13-slim


RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 运行时系统依赖（curl 用于 healthcheck，ffmpeg 可选）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 创建非 root 用户
RUN groupadd -r appuser && useradd -r -g appuser -m -s /bin/bash appuser

# 复制 Python 依赖
COPY --from=builder /install /usr/local

# 创建应用目录
RUN mkdir -p /app/data /app/logs /app/asset

# 复制应用代码
COPY --chown=appuser:appuser . /app/

WORKDIR /app

# 确保必要目录存在
RUN mkdir -p /app/data /app/logs && chown -R appuser:appuser /app/data /app/logs

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 使用 Uvicorn 启动
CMD ["uvicorn", "app.main:app", \
    "--host", "0.0.0.0", \
    "--port", "8000", \
    "--workers", "1", \
    "--loop", "uvloop", \
    "--http", "httptools", \
    "--timeout-keep-alive", "5", \
    "--limit-concurrency", "10", \
    "--log-level", "info", \
    "--access-log", \
    "--proxy-headers", \
    "--forwarded-allow-ips", "*"]
