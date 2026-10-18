#!/bin/bash
# GuineaPig Docker 镜像批量构建脚本
# 为所有服务（backend / aiagent / ops-web）构建 Docker 镜像。
# 可通过环境变量 DOCKER_REGISTRY、DOCKER_TAG 覆盖仓库地址与标签。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"   # 本脚本位于 scripts/docker/，故上溯两级

# 配置：镜像仓库前缀与标签，未设置时分别回退为空（本地）和 latest。
REGISTRY="${DOCKER_REGISTRY:-}"
TAG="${DOCKER_TAG:-latest}"

# 需要构建的服务列表。
SERVICES=(
    "guineapig-backend"
    "guineapig-aiagent"
    "guineapig-ops-web"
)

echo "============================================"
echo "  GuineaPig Docker Build All"
echo "  Registry: ${REGISTRY:-local}"
echo "  Tag: $TAG"
echo "============================================"
echo ""

# 逐个服务构建镜像。
for service in "${SERVICES[@]}"; do
    echo "--- Building $service ---"
    pkg_dir="$ROOT_DIR/packages/$service"

    # 包目录不存在则跳过。
    if [ ! -d "$pkg_dir" ]; then
        echo "  ⚠ Package directory not found: $pkg_dir (skipping)"
        continue
    fi

    # 没有 Dockerfile 则跳过。
    if [ ! -f "$pkg_dir/Dockerfile" ]; then
        echo "  ⚠ No Dockerfile found for $service (skipping)"
        continue
    fi

    # 组装镜像名：有 REGISTRY 时前缀 registry/，否则为本地镜像。
    image_name="${REGISTRY:+$REGISTRY/}$service:$TAG"

    echo "  Building image: $image_name"
    docker build \
        --tag "$image_name" \
        --file "$pkg_dir/Dockerfile" \
        "$pkg_dir"

    echo "  ✓ $service built successfully"
    echo ""
done

echo "============================================"
echo "  All services built successfully!"
echo "============================================"

# 列出刚构建出的镜像。
echo ""
echo "Built images:"
for service in "${SERVICES[@]}"; do
    image_name="${REGISTRY:+$REGISTRY/}$service:$TAG"
    docker images "$image_name" 2>/dev/null || true
done
