#!/bin/bash
# GuineaPig Docker Build All
# Builds Docker images for all services.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Configuration
REGISTRY="${DOCKER_REGISTRY:-}"
TAG="${DOCKER_TAG:-latest}"

# Services to build
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

for service in "${SERVICES[@]}"; do
    echo "--- Building $service ---"
    pkg_dir="$ROOT_DIR/packages/$service"

    if [ ! -d "$pkg_dir" ]; then
        echo "  ⚠ Package directory not found: $pkg_dir (skipping)"
        continue
    fi

    if [ ! -f "$pkg_dir/Dockerfile" ]; then
        echo "  ⚠ No Dockerfile found for $service (skipping)"
        continue
    fi

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

# List built images
echo ""
echo "Built images:"
for service in "${SERVICES[@]}"; do
    image_name="${REGISTRY:+$REGISTRY/}$service:$TAG"
    docker images "$image_name" 2>/dev/null || true
done
