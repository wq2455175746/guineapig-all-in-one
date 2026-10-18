#!/bin/bash
# GuineaPig 端到端测试编排器
# 依次运行所有验证测试套件（冒烟测试、跨项目集成、Python 集成）并汇总结果。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "============================================"
echo "  GuineaPig End-to-End Test Suite"
echo "============================================"
echo ""

TOTAL_PASS=0
TOTAL_FAIL=0

# 运行一个测试套件：依据脚本退出码累计通过/失败计数。
# 参数: $1 套件名  $2 可执行脚本路径
run_suite() {
    local name="$1"
    local script="$2"

    echo "--- $name ---"
    if "$script"; then
        echo "  Suite PASSED"
        TOTAL_PASS=$((TOTAL_PASS + 1))
    else
        echo "  Suite FAILED"
        TOTAL_FAIL=$((TOTAL_FAIL + 1))
    fi
    echo ""
}

# 前置条件检查（仅提示，不阻断）。
echo "[Prerequisites]"
echo -n "  Docker running ... "
if docker info >/dev/null 2>&1; then
    echo "YES"
else
    echo "NO (some tests may fail)"
fi

echo -n "  docker-compose available ... "
if docker compose version >/dev/null 2>&1; then
    echo "YES"
else
    echo "NO"
fi
echo ""

# 运行各测试套件（顺序执行）。
run_suite "API Smoke Tests" "$SCRIPT_DIR/test_api.sh"
run_suite "Cross-Project Integration" "$SCRIPT_DIR/test_cross_project.sh"
run_suite "Python Integration Tests" "$SCRIPT_DIR/test_integration.py"

# 运行项目级校验脚本。
echo "--- Project Validation ---"
if python3 "$ROOT_DIR/scripts/validate.py"; then
    echo "  Validation PASSED"
    TOTAL_PASS=$((TOTAL_PASS + 1))
else
    echo "  Validation FAILED"
    TOTAL_FAIL=$((TOTAL_FAIL + 1))
fi

# 最终汇总。
echo ""
echo "============================================"
echo "  E2E Test Summary"
echo "  Passed: $TOTAL_PASS suites"
echo "  Failed: $TOTAL_FAIL suites"
echo "============================================"

# 有失败套件则非零退出。
if [ "$TOTAL_FAIL" -gt 0 ]; then
    exit 1
fi
