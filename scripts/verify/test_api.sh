#!/bin/bash
# GuineaPig API 冒烟测试
# 检查各服务的基础 API 端点是否返回预期状态码。
# 服务地址可通过 BACKEND_URL / AIAGENT_URL / OPS_WEB_URL 覆盖。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 各服务地址配置（可覆盖）。
BACKEND_URL="${BACKEND_URL:-http://localhost:8080}"
AIAGENT_URL="${AIAGENT_URL:-http://localhost:8000}"
OPS_WEB_URL="${OPS_WEB_URL:-http://localhost:3000}"

PASS=0
FAIL=0

# 检查单个端点：curl 取 HTTP 状态码并与期望值比较，累计通过/失败计数。
# 参数: $1 描述  $2 URL  $3 期望状态码（默认 200）
check() {
    local desc="$1"
    local url="$2"
    local expected_code="${3:-200}"

    echo -n "  Testing $desc ... "
    local http_code
    # -o /dev/null 丢弃响应体，-w 只输出状态码；连接失败时回退为 "000"。
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$url" 2>/dev/null || echo "000")

    if [ "$http_code" = "$expected_code" ]; then
        echo "PASS (HTTP $http_code)"
        PASS=$((PASS + 1))
    else
        echo "FAIL (expected $expected_code, got $http_code)"
        FAIL=$((FAIL + 1))
    fi
}

echo "============================================"
echo "  GuineaPig API Smoke Tests"
echo "============================================"
echo ""

# 后端健康与基础接口。
echo "[Backend API]"
check "Backend health endpoint" "$BACKEND_URL/health" "200"
check "Backend API v1 users" "$BACKEND_URL/api/v1/users" "200"

# AIAgent 健康检查。
echo ""
echo "[AIAgent API]"
check "AIAgent health endpoint" "$AIAGENT_URL/health" "200"

# 运营后台首页。
echo ""
echo "[Ops Web]"
check "Ops Web index" "$OPS_WEB_URL/" "200"

# 汇总结果。
echo ""
echo "============================================"
echo "  Results: $PASS passed, $FAIL failed"
echo "============================================"

# 有失败则非零退出。
if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
