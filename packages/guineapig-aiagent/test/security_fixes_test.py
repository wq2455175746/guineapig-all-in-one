"""
P0 安全修复回归测试 — ZIP Slip、zip bomb、S3 ACL、预签名 URL、硬编码凭据、URL 编码。

覆盖 task-1 修复的 5 项安全议题，验证修复行为而非实现细节。
"""

import io
import os
import zipfile

import pytest

from app.config import settings
from app.core.oss import OSS
from app.services import skill_load_service, skill_service
from app.services.network_search_service import search_web
from app.services.zip_utils import (
    MAX_EXTRACT_FILE_COUNT,
    MAX_EXTRACT_TOTAL_SIZE,
    UnsafeZipError,
    extract_zip_safe,
    safe_zip_target,
)


def _make_zip(entries: dict) -> zipfile.ZipFile:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    buf.seek(0)
    return zipfile.ZipFile(buf, "r")


class TestZipSlip:
    """ZIP Slip 路径穿越防护"""

    def test_normal_extraction(self, tmp_path):
        """正常 zip 应完整解压，公共顶层目录被剥离"""
        zf = _make_zip({"skill/SKILL.md": b"# hi", "skill/scripts/run.py": b"print(1)"})
        extracted, total = extract_zip_safe(zf, str(tmp_path))
        names = {p for _, p in extracted}
        assert names == {"SKILL.md", "scripts/run.py"}
        assert (tmp_path / "SKILL.md").exists()
        assert (tmp_path / "scripts" / "run.py").exists()
        assert total == len(b"# hi") + len(b"print(1)")

    def test_flat_zip_no_prefix(self, tmp_path):
        """无公共目录的 zip 保持原路径"""
        zf = _make_zip({"a.txt": b"1", "dir/b.txt": b"2"})
        extracted, _ = extract_zip_safe(zf, str(tmp_path))
        names = {p for _, p in extracted}
        assert names == {"a.txt", "dir/b.txt"}

    def test_traversal_rejected(self, tmp_path):
        """../ 路径穿越应被拒绝"""
        zf = _make_zip({"../evil.txt": b"x"})
        with pytest.raises(UnsafeZipError):
            extract_zip_safe(zf, str(tmp_path))
        assert not (tmp_path.parent / "evil.txt").exists()

    def test_nested_traversal_rejected(self, tmp_path):
        """嵌套 .. 段应被拒绝"""
        zf = _make_zip({"a/../../evil.txt": b"x"})
        with pytest.raises(UnsafeZipError):
            extract_zip_safe(zf, str(tmp_path))

    def test_traversal_inside_common_prefix(self, tmp_path):
        """公共前缀剥离后出现的 .. 段仍应被拒绝"""
        zf = _make_zip({"skill/../../evil.txt": b"x", "skill/SKILL.md": b"# hi"})
        with pytest.raises(UnsafeZipError):
            extract_zip_safe(zf, str(tmp_path))

    def test_absolute_path_rejected(self, tmp_path):
        """绝对路径应被拒绝"""
        zf = _make_zip({"/etc/passwd": b"x"})
        with pytest.raises(UnsafeZipError):
            extract_zip_safe(zf, str(tmp_path))

    def test_backslash_traversal_rejected(self, tmp_path):
        """反斜杠形式的 .. 段应被拒绝"""
        zf = _make_zip({r"..\evil.txt": b"x"})
        with pytest.raises(UnsafeZipError):
            extract_zip_safe(zf, str(tmp_path))

    def test_prefix_confusion_rejected(self, tmp_path):
        """解析后落在 extract_dir 同名兄弟目录的路径应被拒绝（前缀误匹配）"""
        # extract_dir=/tmp/x/out，member=../out_evil.txt → normpath=/tmp/x/out_evil.txt
        out_dir = tmp_path / "out"
        target = safe_zip_target(str(out_dir), "../out_evil.txt")
        assert target is None

    def test_safe_zip_target_ok(self, tmp_path):
        """合法相对路径应返回 extract_dir 下的目标"""
        target = safe_zip_target(str(tmp_path), "scripts/run.py")
        assert target == str(tmp_path / "scripts" / "run.py")

    def test_symlink_not_created(self, tmp_path):
        """zip 中的符号链接条目只能作为普通文件写入，不会创建真实链接"""
        zf = _make_zip({"skill/link": b"../outside.txt"})
        extract_zip_safe(zf, str(tmp_path))
        assert (tmp_path / "link").is_file()


class TestZipBomb:
    """zip bomb（大小/条目数）防护"""

    def test_too_many_files_rejected(self, tmp_path):
        """超过条目数上限应报错"""
        zf = _make_zip({f"f{i}.txt": b"x" for i in range(3)})
        with pytest.raises(UnsafeZipError):
            extract_zip_safe(zf, str(tmp_path), max_file_count=2)

    def test_too_large_rejected(self, tmp_path):
        """超过解压总大小上限应报错"""
        zf = _make_zip({"big.bin": b"x" * 100})
        with pytest.raises(UnsafeZipError):
            extract_zip_safe(zf, str(tmp_path), max_total_size=10)

    def test_default_limits(self):
        """默认上限应为 100MB / 1000 文件"""
        assert MAX_EXTRACT_TOTAL_SIZE == 100 * 1024 * 1024
        assert MAX_EXTRACT_FILE_COUNT == 1000


class TestSharedZipGuard:
    """两处解压代码应共用同一个安全解压实现"""

    def test_both_services_use_shared_guard(self):
        from app.services.zip_utils import extract_zip_safe as shared

        assert skill_load_service.extract_zip_safe is shared
        assert skill_service.extract_zip_safe is shared


class TestS3Acl:
    """S3 上传不再显式 public-read"""

    def _oss(self, mocker):
        oss = object.__new__(OSS)
        oss.bucket_name = "test-bucket"
        oss.s3_client = mocker.MagicMock()
        return oss

    def test_create_folder_no_public_acl(self, mocker):
        oss = self._oss(mocker)
        oss.create_folder("user/1/")
        oss.s3_client.put_object.assert_called_once()
        assert "ACL" not in oss.s3_client.put_object.call_args.kwargs

    def test_upload_small_file_no_public_acl(self, mocker, tmp_path):
        oss = self._oss(mocker)
        f = tmp_path / "audio.wav"
        f.write_bytes(b"fake-audio")
        assert oss._upload_small_file(str(f), "audio/1.wav")
        oss.s3_client.put_object.assert_called_once()
        assert "ACL" not in oss.s3_client.put_object.call_args.kwargs

    def test_upload_small_file_obj_no_public_acl(self, mocker):
        oss = self._oss(mocker)
        assert oss._upload_small_file_obj(io.BytesIO(b"fake-audio"), "audio/2.wav")
        oss.s3_client.put_object.assert_called_once()
        assert "ACL" not in oss.s3_client.put_object.call_args.kwargs


class TestPresignedUrl:
    """预签名 URL 应保留签名参数"""

    def test_returns_full_presigned_url(self, mocker):
        oss = object.__new__(OSS)
        oss.bucket_name = "test-bucket"
        oss.s3_client = mocker.MagicMock()
        full_url = "https://oss.example.com/audio/1.wav?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Expires=604800&X-Amz-Signature=abc123"
        oss.s3_client.generate_presigned_url.return_value = full_url

        result = oss.get_object_url("audio/1.wav")

        assert result == full_url
        assert "X-Amz-Signature" in result
        oss.s3_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "test-bucket", "Key": "audio/1.wav"},
            ExpiresIn=3600 * 24 * 7,
        )


class TestHardcodedCredentials:
    """配置中不应存在硬编码占位凭据"""

    def test_no_placeholder_secret_key(self):
        assert settings.SECRET_KEY != "your-secret-key-change-in-production"

    def test_no_placeholder_oss_credentials(self):
        assert settings.OSS_AK != "xxxx"
        assert settings.OSS_SK != "xxxx"


class TestSearchUrlEncoding:
    """网络搜索查询应通过 params 传参，而非拼接进 URL"""

    @pytest.mark.asyncio
    async def test_query_encoded_via_params(self, mocker):
        resp_mock = mocker.MagicMock()
        resp_mock.json.return_value = {
            "results": [{"title": "t", "url": "http://e", "content": "c"}]
        }
        client_mock = mocker.MagicMock()
        client_mock.get = mocker.AsyncMock(return_value=resp_mock)
        client_mock.__aenter__ = mocker.AsyncMock(return_value=client_mock)
        client_mock.__aexit__ = mocker.AsyncMock(return_value=False)
        mocker.patch(
            "app.services.network_search_service.httpx.AsyncClient",
            return_value=client_mock,
        )

        result = await search_web("今天天气怎么样")

        assert "1. [t](http://e)" in result
        url = client_mock.get.call_args.args[0]
        params = client_mock.get.call_args.kwargs.get("params")
        assert url == f"{settings.SEARXNG_URL}/search"
        assert "?" not in url
        assert params == {"q": "今天天气怎么样", "format": "json", "language": "zh"}
        assert "今天天气怎么样" not in url