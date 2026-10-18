#!/bin/bash
# GuineaPig 本地部署脚本
# 使用 docker-compose 在本地启动全部服务。
# 可通过环境变量 COMPOSE_FILE 覆盖使用的 compose 文件（默认 docker-compose.dev.yml）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"   # 本脚本位于 scripts/docker/，故上溯两级

# 使用的 compose 文件（可覆盖）。
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.dev.yml}"

echo "============================================"
echo "  GuineaPig Local Deployment"
echo "  Compose file: $COMPOSE_FILE"
echo "============================================"
echo ""

cd "$ROOT_DIR"   # 切换至仓库根，确保 compose 的相对路径生效

# 前置条件检查
echo "[Prerequisites]"

# 1) Docker 是否在运行。
echo -n "  Docker ... "
if docker info >/dev/null 2>&1; then
    echo "OK"
else
    echo "FAILED"
    echo "  Docker is not running. Please start Docker first."
    exit 1
fi

# 2) docker compose 子命令是否可用。
echo -n "  docker compose ... "
if docker compose version >/dev/null 2>&1; then
    echo "OK"
else
    echo "FAILED"
    echo "  docker compose is not available."
    exit 1
fi

echo ""

# 可选：停止已有容器（交互确认）。
read -r -p "Stop existing containers? [y/N]: " stop_existing
if [[ "$stop_existing" =~ ^[Yy]$ ]]; then
    echo "  Stopping existing containers..."
    # --remove-orphans 一并清理 compose 文件中已移除服务的遗留容器。
    docker compose -f "$COMPOSE_FILE" down --remove-orphans 2>/dev/null || true
fi

# 启动服务（后台运行，--build 先重建镜像）。
echo ""
echo "[Starting Services]"
docker compose -f "$COMPOSE_FILE" up -d --build

# 等待服务变为健康状态。
echo ""
echo "[Waiting for services to be healthy...]"
sleep 5

# 查看服务状态。
echo ""
echo "[Service Status]"
docker compose -f "$COMPOSE_FILE" ps

# 输出常见访问地址与后续操作提示。
echo ""
echo "============================================"
echo "  Services running:"
echo "  Backend:   http://localhost:8080"
echo "  AIAgent:   http://localhost:8000"
echo "  Ops Web:   http://localhost:3000"
echo "============================================"
echo ""
echo "  View logs: docker compose -f $COMPOSE_FILE logs -f"
echo "  Stop:      docker compose -f $COMPOSE_FILE down"
