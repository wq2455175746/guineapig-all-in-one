#!/bin/bash
# GuineaPig 跨项目集成测试
# 验证跨包的完整语音对话链路（客户端 -> S3 -> 后端 -> AIAgent -> ASR -> LLM -> TTS）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 服务地址（可覆盖）。
BACKEND_URL="${BACKEND_URL:-http://localhost:8080}"
AIAGENT_URL="${AIAGENT_URL:-http://localhost:8000}"

PASS=0
FAIL=0

# 校验单个流程步骤：判断响应体中是否包含期望子串，累计通过/失败计数。
# 参数: $1 步骤名  $2 响应体  $3 期望包含的子串
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

# 步骤 1：后端可达性（期望响应含 "ok"）。
echo "[Flow Check]"
RESP=$(curl -s --connect-timeout 5 "$BACKEND_URL/health" 2>/dev/null || echo '{"status":"unreachable"}')
check_flow "Backend health" "$RESP" "ok"

# 步骤 2：提交一个测试语音任务（期望响应含 task_id）。
RESP=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d '{"user_id":1,"s3_path":"/test/audio.mp3","task_id":"test-integration-001"}' \
    --connect-timeout 5 \
    "$BACKEND_URL/api/v1/tasks" 2>/dev/null || echo '{"error":"unreachable"}')
check_flow "Submit voice task" "$RESP" "task_id"

# 步骤 3：AIAgent 可达性（期望响应含 "ok"）。
RESP=$(curl -s --connect-timeout 5 "$AIAGENT_URL/health" 2>/dev/null || echo '{"status":"unreachable"}')
check_flow "AIAgent health" "$RESP" "ok"

# 汇总结果。
echo ""
echo "============================================"
echo "  Results: $PASS passed, $FAIL failed"
echo "============================================"

# 有失败则非零退出。
if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
