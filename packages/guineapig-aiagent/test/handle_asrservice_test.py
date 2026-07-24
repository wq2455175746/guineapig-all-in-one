"""
ASR 原子能力单元测试
"""

import os
import sys

import pytest

# 将项目根目录加入 sys.path，使 from app.xxx 能正常导入
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.services.handle_asrservice import handle_asr


class TestHandleAsr:
    """handle_asr 单元测试"""

    def test_success(self, mocker, tmp_path):
        """正常 ASR 识别应返回文本"""
        # 准备: 创建临时音频文件
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio data")

        # Mock requests.post
        mock_resp = mocker.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "你好世界"}
        mock_post = mocker.patch("app.services.handle_asrservice.requests.post", return_value=mock_resp)

        # 执行
        result = handle_asr(str(audio_path))

        # 验证
        assert result == "你好世界"
        mock_post.assert_called_once()

    def test_file_not_found(self, mocker):
        """音频文件不存在时应抛出 FileNotFoundError"""
        with pytest.raises(FileNotFoundError, match="ASR 输入音频文件不存在"):
            handle_asr("/nonexistent/path/audio.mp3")

    def test_api_error(self, mocker, tmp_path):
        """ASR API 返回非 200 时应抛出 RuntimeError"""
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio data")

        mock_resp = mocker.MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mocker.patch("app.services.handle_asrservice.requests.post", return_value=mock_resp)

        with pytest.raises(RuntimeError, match="ASR API 返回 500"):
            handle_asr(str(audio_path))

    def test_empty_text_response(self, mocker, tmp_path):
        """ASR API 返回空文本时应返回空字符串"""
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio data")

        mock_resp = mocker.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        mocker.patch("app.services.handle_asrservice.requests.post", return_value=mock_resp)

        result = handle_asr(str(audio_path))
        assert result == ""
