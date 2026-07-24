"""
任务编排服务单元测试 — 测试 handler_task_submit 完整管线
"""

import os
import sys

import pytest

from fastapi.responses import JSONResponse

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.services.task_service import handler_task_submit


def _make_request(session_id="session-001", task_id="task-001", request_id="req-001", its=1717000000, object_key="audio/asr/1000000001/202600521/audio.mp3"):
    return {
        "sessionId": session_id,
        "taskId": task_id,
        "requestId": request_id,
        "its": its,
        "objectKey": object_key,
    }


class TestHandlerTaskSubmit:
    """handler_task_submit 完整管线单元测试"""

    def test_success(self, mocker):
        """完整管线成功执行应返回成功 JSONResponse"""
        # Mock 所有内部依赖
        mocker.patch("app.services.task_service.download_file_from_s3")
        mocker.patch("app.services.task_service.handle_asr", return_value="识别文本")
        mocker.patch("app.services.task_service.get_llm_response", return_value="LLM 回复")
        mocker.patch("app.services.task_service.handle_tts", return_value="/tmp/tts/output.mp3")
        mocker.patch(
            "app.services.task_service.upload_tts_result",
            return_value="guineapig/audio/tts/1000000001/202600521/output.mp3",
        )

        resp = handler_task_submit(_make_request())

        # 验证返回 JSONResponse
        assert isinstance(resp, JSONResponse)
        body = resp.body
        import json
        data = json.loads(body)
        assert data["success"] is True
        assert data["result"]["taskId"] == "task-001"
        assert data["result"]["requestId"] == "req-001"
        assert data["result"]["its"] == 1717000000
        assert data["result"]["objectKey"] == "guineapig/audio/tts/1000000001/202600521/output.mp3"

    def test_missing_object_key(self, mocker):
        """缺少 objectKey 应返回错误响应"""
        resp = handler_task_submit(_make_request(object_key=""))

        import json
        data = json.loads(resp.body)
        assert data["success"] is False
        assert data["errMessage"] == "objectKey 不能为空"

    def test_invalid_object_key_format(self, mocker):
        """objectKey 格式无效时应返回错误响应"""
        resp = handler_task_submit(_make_request(object_key="invalid/key"))

        import json
        data = json.loads(resp.body)
        assert data["success"] is False
        assert "格式无效" in data["errMessage"]

    def test_asr_failure_propagates(self, mocker):
        """ASR 失败时错误应传播到调用方"""
        mocker.patch("app.services.task_service.download_file_from_s3")
        mocker.patch("app.services.task_service.handle_asr", side_effect=RuntimeError("ASR failed"))

        resp = handler_task_submit(_make_request())

        import json
        data = json.loads(resp.body)
        assert data["success"] is False
        assert "ASR failed" in data["errMessage"]

    def test_llm_failure_propagates(self, mocker):
        """LLM 失败时错误应传播到调用方"""
        mocker.patch("app.services.task_service.download_file_from_s3")
        mocker.patch("app.services.task_service.handle_asr", return_value="识别文本")
        mocker.patch("app.services.task_service.get_llm_response", side_effect=RuntimeError("LLM failed"))

        resp = handler_task_submit(_make_request())

        import json
        data = json.loads(resp.body)
        assert data["success"] is False
        assert "LLM failed" in data["errMessage"]

    def test_tts_failure_propagates(self, mocker):
        """TTS 失败时错误应传播到调用方"""
        mocker.patch("app.services.task_service.download_file_from_s3")
        mocker.patch("app.services.task_service.handle_asr", return_value="识别文本")
        mocker.patch("app.services.task_service.get_llm_response", return_value="LLM 回复")
        mocker.patch("app.services.task_service.handle_tts", side_effect=RuntimeError("TTS failed"))

        resp = handler_task_submit(_make_request())

        import json
        data = json.loads(resp.body)
        assert data["success"] is False
        assert "TTS failed" in data["errMessage"]

    def test_upload_failure_propagates(self, mocker):
        """TTS 上传失败时错误应传播到调用方"""
        mocker.patch("app.services.task_service.download_file_from_s3")
        mocker.patch("app.services.task_service.handle_asr", return_value="识别文本")
        mocker.patch("app.services.task_service.get_llm_response", return_value="LLM 回复")
        mocker.patch("app.services.task_service.handle_tts", return_value="/tmp/tts/output.mp3")
        mocker.patch(
            "app.services.task_service.upload_tts_result",
            side_effect=RuntimeError("Upload failed"),
        )

        resp = handler_task_submit(_make_request())

        import json
        data = json.loads(resp.body)
        assert data["success"] is False
        assert "Upload failed" in data["errMessage"]

    def test_download_audio_called(self, mocker):
        """音频不存在时应调用 download_file_from_s3 下载"""
        # Mock os.path.exists 返回 False，模拟音频文件不存在
        original_exists = os.path.exists

        def mock_exists(path):
            if "data/asr" in path or "data/tts" in path:
                return False
            return original_exists(path)

        mocker.patch("app.services.task_service.os.path.exists", side_effect=mock_exists)

        mock_download = mocker.patch("app.services.task_service.download_file_from_s3")
        mocker.patch("app.services.task_service.handle_asr", return_value="文本")
        mocker.patch("app.services.task_service.get_llm_response", return_value="回复")
        mocker.patch("app.services.task_service.handle_tts", return_value="/tmp/tts/output.mp3")
        mocker.patch(
            "app.services.task_service.upload_tts_result",
            return_value="guineapig/audio/tts/1000000001/202600521/output.mp3",
        )

        handler_task_submit(_make_request())

        # 验证 download_file_from_s3 被调用
        mock_download.assert_called()
