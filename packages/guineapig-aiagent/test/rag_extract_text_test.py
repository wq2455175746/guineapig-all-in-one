"""extract_document_text 文件解析分派测试。

txt/md/html 直接按文本读取；docx/xlsx/pptx 等 14 种格式走 anydoc 解析；
未知扩展名（需要 OCR 的图片/音频等）抛出异常。
"""

import sys
import types

import pytest

from app.services.rag_service import extract_document_text


class TestExtractDocumentText:
    def test_txt_read_directly(self, tmp_path):
        p = tmp_path / "a.txt"
        p.write_text("你好 hello", encoding="utf-8")
        assert extract_document_text(str(p)) == "你好 hello"

    def test_markdown_read_directly(self, tmp_path):
        p = tmp_path / "a.md"
        p.write_text("# 标题\n正文", encoding="utf-8")
        assert extract_document_text(str(p)) == "# 标题\n正文"

    def test_html_read_directly(self, tmp_path):
        p = tmp_path / "a.html"
        p.write_text("<p>hi</p>", encoding="utf-8")
        assert extract_document_text(str(p)) == "<p>hi</p>"

    def test_gbk_fallback(self, tmp_path):
        p = tmp_path / "a.txt"
        p.write_bytes("中文内容".encode("gbk"))
        assert extract_document_text(str(p)) == "中文内容"

    @pytest.mark.parametrize(
        "ext",
        ["docx", "doc", "docm", "xlsx", "xls", "xlsm", "pptx", "ppt",
         "rtf", "odt", "ods", "odp", "epub", "csv", "pdf"],
    )
    def test_anydoc_formats_use_anydoc(self, tmp_path, monkeypatch, ext):
        p = tmp_path / f"a.{ext}"
        p.write_text("raw", encoding="utf-8")

        called = {}

        def fake_to_markdown(path):
            called["path"] = path
            return f"# parsed {ext}"

        fake_anydoc = types.ModuleType("anydoc")
        fake_anydoc.to_markdown = fake_to_markdown
        monkeypatch.setitem(sys.modules, "anydoc", fake_anydoc)

        assert extract_document_text(str(p)) == f"# parsed {ext}"
        assert called["path"] == str(p)

    def test_unknown_extension_raises(self, tmp_path):
        p = tmp_path / "a.png"
        p.write_bytes(b"\x89PNG")
        with pytest.raises(ValueError):
            extract_document_text(str(p))

    def test_case_insensitive_extension(self, tmp_path, monkeypatch):
        p = tmp_path / "A.DOCX"
        p.write_text("raw", encoding="utf-8")

        fake_anydoc = types.ModuleType("anydoc")
        fake_anydoc.to_markdown = lambda path: "parsed"
        monkeypatch.setitem(sys.modules, "anydoc", fake_anydoc)

        assert extract_document_text(str(p)) == "parsed"
