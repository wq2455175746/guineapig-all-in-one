"""
Agent 入口路由端到端测试 — Phase 0-3 + DAG 生成。

DeepAnalyzer 和 DAGGenerator 由 settings.LLM_API_KEY 控制。
有 LLM Key 时 → 全流程测试（含 LLM 分析 + DAG 生成）
无 LLM Key 时 → 验证优雅降级（fallback/error）
"""

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)
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

    # ── Phase 1: 关键词匹配 → proceed ──

    def test_search_keyword(self):
        """搜索关键词 → proceed (置信度 >= 0.5)"""
        resp = client.post(f"{BASE}/chat", json={"message": "帮我搜索量子计算的最新进展"})
        data = resp.json()["result"]
        assert data["action"] == "proceed"
        assert data["quick_filter"] == "simple"
        assert any(c["intent_type"] == "web_search" for c in data["candidates"])

    def test_memory_keyword(self):
        """记忆关键词 → proceed"""
        resp = client.post(f"{BASE}/chat", json={"message": "我记得上次讨论的方案"})
        data = resp.json()["result"]
        assert data["action"] == "proceed"
        assert any(c["intent_type"] == "memory_retrieve" for c in data["candidates"])

    def test_cli_execute_keyword(self):
        """CLI 执行 → proceed"""
        resp = client.post(f"{BASE}/chat", json={"message": "帮我安装python包requests"})
        data = resp.json()["result"]
        assert data["action"] == "proceed"
        assert any(c["intent_type"] == "cli_execute" for c in data["candidates"])

    def test_summarize_keyword(self):
        """总结 → proceed (置信度 >= 0.5)"""
        resp = client.post(f"{BASE}/chat", json={"message": "帮我把这篇文章总结一下"})
        data = resp.json()["result"]
        assert data["action"] == "proceed"
        assert any(c["intent_type"] == "memory_summarize" for c in data["candidates"])

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
                        "tools": ["read_file", "write_file"],
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

    def test_decision_structure(self):
        """决策结果应包含完整结构"""
        resp = client.post(f"{BASE}/chat", json={"message": "帮我搜索一下最新的AI新闻"})
        data = resp.json()["result"]
        assert "decision" in data
        assert "action" in data["decision"]
        assert "confidence" in data["decision"]
        assert "reason" in data["decision"]

    # ── Phase 2: 复杂请求 (LLM 可用时全流程) ──

    def test_complex_multi_step(self):
        """复杂请求 → complex 标记 → LLM 分析 → proceed (LLM 可用时)"""
        resp = client.post(
            f"{BASE}/chat",
            json={"message": "先搜索量子计算的最新进展，然后总结成报告"},
        )
        data = resp.json()["result"]
        assert data["quick_filter"] == "complex"

        if HAS_LLM and data.get("deep_analysis"):
            # LLM 可用且分析成功 → proceed
            assert data["action"] in ("proceed", "clarify")
            assert data["deep_analysis"]["intent_type"] is not None
        else:
            # 无 LLM → fallback
            assert data["action"] in ("fallback", "fallback_to_chat")

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
        """无关键词匹配 → 走 LLM 或 fallback，不崩溃"""
        resp = client.post(f"{BASE}/chat", json={"message": "今天天气怎么样"})
        data = resp.json()["result"]
        # 任何合理的响应都可以（不崩溃）
        assert data["action"] in (
            "fallback", "fallback_to_chat", "clarify", "proceed", "reject"
        )

    # ── SSE Streaming ──

    def test_stream_trivial_returns_json(self):
        """SSE 端点对 trivial 消息应返回 JSON（不流式）"""
        resp = client.post(f"{BASE}/chat/stream", json={"message": "你好"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["action"] == "fallback_to_chat"

    def test_stream_empty_message(self):
        """SSE 端点空消息应返回错误"""
        resp = client.post(f"{BASE}/chat/stream", json={"message": "  "})
        data = resp.json()
        assert data.get("errCode") == 400 or data.get("code") == 400

    def test_stream_simple_returns_json(self):
        """SSE 端点对简单消息应返回 JSON（无需执行）"""
        resp = client.post(f"{BASE}/chat/stream", json={"message": "帮我搜索一下AI新闻"})
        data = resp.json()["result"]
        assert data["action"] in ("proceed", "clarify", "fallback")

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
