"""
Agent 入口路由端到端测试 — 简化意图识别 (规则筛选 + LLM 意图识别) + DAG 生成。

DeepAnalyzer 和 DAGGenerator 由 settings.LLM_API_KEY 控制。
有 LLM Key 时 → 全流程测试（含 LLM 分析 + DAG 生成）
无 LLM Key 时 → 验证优雅降级（fallback_to_chat）
"""

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)
client.headers.update({"X-Admin-Token": settings.ADMIN_TOKEN})
BASE = "/guineapig-aiagent/agent"
HAS_LLM = bool(settings.LLM_API_KEY)


class TestAgentChat:
    """Agent 聊天入口端到端测试"""

    # ── 输入验证 ──

    def test_empty_message(self):
        """空消息应返回错误"""
        resp = client.post(f"{BASE}/chat", json={"message": "  "})
        data = resp.json()
        assert data.get("errCode") == 400 or data.get("code") == 400

    # ── Phase 0: Trivial ──

    def test_trivial_greeting(self):
        """问候 → fallback_to_chat"""
        resp = client.post(f"{BASE}/chat", json={"message": "你好"})
        data = resp.json()["result"]
        assert data["action"] == "fallback_to_chat"
        assert data["quick_filter"] == "trivial"

    def test_trivial_thanks(self):
        """感谢 → fallback_to_chat"""
        resp = client.post(f"{BASE}/chat", json={"message": "谢谢"})
        data = resp.json()["result"]
        assert data["action"] == "fallback_to_chat"

    def test_trivial_identity(self):
        """你是谁 → fallback_to_chat"""
        resp = client.post(f"{BASE}/chat", json={"message": "你是谁"})
        data = resp.json()["result"]
        assert data["action"] == "fallback_to_chat"

    # ── 非 trivial → LLM 意图识别 → 路由 ──

    def test_search_keyword(self):
        """搜索请求 → task → LLM 意图识别 → proceed 或 fallback_to_chat"""
        resp = client.post(f"{BASE}/chat", json={"message": "帮我搜索量子计算的最新进展"})
        data = resp.json()["result"]
        assert data["quick_filter"] == "task"
        assert data["action"] in ("proceed", "fallback_to_chat")

    def test_actionable_message(self):
        """可执行请求在有 LLM 时应生成 DAG"""
        resp = client.post(f"{BASE}/chat", json={"message": "帮我搜索今天星期几"})
        data = resp.json()["result"]
        assert data["quick_filter"] == "task"

        if HAS_LLM and data.get("deep_analysis"):
            # LLM 可用且分析成功 → proceed 并生成 DAG
            assert data["action"] in ("proceed", "fallback_to_chat")
            assert data["deep_analysis"]["intent_type"] is not None
        else:
            # 无 LLM → fallback_to_chat
            assert data["action"] == "fallback_to_chat"

    # ── 能力清单 ──

    def test_capabilities_in_response(self):
        """能力清单应始终包含在响应中"""
        resp = client.post(
            f"{BASE}/chat",
            json={
                "message": "帮我搜索一下",
                "mcp_servers": [
                    {
                        "server_name": "filesystem",
                        "transport_type": "stdio",
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
                        "tools": [
                            {"name": "read_file", "description": "read a file"},
                            {"name": "write_file", "description": "write a file"},
                        ],
                    }
                ],
                "skills": [{"name": "数据分析"}],
                "rag_context": {"rag_names": ["guineapig_docs"]},
            },
        )
        data = resp.json()["result"]
        assert "capabilities" in data
        caps = data["capabilities"]
        assert "available" in caps
        assert "formatted" in caps
        assert any("mcp_" in c for c in caps["available"])

    def test_response_structure(self):
        """响应应包含 action / quick_filter / deep_analysis / dag"""
        resp = client.post(f"{BASE}/chat", json={"message": "帮我搜索一下最新的AI新闻"})
        data = resp.json()["result"]
        assert "action" in data
        assert "quick_filter" in data
        assert "deep_analysis" in data
        assert "dag" in data

    # ── 复杂请求 (LLM 可用时全流程) ──

    def test_complex_multi_step(self):
        """复杂请求 → task → LLM 分析 → proceed (LLM 可用时)"""
        resp = client.post(
            f"{BASE}/chat",
            json={"message": "先搜索量子计算的最新进展，然后总结成报告"},
        )
        data = resp.json()["result"]
        assert data["quick_filter"] == "task"

        if HAS_LLM and data.get("deep_analysis"):
            # LLM 可用且分析成功 → proceed
            assert data["action"] in ("proceed", "fallback_to_chat")
            assert data["deep_analysis"]["intent_type"] is not None
        else:
            # 无 LLM → fallback_to_chat
            assert data["action"] == "fallback_to_chat"

    def test_dag_generation(self):
        """DAG 在有 LLM 时可能被生成"""
        resp = client.post(
            f"{BASE}/chat",
            json={"message": "先搜索再总结"},
        )
        data = resp.json()["result"]
        # 无论 LLM 是否可用，DAG 要么是 None 要么是有效结构
        if data.get("dag") is not None:
            dag = data["dag"]
            assert "steps" in dag
            assert "original_intent" in dag
            assert "estimated_total_steps" in dag
            if dag["steps"]:
                assert dag["steps"][0]["step_id"]
                assert dag["steps"][0]["capability"]

    # ── 降级路径 ──

    def test_no_keyword_no_llm(self):
        """无关键词消息 → 走 LLM 或 fallback，不崩溃"""
        resp = client.post(f"{BASE}/chat", json={"message": "今天天气怎么样"})
        data = resp.json()["result"]
        # 任何合理的响应都可以（不崩溃）
        assert data["action"] in ("fallback_to_chat", "proceed")

    # ── SSE Streaming ──

    def test_stream_trivial_returns_sse(self):
        """SSE 端点对 trivial 消息应返回 LLM 流式内容事件（不进入 DAG）"""
        resp = client.post(f"{BASE}/chat/stream", json={"message": "你好"})
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "text/event-stream" in content_type
        assert "event: content" in resp.text or "event: error" in resp.text

    def test_stream_empty_message(self):
        """SSE 端点空消息应返回错误"""
        resp = client.post(f"{BASE}/chat/stream", json={"message": "  "})
        data = resp.json()
        assert data.get("errCode") == 400 or data.get("code") == 400

    def test_stream_simple_message(self):
        """SSE 端点对可执行简单消息应返回 SSE 或 JSON（不崩溃）"""
        resp = client.post(f"{BASE}/chat/stream", json={"message": "帮我搜索一下AI新闻"})
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            assert "event: " in resp.text
        else:
            data = resp.json()
            assert data["result"]["action"] in ("proceed", "fallback_to_chat")

    def test_stream_complex_returns_sse(self):
        """SSE 端点对复杂请求应返回 SSE 事件流"""
        resp = client.post(
            f"{BASE}/chat/stream",
            json={"message": "先搜索量子计算的最新进展，然后总结成报告"},
        )
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "text/event-stream" in content_type or "application/json" in content_type

        # 如果是 SSE，验证事件结构
        if "text/event-stream" in content_type:
            text = resp.text
            assert "event: " in text
            assert "data: " in text
            # 应该包含计划就绪事件
            assert "plan_ready" in text or "execution_complete" in text or "error" in text

    def test_stream_returns_sse_events(self):
        """SSE 端点流式事件应包含正确的事件结构"""
        resp = client.post(
            f"{BASE}/chat/stream",
            json={"message": "先搜索AI最新进展再总结"},
        )
        # 如果返回 SSE
        if "text/event-stream" in resp.headers.get("content-type", ""):
            lines = resp.text.strip().split("\n")
            events = []
            for i, line in enumerate(lines):
                if line.startswith("event: "):
                    event_type = line[7:]
                    # 下一条 data 行
                    if i + 1 < len(lines) and lines[i + 1].startswith("data: "):
                        events.append(event_type)
            assert len(events) > 0
            # 通常应以 execution_complete 或 error 结束
            assert events[-1] in ("execution_complete", "error", "plan_ready")
        else:
            # JSON 响应也是有效的（非 proceed）
            data = resp.json()
            assert "result" in data or "errCode" in data