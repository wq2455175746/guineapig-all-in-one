"""
路由集成测试 — 测试 FastAPI /guineapig-aiagent/task/submit 端点
"""

import os
import sys

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.config import settings
from app.main import app


@pytest.fixture
def client():
    """提供 FastAPI TestClient（默认携带测试鉴权 token）"""
    client = TestClient(app)
    client.headers.update({"X-Admin-Token": settings.ADMIN_TOKEN})
    return client


class TestTaskRouter:
    """任务提交路由集成测试"""

    def test_submit_success(self, client, mocker):
        """正常提交应返回 200 和成功响应"""
        mock_handler = mocker.patch("app.routers.task.handler_task_submit")
        mock_handler.return_value = JSONResponse(
            status_code=200,
            content={
                "success": True,
                "errCode": 0,
                "errMessage": "success",
                "result": {
                    "taskId": "t1",
                    "requestId": "r1",
                    "its": 1717000000,
                    "objectKey": "audio/tts/1/202600521/o.mp3",
                },
            },
        )

        payload = {
            "sessionId": "session-t1",
            "taskId": "t1",
            "requestId": "r1",
            "its": 1717000000,
            "objectKey": "audio/asr/1/202600521/a.mp3",
        }

        resp = client.post("/guineapig-aiagent/task/submit", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["result"]["taskId"] == "t1"

    def test_submit_missing_field(self, client):
        """缺少必填字段应返回 422"""
        resp = client.post(
            "/guineapig-aiagent/task/submit",
            json={"taskId": "t1"},  # 缺少 sessionId, requestId, its, objectKey
        )
        assert resp.status_code == 422

    def test_submit_empty_body(self, client):
        """空请求体应返回 422"""
        resp = client.post(
            "/guineapig-aiagent/task/submit",
            json={},
        )
        assert resp.status_code == 422

    def test_submit_wrong_type(self, client):
        """字段类型错误应返回 422"""
        resp = client.post(
            "/guineapig-aiagent/task/submit",
            json={
                "sessionId": "session-t1",
                "taskId": "t1",
                "requestId": "r1",
                "its": "not-an-int",  # 本应为 int
                "objectKey": "audio/asr/1/202600521/a.mp3",
            },
        )
        assert resp.status_code == 422

    def test_submit_internal_error(self, client, mocker):
        """服务内部抛出异常时应返回 500 状态码和错误响应"""
        mock_handler = mocker.patch("app.routers.task.handler_task_submit")
        mock_handler.return_value = JSONResponse(
            status_code=500,
            content={
                "success": False,
                "errCode": 500,
                "errMessage": "Internal Error",
                "result": None,
            },
        )

        payload = {
            "sessionId": "session-t1",
            "taskId": "t1",
            "requestId": "r1",
            "its": 1717000000,
            "objectKey": "audio/asr/1/202600521/a.mp3",
        }

        resp = client.post("/guineapig-aiagent/task/submit", json=payload)
        assert resp.status_code == 500
        data = resp.json()
        assert data["success"] is False
