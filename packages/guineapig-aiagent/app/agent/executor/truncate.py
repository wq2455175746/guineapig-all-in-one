"""工具输出截断 — 双重限制（行数 + 字节），双向策略（head/tail），UTF-8 边界安全。

移植自 pi-agent `packages/coding-agent/src/core/tools/truncate.ts`。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.log import logger

DEFAULT_MAX_LINES = 2000
DEFAULT_MAX_BYTES = 50 * 1024
GREP_MAX_LINE_LENGTH = 500

# 检索/知识类能力：开头信息密度最高，保留头部
HEAD_CAPABILITIES = {
    "web_search",
    "rag",
    "memory",
    "memory_retrieve",
    "memory_summarize",
}


@dataclass
class TruncationResult:
    content: str
    truncated: bool = False
    truncated_by: str | None = None  # "lines" | "bytes" | None
    total_lines: int = 0
    output_lines: int = 0
    total_bytes: int = 0
    output_bytes: int = 0
    line_partial: bool = False


def _byte_len(text: str) -> int:
    return len(text.encode("utf-8"))


def _truncate_str_from_start(text: str, max_bytes: int) -> str:
    """保留字符串**前** max_bytes 字节，且不切断多字节字符。"""
    data = text.encode("utf-8")
    if len(data) <= max_bytes:
        return text
    sliced = data[:max_bytes]
    for cut in range(0, 4):
        candidate = sliced[: len(sliced) - cut] if cut else sliced
        try:
            return candidate.decode("utf-8")
        except UnicodeDecodeError:
            continue
    return sliced.decode("utf-8", errors="ignore")


def _truncate_str_from_end(text: str, max_bytes: int) -> str:
    """保留字符串**后** max_bytes 字节，且不切断多字节字符。"""
    data = text.encode("utf-8")
    if len(data) <= max_bytes:
        return text
    sliced = data[len(data) - max_bytes:]
    for cut in range(0, 4):
        candidate = sliced[cut:]
        try:
            return candidate.decode("utf-8")
        except UnicodeDecodeError:
            continue
    return sliced.decode("utf-8", errors="ignore")


def truncate_head(
    content: str,
    max_lines: int = DEFAULT_MAX_LINES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> TruncationResult:
    """从前往后保留（检索类结果用）。"""
    if content is None:
        content = ""
    total_bytes = _byte_len(content)
    lines = content.split("\n")
    total_lines = len(lines)

    if total_lines <= max_lines and total_bytes <= max_bytes:
        return TruncationResult(
            content=content,
            total_lines=total_lines,
            output_lines=total_lines,
            total_bytes=total_bytes,
            output_bytes=total_bytes,
        )

    kept: list[str] = []
    out_bytes = 0
    truncated_by: str | None = None
    line_partial = False

    for line in lines:
        if len(kept) >= max_lines:
            truncated_by = "lines"
            break
        line_bytes = _byte_len(line) + 1  # +1 换行
        if out_bytes + line_bytes > max_bytes:
            truncated_by = "bytes"
            if not kept:
                piece = _truncate_str_from_start(line, max_bytes)
                kept.append(piece)
                out_bytes = _byte_len(piece)
                line_partial = True
            break
        kept.append(line)
        out_bytes += line_bytes

    output = "\n".join(kept)
    return TruncationResult(
        content=output,
        truncated=True,
        truncated_by=truncated_by,
        total_lines=total_lines,
        output_lines=len(kept),
        total_bytes=total_bytes,
        output_bytes=_byte_len(output),
        line_partial=line_partial,
    )


def truncate_tail(
    content: str,
    max_lines: int = DEFAULT_MAX_LINES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> TruncationResult:
    """从后往前保留（命令/执行类结果用，错误堆栈在末尾）。"""
    if content is None:
        content = ""
    total_bytes = _byte_len(content)
    lines = content.split("\n")
    total_lines = len(lines)

    if total_lines <= max_lines and total_bytes <= max_bytes:
        return TruncationResult(
            content=content,
            total_lines=total_lines,
            output_lines=total_lines,
            total_bytes=total_bytes,
            output_bytes=total_bytes,
        )

    kept: list[str] = []
    out_bytes = 0
    truncated_by: str | None = None
    line_partial = False

    for line in reversed(lines):
        if len(kept) >= max_lines:
            truncated_by = "lines"
            break
        line_bytes = _byte_len(line) + 1
        if out_bytes + line_bytes > max_bytes:
            truncated_by = "bytes"
            if not kept:
                piece = _truncate_str_from_end(line, max_bytes)
                kept.insert(0, piece)
                out_bytes = _byte_len(piece)
                line_partial = True
            break
        kept.insert(0, line)
        out_bytes += line_bytes

    output = "\n".join(kept)
    return TruncationResult(
        content=output,
        truncated=True,
        truncated_by=truncated_by,
        total_lines=total_lines,
        output_lines=len(kept),
        total_bytes=total_bytes,
        output_bytes=_byte_len(output),
        line_partial=line_partial,
    )


def truncate_line(line: str, max_length: int = GREP_MAX_LINE_LENGTH) -> str:
    """截断超长单行（grep/minified 输出），附标记。"""
    if len(line) <= max_length:
        return line
    return line[:max_length] + "... [truncated]"


def truncation_mode(capability: str) -> str:
    """检索类保留头部，其余保留末尾。"""
    return "head" if capability in HEAD_CAPABILITIES else "tail"


def build_notice(result: TruncationResult, mode: str) -> str:
    if not result.truncated:
        return ""
    if result.line_partial:
        if mode == "head":
            return (
                f"... [输出已截断：单行超长，仅保留前 {result.output_bytes} 字节；"
                f"原始 {result.total_bytes} 字节]"
            )
        return (
            f"... [输出已截断：单行超长，仅保留末 {result.output_bytes} 字节；"
            f"原始 {result.total_bytes} 字节]"
        )
    if mode == "head":
        return (
            f"... [输出已截断：显示前 {result.output_lines}/{result.total_lines} 行，"
            f"{result.output_bytes}/{result.total_bytes} 字节]"
        )
    return (
        f"... [输出已截断：显示后 {result.output_lines}/{result.total_lines} 行，"
        f"{result.output_bytes}/{result.total_bytes} 字节]"
    )


def truncate_tool_result(
    result,
    capability: str,
    *,
    enabled: bool = True,
    max_lines: int = DEFAULT_MAX_LINES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict:
    """对 handle/委托结果的 `result` 文本字段做截断；非文本或未超限时原样返回。"""
    if not enabled or not isinstance(result, dict):
        return result
    text = result.get("result")
    if not isinstance(text, str) or not text:
        return result

    mode = truncation_mode(capability)
    if mode == "head":
        tr = truncate_head(text, max_lines=max_lines, max_bytes=max_bytes)
    else:
        tr = truncate_tail(text, max_lines=max_lines, max_bytes=max_bytes)

    if not tr.truncated:
        return result

    new_result = dict(result)
    new_result["result"] = tr.content + "\n\n" + build_notice(tr, mode)
    new_result["truncated"] = True
    logger.info(
        f"[Truncate] capability={capability} mode={mode} 截断输出: "
        f"{tr.output_bytes}/{tr.total_bytes} 字节, "
        f"{tr.output_lines}/{tr.total_lines} 行"
    )
    return new_result
