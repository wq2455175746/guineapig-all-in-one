"""工具输出截断 — 双限制 / 双向策略 / UTF-8 边界安全。"""

from app.agent.executor.truncate import (
    TruncationResult,
    truncate_head,
    truncate_tail,
    truncate_line,
    truncate_tool_result,
    truncation_mode,
)


class TestNoTruncation:
    def test_small_content_untouched(self):
        r = truncate_tail("line1\nline2", max_lines=10, max_bytes=1000)
        assert r.truncated is False
        assert r.content == "line1\nline2"
        assert r.total_lines == 2
        assert r.output_lines == 2

    def test_empty_content(self):
        r = truncate_head("", max_lines=10, max_bytes=1000)
        assert r.truncated is False
        assert r.content == ""


class TestLineLimit:
    def test_tail_keeps_last_lines(self):
        text = "\n".join(f"line{i}" for i in range(1, 11))
        r = truncate_tail(text, max_lines=3, max_bytes=10_000)
        assert r.truncated is True
        assert r.truncated_by == "lines"
        assert r.output_lines == 3
        assert r.total_lines == 10
        assert r.content.endswith("line10")
        assert "line8" in r.content
        assert "line7" not in r.content

    def test_head_keeps_first_lines(self):
        text = "\n".join(f"line{i}" for i in range(1, 11))
        r = truncate_head(text, max_lines=3, max_bytes=10_000)
        assert r.truncated is True
        assert r.truncated_by == "lines"
        assert r.content.startswith("line1")
        assert "line3" in r.content
        assert "line4" not in r.content


class TestByteLimit:
    def test_tail_byte_limit(self):
        text = "a" * 1000
        r = truncate_tail(text, max_lines=10_000, max_bytes=100)
        assert r.truncated is True
        assert r.truncated_by == "bytes"
        assert r.output_bytes <= 100

    def test_head_byte_limit(self):
        text = "abcdefghij" * 100
        r = truncate_head(text, max_lines=10_000, max_bytes=50)
        assert r.truncated is True
        assert r.output_bytes <= 50
        assert r.content == "abcdefghij" * 5


class TestUtf8Safety:
    def test_tail_emoji_not_split(self):
        text = "😀" * 100  # 每个 4 字节
        r = truncate_tail(text, max_lines=10_000, max_bytes=10)
        # 10 字节最多容纳 2 个 emoji（8 字节），结果必须是合法 UTF-8
        assert r.output_bytes <= 10
        assert "�" not in r.content
        assert all(ch == "😀" for ch in r.content)

    def test_head_emoji_not_split(self):
        text = "😀" * 100
        r = truncate_head(text, max_lines=10_000, max_bytes=6)
        assert "�" not in r.content
        assert r.content == "😀"


class TestSingleHugeLine:
    def test_head_single_line_exceeds(self):
        r = truncate_head("x" * 1000, max_lines=5, max_bytes=100)
        assert r.truncated is True
        assert r.line_partial is True
        assert r.output_bytes <= 100

    def test_tail_single_line_exceeds(self):
        r = truncate_tail("x" * 1000, max_lines=5, max_bytes=100)
        assert r.truncated is True
        assert r.line_partial is True
        assert r.output_bytes <= 100


class TestTruncateLine:
    def test_short_line_unchanged(self):
        assert truncate_line("short", max_length=500) == "short"

    def test_long_line_marked(self):
        out = truncate_line("a" * 600, max_length=500)
        assert len(out) <= 500 + len("... [truncated]")
        assert out.endswith("... [truncated]")


class TestToolResultIntegration:
    def test_head_capability_for_rag(self):
        assert truncation_mode("rag") == "head"
        assert truncation_mode("web_search") == "head"
        assert truncation_mode("mcp_filesystem") == "tail"
        assert truncation_mode("cli") == "tail"

    def test_result_truncated_and_notice_added(self):
        result = {"result": "line\n" * 5000, "count": 1}
        out = truncate_tool_result(result, "rag", enabled=True, max_lines=10, max_bytes=10_000)
        assert out["truncated"] is True
        assert "输出已截断" in out["result"]
        assert out["count"] == 1

    def test_disabled_returns_original(self):
        result = {"result": "x" * 100000}
        out = truncate_tool_result(result, "rag", enabled=False)
        assert out is result

    def test_non_string_result_untouched(self):
        result = {"result": {"nested": 1}}
        out = truncate_tool_result(result, "rag", enabled=True, max_lines=10, max_bytes=10)
        assert out is result


def test_truncation_settings_defaults():
    from app.config import settings

    assert settings.AGENT_TOOL_OUTPUT_TRUNCATION_ENABLED is True
    assert settings.AGENT_TOOL_OUTPUT_MAX_LINES == 2000
    assert settings.AGENT_TOOL_OUTPUT_MAX_BYTES == 51200
