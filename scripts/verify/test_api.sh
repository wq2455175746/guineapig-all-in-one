#!/bin/bash
# GuineaPig API Smoke Test
# Tests basic API endpoint health across all services.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Configuration
BACKEND_URL="${BACKEND_URL:-http://localhost:8080}"
AIAGENT_URL="${AIAGENT_URL:-http://localhost:8000}"
OPS_WEB_URL="${OPS_WEB_URL:-http://localhost:3000}"

PASS=0
FAIL=0

check() {
    local desc="$1"
    local url="$2"
    local expected_code="${3:-200}"

    echo -n "  Testing $desc ... "
    local http_code
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

# Backend health check
echo "[Backend API]"
check "Backend health endpoint" "$BACKEND_URL/health" "200"
check "Backend API v1 users" "$BACKEND_URL/api/v1/users" "200"

# AIAgent health check
echo ""
echo "[AIAgent API]"
check "AIAgent health endpoint" "$AIAGENT_URL/health" "200"

# Ops Web
echo ""
echo "[Ops Web]"
check "Ops Web index" "$OPS_WEB_URL/" "200"

# Summary
echo ""
echo "============================================"
echo "  Results: $PASS passed, $FAIL failed"
echo "============================================"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
