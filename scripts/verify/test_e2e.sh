#!/bin/bash
# GuineaPig End-to-End Test Orchestrator
# Runs all verification tests in order.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "============================================"
echo "  GuineaPig End-to-End Test Suite"
echo "============================================"
echo ""

TOTAL_PASS=0
TOTAL_FAIL=0

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

# Prerequisite check
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

# Run test suites
run_suite "API Smoke Tests" "$SCRIPT_DIR/test_api.sh"
run_suite "Cross-Project Integration" "$SCRIPT_DIR/test_cross_project.sh"
run_suite "Python Integration Tests" "$SCRIPT_DIR/test_integration.py"

# Run project-level validations
echo "--- Project Validation ---"
if python3 "$ROOT_DIR/scripts/validate.py"; then
    echo "  Validation PASSED"
    TOTAL_PASS=$((TOTAL_PASS + 1))
else
    echo "  Validation FAILED"
    TOTAL_FAIL=$((TOTAL_FAIL + 1))
fi

# Final summary
echo ""
echo "============================================"
echo "  E2E Test Summary"
echo "  Passed: $TOTAL_PASS suites"
echo "  Failed: $TOTAL_FAIL suites"
echo "============================================"

if [ "$TOTAL_FAIL" -gt 0 ]; then
    exit 1
fi
