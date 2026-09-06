"""
鉴权中间件测试 — 验证 P0 接口鉴权（token 校验 + 元数据白名单）。

覆盖：
- 无 token 访问受保护端点 → 401
- 错误 token → 401
- X-Admin-Token 正确 → 放行
- Authorization: Bearer 正确 → 放行
- 元数据白名单（/health、/docs、/openapi.json、/redoc）无需 token → 放行
- agent_control（confirm/cancel/delegate-result）同样受保护
"""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

VALID_TOKEN = settings.ADMIN_TOKEN


@pytest.fixture
def client():
    """不带 token 的客户端（用于 401 断言）"""
    return TestClient(app)


@pytest.fixture
def authed_client():
    """带正确 token 的客户端"""
    c = TestClient(app)
    c.headers.update({"X-Admin-Token": VALID_TOKEN})
    return c


class TestAuthRequired:
    """受保护端点必须携带有效 token"""

    @pytest.mark.parametrize(
        "path,method,kwargs",
        [
            ("/", "get", {}),
            ("/metrics", "get", {}),
            ("/guineapig-aiagent/task/submit", "post", {"json": {}}),
            ("/guineapig-aiagent/asr/transcribe", "post", {"json": {"objectKey": "x"}}),
            ("/guineapig-aiagent/agent/chat", "post", {"json": {"message": "hi"}}),
            ("/guineapig-aiagent/agent/chat/stream", "post", {"json": {"message": "hi"}}),
            ("/guineapig-aiagent/llm/chat/stream", "post", {"json": {}}),
            ("/guineapig-aiagent/skill/process", "post", {"json": {}}),
            ("/guineapig-aiagent/rag/embed", "post", {"json": {}}),
            ("/guineapig-aiagent/memory/summarize", "post", {"json": {}}),
            ("/guineapig-aiagent/agent/chat/confirm", "post", {"json": {"session_id": "s1"}}),
            ("/guineapig-aiagent/agent/chat/cancel", "post", {"json": {"session_id": "s1"}}),
            ("/guineapig-aiagent/agent/chat/delegate-result", "post", {"json": {"session_id": "s1", "step_id": "st1"}}),
        ],
    )
    def test_no_token_returns_401(self, client, path, method, kwargs):
        resp = getattr(client, method)(path, **kwargs)
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self, client):
        resp = client.get("/", headers={"X-Admin-Token": "wrong-token"})
        assert resp.status_code == 401

    def test_wrong_bearer_returns_401(self, client):
        resp = client.get("/", headers={"Authorization": "Bearer wrong-token"})
        assert resp.status_code == 401

    def test_valid_x_admin_token_passes(self, authed_client):
        resp = authed_client.get("/")
        assert resp.status_code == 200

    def test_valid_bearer_passes(self, client):
        resp = client.get("/", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
        assert resp.status_code == 200


class TestMetadataAllowlist:
    """元数据端点无需鉴权"""

    @pytest.mark.parametrize("path", ["/health", "/docs", "/openapi.json", "/redoc"])
    def test_allowlist_without_token(self, client, path):
        resp = client.get(path)
        assert resp.status_code == 200


class TestAgentControlProtected:
    """agent_control 的 confirm/cancel/delegate-result 同样受鉴权保护"""

    @pytest.mark.parametrize(
        "path",
        [
            "/guineapig-aiagent/agent/chat/confirm",
            "/guineapig-aiagent/agent/chat/cancel",
            "/guineapig-aiagent/agent/chat/delegate-result",
        ],
    )
    def test_no_token_returns_401(self, client, path):
        resp = client.post(path, json={"session_id": "s1"})
        assert resp.status_code == 401

    def test_with_token_not_401(self, authed_client):
        """带正确 token 时不应被鉴权拦截（返回 4xx 应为参数/业务错误而非 401）"""
        resp = authed_client.post(
            "/guineapig-aiagent/agent/chat/delegate-result",
            json={"session_id": "s1", "step_id": "st1"},
        )
        assert resp.status_code != 401