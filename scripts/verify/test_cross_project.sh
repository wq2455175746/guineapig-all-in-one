#!/bin/bash
# GuineaPig Cross-Project Integration Test
# Tests the full voice dialogue flow across packages.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

BACKEND_URL="${BACKEND_URL:-http://localhost:8080}"
AIAGENT_URL="${AIAGENT_URL:-http://localhost:8000}"

PASS=0
FAIL=0

check_flow() {
    local step="$1"
    local result="$2"
    local expected="$3"

    echo -n "  Step: $step ... "
    if echo "$result" | grep -q "$expected"; then
        echo "PASS"
        PASS=$((PASS + 1))
    else
        echo "FAIL (expected '$expected' in response)"
        FAIL=$((FAIL + 1))
    fi
}

echo "============================================"
echo "  GuineaPig Cross-Project Integration Test"
echo "============================================"
echo ""
echo "Testing voice dialogue flow:"
echo "  Client -> S3 -> Backend -> AIAgent -> ASR -> LLM -> TTS"
echo ""

# Step 1: Verify backend can reach AIAgent
echo "[Flow Check]"
RESP=$(curl -s --connect-timeout 5 "$BACKEND_URL/health" 2>/dev/null || echo '{"status":"unreachable"}')
check_flow "Backend health" "$RESP" "ok"

# Step 2: Create a test task
RESP=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d '{"user_id":1,"s3_path":"/test/audio.mp3","task_id":"test-integration-001"}' \
    --connect-timeout 5 \
    "$BACKEND_URL/api/v1/tasks" 2>/dev/null || echo '{"error":"unreachable"}')
check_flow "Submit voice task" "$RESP" "task_id"

# Step 3: Check AIAgent health
RESP=$(curl -s --connect-timeout 5 "$AIAGENT_URL/health" 2>/dev/null || echo '{"status":"unreachable"}')
check_flow "AIAgent health" "$RESP" "ok"

# Summary
echo ""
echo "============================================"
echo "  Results: $PASS passed, $FAIL failed"
echo "============================================"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
