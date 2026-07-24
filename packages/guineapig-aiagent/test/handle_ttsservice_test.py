"""
TTS 原子能力单元测试
"""

import os
import subprocess
import sys

import pytest

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


class TestHandleTts:
    """handle_tts 单元测试"""

    def test_success(self, mocker, tmp_path):
        """正常 TTS 合成应返回 MP3 文件路径"""
        tts_dir = tmp_path / "tts"
        prompt_wav = tmp_path / "prompt.wav"
        prompt_wav.write_bytes(b"fake wav data")

        # Mock requests.post — 返回 raw 音频数据
        mock_resp = mocker.MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"fake raw audio data"
        mocker.patch("app.services.handle_ttsservice.requests.post", return_value=mock_resp)

        # Mock subprocess.run — ffmpeg 成功
        mock_run = mocker.patch("app.services.handle_ttsservice.subprocess.run")
        mock_run.return_value.returncode = 0

        import app.services.handle_ttsservice as tts_service

        result = tts_service.handle_tts("测试文本", str(tts_dir), str(prompt_wav))

        # 验证返回路径
        expected_mp3 = os.path.join(str(tts_dir), "output.mp3")
        assert result == expected_mp3

    def test_missing_prompt_wav(self, mocker, tmp_path):
        """参考音频不存在时应抛出 FileNotFoundError"""
        import app.services.handle_ttsservice as tts_service

        with pytest.raises(FileNotFoundError, match="TTS 参考音频不存在"):
            tts_service.handle_tts("测试文本", str(tmp_path / "tts"), "/nonexistent/prompt.wav")

    def test_api_error(self, mocker, tmp_path):
        """TTS API 返回非 200 时应抛出 RuntimeError"""
        tts_dir = tmp_path / "tts"
        prompt_wav = tmp_path / "prompt.wav"
        prompt_wav.write_bytes(b"fake wav data")

        mock_resp = mocker.MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "TTS Error"
        mocker.patch("app.services.handle_ttsservice.requests.post", return_value=mock_resp)

        import app.services.handle_ttsservice as tts_service

        with pytest.raises(RuntimeError, match="TTS API 返回 500"):
            tts_service.handle_tts("测试文本", str(tts_dir), str(prompt_wav))

    def test_ffmpeg_failure(self, mocker, tmp_path):
        """ffmpeg 转换失败时应抛出 RuntimeError"""
        tts_dir = tmp_path / "tts"
        prompt_wav = tmp_path / "prompt.wav"
        prompt_wav.write_bytes(b"fake wav data")

        mock_resp = mocker.MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"fake raw audio data"
        mocker.patch("app.services.handle_ttsservice.requests.post", return_value=mock_resp)

        mock_run = mocker.patch("app.services.handle_ttsservice.subprocess.run")
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "ffmpeg error"

        import app.services.handle_ttsservice as tts_service

        with pytest.raises(RuntimeError, match="ffmpeg 转换失败"):
            tts_service.handle_tts("测试文本", str(tts_dir), str(prompt_wav))


class TestUploadTtsResult:
    """upload_tts_result 单元测试"""

    def test_success(self, mocker):
        """正常上传应返回 S3 远程路径"""
        mock_upload = mocker.patch(
            "app.services.handle_ttsservice.upload_doc_to_s3_and_get_path",
            return_value="audio/tts/1000000001/202600521/output.mp3",
        )

        import app.services.handle_ttsservice as tts_service

        result = tts_service.upload_tts_result("/tmp/output.mp3", "1000000001", "202600521")

        assert result == "audio/tts/1000000001/202600521/output.mp3"
        mock_upload.assert_called_once_with(
            file_obj_or_path="/tmp/output.mp3",
            project_id="audio/tts",
            file_path="1000000001/202600521",
            filename="output.mp3",
        )

    def test_upload_failure_propagates(self, mocker):
        """上传失败时应传播异常"""
        mocker.patch(
            "app.services.handle_ttsservice.upload_doc_to_s3_and_get_path",
            side_effect=RuntimeError("S3 upload failed"),
        )

        import app.services.handle_ttsservice as tts_service

        with pytest.raises(RuntimeError, match="S3 upload failed"):
            tts_service.upload_tts_result("/tmp/output.mp3", "1000000001", "202600521")
