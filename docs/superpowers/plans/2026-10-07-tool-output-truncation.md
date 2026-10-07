# 工具输出截断 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 DAG 步骤产出（server handler 结果与 client delegate 结果）增加"双重限制（行数 + 字节）+ 双向策略（head/tail）+ UTF-8 边界安全 + 截断提示"的输出截断，防止单条超大结果通过 `{{step.result}}` 注入撑爆后续 LLM 上下文。

**Architecture:** 移植 pi-agent `packages/coding-agent/src/core/tools/truncate.ts` 的算法到 `app/agent/executor/truncate.py`（纯函数、零依赖）。引擎在把结果写入 `self.step_results` 之前调用 `truncate_tool_result(result, capability)`，按能力选择 head（检索类，保留开头）/ tail（执行类，保留末尾）。

**Tech Stack:** Python 3.13, loguru, pydantic-settings, pytest。

**Spec:** `docs/design-docs/pi-agent-borrowable-ideas.md`（#12 双向截断 + 双限制）

## Global Constraints

- 算法必须 UTF-8 安全：多字节字符（emoji、中文）不得被切成无效码元。
- 截断必须**有提示**：追加一行 `... [输出已截断：...]`，让模型知道自己看到的是片段。
- 不改变成功结果的结构：仅在 `result` 字段追加提示，并新增 `truncated: true` 标记。
- 默认开启截断，阈值为行 2000 / 字节 51200（50KB），与 pi 默认一致。
- 阈值与开关走 `settings`（可配）。
- 测试命令：`cd packages/guineapig-aiagent && uv run pytest -q`。

> 若已实施「错误即消息」计划，本计划对 `engine.py::_execute_step` 的改动需要与其合并（两者都改写成功结果存储段）。

---

## File Structure

- **Create** `packages/guineapig-aiagent/app/agent/executor/truncate.py` — 截断算法与集成函数。
- **Modify** `packages/guineapig-aiagent/app/config.py` — 3 个截断配置项。
- **Modify** `packages/guineapig-aiagent/app/agent/executor/engine.py` — server 结果与 client delegate 结果两处接入。
- **Test** `packages/guineapig-aiagent/test/tool_output_truncation_test.py`

---

## Task 1: 截断算法模块

**Files:**
- Create: `packages/guineapig-aiagent/app/agent/executor/truncate.py`
- Test: `packages/guineapig-aiagent/test/tool_output_truncation_test.py`

**Interfaces:**
- Produces:
  - `TruncationResult(content, truncated, truncated_by, total_lines, output_lines, total_bytes, output_bytes, line_partial)`
  - `truncate_head(content, max_lines=2000, max_bytes=51200) -> TruncationResult`
  - `truncate_tail(content, max_lines=2000, max_bytes=51200) -> TruncationResult`
  - `truncate_line(line, max_length=500) -> str`
  - `truncate_tool_result(result: dict, capability: str, *, enabled=True, max_lines=..., max_bytes=...) -> dict`
  - `truncation_mode(capability: str) -> "head" | "tail"`
  - 常量 `DEFAULT_MAX_LINES=2000`、`DEFAULT_MAX_BYTES=50*1024`、`GREP_MAX_LINE_LENGTH=500`、`HEAD_CAPABILITIES`

- [ ] **Step 1: 写失败测试**

Create `packages/guineapig-aiagent/test/tool_output_truncation_test.py`:

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/guineapig-aiagent && uv run pytest test/tool_output_truncation_test.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agent.executor.truncate'`

- [ ] **Step 3: 实现 truncate.py**

Create `packages/guineapig-aiagent/app/agent/executor/truncate.py`:

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd packages/guineapig-aiagent && uv run pytest test/tool_output_truncation_test.py -q`
Expected: PASS（全部用例）

- [ ] **Step 5: 提交**

```bash
git add packages/guineapig-aiagent/app/agent/executor/truncate.py packages/guineapig-aiagent/test/tool_output_truncation_test.py
git commit -m "feat(aiagent): add tool output truncation algorithm (port of pi truncate.ts)"
```

---

## Task 2: 截断配置项

**Files:**
- Modify: `packages/guineapig-aiagent/app/config.py`（LLM 配置段后）
- Test: `packages/guineapig-aiagent/test/tool_output_truncation_test.py`（追加）

**Interfaces:**
- Produces: `settings.AGENT_TOOL_OUTPUT_TRUNCATION_ENABLED: bool = True`、`settings.AGENT_TOOL_OUTPUT_MAX_LINES: int = 2000`、`settings.AGENT_TOOL_OUTPUT_MAX_BYTES: int = 51200`

- [ ] **Step 1: 写失败测试**

追加：

```python
def test_truncation_settings_defaults():
    from app.config import settings

    assert settings.AGENT_TOOL_OUTPUT_TRUNCATION_ENABLED is True
    assert settings.AGENT_TOOL_OUTPUT_MAX_LINES == 2000
    assert settings.AGENT_TOOL_OUTPUT_MAX_BYTES == 51200
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/guineapig-aiagent && uv run pytest test/tool_output_truncation_test.py::test_truncation_settings_defaults -q`
Expected: FAIL — `AttributeError: AGENT_TOOL_OUTPUT_TRUNCATION_ENABLED`

- [ ] **Step 3: 修改 config.py**

在 `LLM_RETRY_BACKOFF` 之后追加：

```python
    # DAG 工具输出截断：防止单条超大结果撑爆后续 LLM 上下文
    AGENT_TOOL_OUTPUT_TRUNCATION_ENABLED: bool = True
    AGENT_TOOL_OUTPUT_MAX_LINES: int = 2000
    AGENT_TOOL_OUTPUT_MAX_BYTES: int = 51200  # 50KB
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd packages/guineapig-aiagent && uv run pytest test/tool_output_truncation_test.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add packages/guineapig-aiagent/app/config.py packages/guineapig-aiagent/test/tool_output_truncation_test.py
git commit -m "feat(aiagent): add tool output truncation settings"
```

---

## Task 3: 引擎接入截断（server 结果 + client delegate 结果）

**Files:**
- Modify: `packages/guineapig-aiagent/app/agent/executor/engine.py`（`_execute_step`）
- Test: `packages/guineapig-aiagent/test/tool_output_truncation_test.py`（追加）

**Interfaces:**
- Consumes: `truncate_tool_result`、`settings.AGENT_TOOL_OUTPUT_*`
- Produces: 超大结果写入 `step_results` 前被截断并打标记。

- [ ] **Step 1: 写失败测试**

追加：

```python
import pytest

from app.agent.models import DAGDefinition, DAGStep
from app.agent.executor.engine import DAGExecutionEngine
from app.agent.executor import handlers as handlers_mod


@pytest.mark.asyncio
async def test_engine_truncates_huge_server_result(mocker):
    async def huge(capability, params):
        return {"result": "line\n" * 100000, "count": 1}

    mocker.patch.object(handlers_mod.CapabilityHandlers, "execute", side_effect=huge)
    dag = DAGDefinition(
        steps=[DAGStep(step_id="s1", capability="rag", action="x", max_retries=0)],
        original_intent="t",
    )
    engine = DAGExecutionEngine(dag)
    _ = [e async for e in engine.execute()]

    stored = engine.step_results["s1"]
    assert stored["truncated"] is True
    assert "输出已截断" in stored["result"]
    assert len(stored["result"]) < 100_000
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/guineapig-aiagent && uv run pytest test/tool_output_truncation_test.py::test_engine_truncates_huge_server_result -q`
Expected: FAIL — `KeyError: 'truncated'`

- [ ] **Step 3: 修改 engine.py**

顶部导入：

```python
from app.config import settings
from .truncate import truncate_tool_result
```

新增私有方法（放在 `_execute_step` 之前）：

```python
    def _truncate_result(self, result: dict, capability: str) -> dict:
        return truncate_tool_result(
            result,
            capability,
            enabled=settings.AGENT_TOOL_OUTPUT_TRUNCATION_ENABLED,
            max_lines=settings.AGENT_TOOL_OUTPUT_MAX_LINES,
            max_bytes=settings.AGENT_TOOL_OUTPUT_MAX_BYTES,
        )
```

**Server 路径**：在成功分支 `self.step_results[step.step_id] = result` 之前插入：

```python
            result = self._truncate_result(result, step.capability)
```

**Client 路径**：把 `result_data = delegate_result.get("result", {})` 改为：

```python
                    result_data = self._truncate_result(
                        delegate_result.get("result", {}) or {}, step.capability
                    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd packages/guineapig-aiagent && uv run pytest test/tool_output_truncation_test.py test/executor_engine_test.py -q`
Expected: PASS（截断测试 + 既有引擎测试全绿）

- [ ] **Step 5: 运行整个 aiagent 测试套件**

Run: `cd packages/guineapig-aiagent && uv run pytest -q --ignore=test/routers_agent_test.py`
Expected: PASS（无回归）

- [ ] **Step 6: 提交**

```bash
git add packages/guineapig-aiagent/app/agent/executor/engine.py packages/guineapig-aiagent/test/tool_output_truncation_test.py
git commit -m "feat(aiagent): truncate oversized server/client tool results before storing"
```

---

## Self-Review

- **Spec coverage:** #12 双向截断 → `truncate_head`/`truncate_tail`；双限制 → 行数 + 字节谁先触发谁赢；UTF-8 边界安全 → `_truncate_str_from_start/end` + 测试；逃生提示 → `build_notice`；接入 → Task 3 覆盖 server + client 两条结果路径。
- **Placeholder scan:** 无占位；测试与实现均为完整代码。
- **Type consistency:** `TruncationResult` 字段在 head/tail/notice 中一致；`truncate_tool_result` 返回 dict 且保留原字段。
- **配置一致:** `settings.AGENT_TOOL_OUTPUT_*` 在 config.py、engine.py、测试中命名一致。

## Open Questions

- [ ] 是否需要新增 `HEAD_CAPABILITIES` 配置化（目前硬编码）？
- [ ] client 端在本地截断是否更省带宽？（当前仅在服务端收到后截断，带宽未优化）
