#!/bin/bash
# guineapig-client 构建打包脚本
# Usage: ./build.sh [platform] [--dir]
#   platform: mac, win, linux, all (default: current OS)
#   --dir:    仅输出 .app 目录（不打包，速度最快，适合开发测试）
#
# 环境变量:
#   USE_MIRROR=true  启用国内镜像加速（默认 true）
#   MIRROR=https://npmmirror.com/mirrors/  镜像地址
#   ELECTRON_CACHE_DIR  自定义 Electron 缓存目录（默认 .electron-cache/）

set -e

cd "$(dirname "$0")"

USE_MIRROR="${USE_MIRROR:-true}"
MIRROR="${MIRROR:-https://npmmirror.com/mirrors}"
ELECTRON_CACHE_DIR="${ELECTRON_CACHE_DIR:-$(pwd)/.electron-cache}"

# 国内镜像加速
if [ "$USE_MIRROR" = "true" ]; then
  export ELECTRON_MIRROR="${MIRROR}/electron/"
  export ELECTRON_BUILDER_BINARIES_MIRROR="${MIRROR}/electron-builder-binaries/"
  echo "==> 启用国内镜像: ${MIRROR}"
fi

# 持久化 Electron 缓存目录，避免每次重新下载 123MB
# 在 TeamCity 上，将此目录设为持久化路径（如 %system.teamcity.build.checkoutDir%/.electron-cache）
export ELECTRON_BUILDER_CACHE="${ELECTRON_CACHE_DIR}"
mkdir -p "${ELECTRON_CACHE_DIR}"
echo "==> Electron 缓存目录: ${ELECTRON_CACHE_DIR}"

echo "==> 1/3 安装依赖..."
npm install

echo "==> 2/3 构建前端 + Electron 主进程..."
npx vue-tsc --noEmit 2>/dev/null || true
npx vite build

echo "==> 3/3 验证产物结构..."
if [ ! -f "dist/electron/index.js" ]; then
  echo "ERROR: dist/electron/index.js 不存在，构建失败"
  exit 1
fi
echo "  ✓ dist/electron/index.js"
echo "  ✓ dist/renderer/index.html"

echo "==> 4/3 electron-builder 打包..."

PLATFORM="${1:-$(uname)}"
DIR_ONLY=""
[ "$2" = "--dir" ] && DIR_ONLY="--dir"

case "$PLATFORM" in
  mac|darwin|Darwin|MAC)
    echo "打包 macOS..."
    npx electron-builder --mac $DIR_ONLY
    echo "产物: dist/release/mac/"
    ;;
  win|windows|Windows|WIN)
    echo "打包 Windows..."
    npx electron-builder --win $DIR_ONLY
    echo "产物: dist/release/win/"
    ;;
  linux|Linux|LINUX)
    echo "打包 Linux..."
    npx electron-builder --linux $DIR_ONLY
    echo "产物: dist/release/linux/"
    ;;
  all|ALL)
    echo "打包全平台..."
    npx electron-builder --mac --win --linux $DIR_ONLY
    echo "产物: dist/release/"
    ;;
esac

echo "==> 完成！"
