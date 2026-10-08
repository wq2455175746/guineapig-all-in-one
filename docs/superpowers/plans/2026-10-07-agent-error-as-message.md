# 错误即消息 + 错误分层 & DAG 自纠错 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 DAG 执行引擎在步骤失败时把结构化错误"当作消息"回喂给一个受限的 re-planner，产出并执行修正步骤，从而具备自纠错能力；同时把错误信息分层（工具层具体化 + 框架层兜底），所有错误路径保留完整日志。

**Architecture:** 在 `app/agent/executor/` 下新增 `errors.py`（错误构造/分类/失败记录）与 `replanner.py`（复用 `DAGGenerator` 的 LLM 解析 + `DAGValidator` 校验）。`DAGExecutionEngine.execute()` 的执行段拆成 `_execute_batch` + 有界 `while` 循环：批内出现终态失败且满足条件（`AGENT_REPLAN_ENABLED` 且存在 `session_id`）时，调用 `Replanner` 生成**仅 server 端**的修正步骤并执行，最多 `AGENT_REPLAN_MAX` 轮。

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, loguru, openai SDK, pytest + pytest-asyncio + pytest-mock。

**Spec:** `docs/design-docs/pi-agent-borrowable-ideas.md`（#1 错误即消息、#2 错误分层）

## Global Constraints

- 不改变 SSE 事件契约（`event:` 名称与 `data:` JSON 字段）——仅**新增** `replan_started` / `replan_generated` / `replan_failed` 三种事件。
- 所有错误路径必须打印日志：工具层用 `WARNING/ERROR`，框架层兜底未知异常必须 `logger.opt(exception=e).error(...)`（保留 traceback）。
- 保留旧结果字段：错误结果 dict 必须仍含 `error` 与 `result` 键（下游 `if "error" in result` 逻辑依赖）。
- 遵循现有代码风格（loguru、Pydantic、`async`）；不引入新依赖。
- re-plan 只允许 `ExecutionLocation.SERVER` 的步骤（避免 client 二次确认语义复杂化）。
- 默认配置 `AGENT_REPLAN_ENABLED=False`（避免既有单测触发网络调用）；生产通过 `.env` 开启。
- 测试命令：`cd packages/guineapig-aiagent && uv run pytest -q`（单测文件用 `uv run pytest test/<file>.py -q`）。

---

## File Structure

- **Create** `packages/guineapig-aiagent/app/agent/executor/errors.py` — `StepFailure`、`error_result()`、`exception_result()`、`classify_exception()`。
- **Create** `packages/guineapig-aiagent/app/agent/executor/replanner.py` — `Replanner.replan()`。
- **Modify** `packages/guineapig-aiagent/app/agent/executor/handlers.py` — 所有错误返回改用 `error_result()`，文案具体化。
- **Modify** `packages/guineapig-aiagent/app/agent/executor/engine.py` — 拆分 `_execute_batch`、新增 `_can_replan` / `_replan`、失败结构化、日志。
- **Modify** `packages/guineapig-aiagent/app/agent/models.py` — `StreamEventType` 新增 3 个成员。
- **Modify** `packages/guineapig-aiagent/app/agent/intent/prompts.py` — `REPLAN_SYSTEM` / `REPLAN_HUMAN_TEMPLATE`。
- **Modify** `packages/guineapig-aiagent/app/config.py` — `AGENT_REPLAN_ENABLED` / `AGENT_REPLAN_MAX`。
- **Modify** `packages/guineapig-aiagent/app/routers/agent.py` — `context` 注入 `capabilities_formatted` / `trace_id`。
- **Test** `packages/guineapig-aiagent/test/agent_error_message_test.py`
- **Test** `packages/guineapig-aiagent/test/agent_replan_test.py`

---

## Task 1: 错误构造与分类模块

**Files:**
- Create: `packages/guineapig-aiagent/app/agent/executor/errors.py`
- Test: `packages/guineapig-aiagent/test/agent_error_message_test.py`

**Interfaces:**
- Produces:
  - `StepFailure(step_id: str, capability: str, action: str, error: str, error_type: str = "unknown", suggestion: str = "", params: dict = {})` (dataclass)
  - `error_result(message: str, *, error_type="tool_error", suggestion="", capability="", level="WARNING") -> dict`
  - `exception_result(exc, *, capability="", context="") -> dict`
  - `classify_exception(exc) -> str`（返回 `timeout|connection|auth|bad_request|unknown`）

- [ ] **Step 1: 写失败测试**

Create `packages/guineapig-aiagent/test/agent_error_message_test.py`:

```python
"""错误即消息 / 错误分层 — errors.py 单元测试。"""

import asyncio

import pytest

from app.core.log import logger as app_logger
from app.agent.executor.errors import (
    StepFailure,
    classify_exception,
    error_result,
    exception_result,
)


@pytest.fixture
def captured_logs():
    records = []
    sink_id = app_logger.add(lambda m: records.append(m.record["message"]), level="DEBUG")
    try:
        yield records
    finally:
        app_logger.remove(sink_id)


def test_error_result_shape_and_log(captured_logs):
    r = error_result(
        "联网搜索失败：关键词为空",
        error_type="validation",
        suggestion="请在 params 中提供非空 query",
        capability="web_search",
    )
    assert r["error"] == "联网搜索失败：关键词为空"
    assert r["error_type"] == "validation"
    assert r["error_suggestion"] == "请在 params 中提供非空 query"
    assert r["result"] == ""
    assert any("联网搜索失败" in m for m in captured_logs)


def test_classify_exception_timeout():
    assert classify_exception(asyncio.TimeoutError()) == "timeout"


def test_classify_exception_connection():
    assert classify_exception(ConnectionError("x")) == "connection"


def test_classify_exception_unknown():
    assert classify_exception(ValueError("x")) == "unknown"


def test_exception_result_logs_traceback_and_shape(captured_logs):
    r = exception_result(ValueError("bad"), capability="rag", context="执行异常")
    assert r["error_type"] == "unknown"
    assert "bad" in r["error"]
    assert r["result"] == ""
    assert any("能力执行异常" in m for m in captured_logs)


def test_step_failure_defaults():
    f = StepFailure("s1", "web_search", "search", "超时")
    assert f.error_type == "unknown"
    assert f.suggestion == ""
    assert f.params == {}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/guineapig-aiagent && uv run pytest test/agent_error_message_test.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agent.executor.errors'`

- [ ] **Step 3: 实现 errors.py**

Create `packages/guineapig-aiagent/app/agent/executor/errors.py`:

```python
"""能力执行的错误构造与分类 — 错误即消息 / 错误分层。

分层原则：
- 工具层（handlers）：识别已知错误，包装成具体可读描述 + 修复建议；
- 框架层（engine）：兜底捕获未知异常，保留 traceback 并转成结构化错误结果。

所有错误结果都带 error_type / error / error_suggestion，供后续步骤引用、总结、re-plan 使用。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.core.log import logger


@dataclass
class StepFailure:
    """一次终态步骤失败的结构化记录（供 re-plan 使用）。"""

    step_id: str
    capability: str
    action: str
    error: str
    error_type: str = "unknown"
    suggestion: str = ""
    params: dict = field(default_factory=dict)


def error_result(
    message: str,
    *,
    error_type: str = "tool_error",
    suggestion: str = "",
    capability: str = "",
    level: str = "WARNING",
) -> dict:
    """构造统一的错误结果 dict，并按 level 打印日志。

    返回结构保留旧字段 error/result，新增 error_type/error_suggestion：
        {"error": message, "error_type": error_type,
         "error_suggestion": suggestion, "result": ""}
    """
    prefix = f"[Handler:{capability}] " if capability else "[Handler] "
    suffix = f" | 建议: {suggestion}" if suggestion else ""
    logger.log(level, f"{prefix}{message}{suffix}")
    return {
        "error": message,
        "error_type": error_type,
        "error_suggestion": suggestion,
        "result": "",
    }


def classify_exception(exc: BaseException) -> str:
    """把异常归类到 error_type，用于错误分层与 re-plan 决策。"""
    try:
        import httpx
        from openai import (
            APIConnectionError,
            APITimeoutError,
            AuthenticationError,
            BadRequestError,
        )
    except Exception:  # pragma: no cover - 依赖缺失时退化为 unknown
        httpx = None
        APITimeoutError = APIConnectionError = AuthenticationError = BadRequestError = ()

    if isinstance(exc, asyncio.TimeoutError):
        return "timeout"
    if httpx is not None and isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if APITimeoutError and isinstance(exc, APITimeoutError):
        return "timeout"
    if httpx is not None and isinstance(exc, httpx.ConnectError):
        return "connection"
    if APIConnectionError and isinstance(exc, APIConnectionError):
        return "connection"
    if isinstance(exc, ConnectionError):
        return "connection"
    if AuthenticationError and isinstance(exc, AuthenticationError):
        return "auth"
    if BadRequestError and isinstance(exc, BadRequestError):
        return "bad_request"
    return "unknown"


def exception_result(
    exc: BaseException, *, capability: str = "", context: str = ""
) -> dict:
    """框架层兜底：把未知异常转成结构化错误结果（完整打印 traceback）。"""
    error_type = classify_exception(exc)
    detail = f"{context}: {exc}" if context else str(exc)
    logger.opt(exception=exc).error(
        f"[Engine] 能力执行异常: capability={capability}, type={error_type}, detail={detail}"
    )
    suggestion = {
        "timeout": "可提高 timeout_seconds 或稍后重试",
        "connection": "检查目标服务可达性与网络",
        "auth": "检查 API Key / Token 配置",
        "bad_request": "检查步骤参数是否符合工具签名",
    }.get(error_type, "")
    return {
        "error": detail,
        "error_type": error_type,
        "error_suggestion": suggestion,
        "result": "",
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd packages/guineapig-aiagent && uv run pytest test/agent_error_message_test.py -q`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
git add packages/guineapig-aiagent/app/agent/executor/errors.py packages/guineapig-aiagent/test/agent_error_message_test.py
git commit -m "feat(aiagent): add structured error helpers (error-as-message layer)"
```

---

## Task 2: handlers 错误文案具体化（工具层错误）

**Files:**
- Modify: `packages/guineapig-aiagent/app/agent/executor/handlers.py`
- Test: `packages/guineapig-aiagent/test/agent_error_message_test.py`（追加）

**Interfaces:**
- Consumes: `error_result`（Task 1）
- Produces: 每个 handler 的失败返回形如 `error_result(...)`，含具体上下文与建议。

- [ ] **Step 1: 写失败测试**

在 `test/agent_error_message_test.py` 追加：

```python
import pytest

from app.agent.executor.handlers import CapabilityHandlers


@pytest.mark.asyncio
async def test_web_search_missing_query_specific_error():
    r = await CapabilityHandlers.handle_web_search({"query": ""})
    assert r["error_type"] == "validation"
    assert "关键词" in r["error"]
    assert r["error_suggestion"]


@pytest.mark.asyncio
async def test_rag_missing_names_specific_error():
    r = await CapabilityHandlers.handle_rag({"query": "x", "rag_names": []})
    assert r["error_type"] == "validation"
    assert "知识库" in r["error"]


@pytest.mark.asyncio
async def test_unknown_capability_specific_error():
    r = await CapabilityHandlers.execute("totally_unknown", {})
    assert r["error_type"] == "unknown_capability"
    assert "totally_unknown" in r["error"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/guineapig-aiagent && uv run pytest test/agent_error_message_test.py -q`
Expected: FAIL — `KeyError: 'error_type'`（旧返回只有 `error`/`result`）

- [ ] **Step 3: 改写 handlers.py 的错误返回**

在 `handlers.py` 顶部导入：

```python
from .errors import error_result, exception_result
```

将下列返回语句按表逐条替换（保留原有成功路径不变）：

| 位置 | 旧返回 | 新返回 |
|------|--------|--------|
| `handle_web_search` 无 query (L40) | `{"error": "搜索关键词为空", "result": ""}` | `error_result("联网搜索失败：搜索关键词为空", error_type="validation", suggestion="请在 params 中提供非空 query", capability="web_search")` |
| 未配置 SearXNG (L43) | `{"error": "SearXNG 未配置", "result": ""}` | `error_result("联网搜索失败：SearXNG 未配置", error_type="config", suggestion="设置环境变量 SEARXNG_URL", capability="web_search")` |
| 超时 (L75) | `{"error": "联网搜索超时", "result": ""}` | `error_result(f"联网搜索超时（15s）：query={query}", error_type="timeout", suggestion="缩小关键词范围或稍后重试", capability="web_search")` |
| 其它异常 (L78) | `{"error": f"联网搜索失败: {e}", "result": ""}` | `exception_result(e, capability="web_search", context="联网搜索失败")` |
| `handle_rag` 无 query (L89) | `{"error": "检索关键词为空", "result": ""}` | `error_result("知识库检索失败：检索关键词为空", error_type="validation", suggestion="请在 params 中提供非空 query", capability="rag")` |
| 无 rag_names (L92) | `{"error": "未指定知识库名称", "result": ""}` | `error_result("知识库检索失败：未指定知识库名称", error_type="validation", suggestion="请在 params.rag_names 中提供知识库名称", capability="rag")` |
| RAG 异常 (L116) | `{"error": f"知识库检索失败: {e}", "result": ""}` | `exception_result(e, capability="rag", context="知识库检索失败")` |
| `handle_llm_chat` 无 prompt (L127) | `{"error": "提示词为空", "result": ""}` | `error_result("LLM 对话失败：提示词为空", error_type="validation", suggestion="请在 params 中提供 prompt/text/query 之一", capability="llm_chat")` |
| LLM 异常 (L184) | `{"error": f"LLM 对话失败: {e}", "result": ""}` | `exception_result(e, capability="llm_chat", context="LLM 对话失败")` |
| `handle_memory_retrieve` 无 query (L195) | `{"error": "记忆检索关键词为空", "result": ""}` | `error_result("记忆检索失败：检索关键词为空", error_type="validation", suggestion="请在 params 中提供非空 query", capability="memory_retrieve")` |
| 未配置 backend (L198) | `{"error": "Backend URL 未配置", "result": ""}` | `error_result("记忆检索失败：Backend URL 未配置", error_type="config", suggestion="设置环境变量 BACKEND_BASE_URL", capability="memory_retrieve")` |
| 记忆检索超时 (L228) | `{"error": "记忆检索超时", "result": ""}` | `error_result("记忆检索超时（10s）", error_type="timeout", suggestion="稍后重试", capability="memory_retrieve")` |
| 记忆检索异常 (L233) | `{"error": f"记忆检索失败: {e}", "result": ""}` | `exception_result(e, capability="memory_retrieve", context="记忆检索失败")` |
| `handle_memory_summarize` 无 content (L244) | `{"error": "总结内容为空", "result": ""}` | `error_result("记忆总结失败：内容为空", error_type="validation", suggestion="请在 params 中提供非空 content", capability="memory_summarize")` |
| 未配置 backend (L247) | `{"error": "Backend URL 未配置", "result": ""}` | `error_result("记忆总结失败：Backend URL 未配置", error_type="config", suggestion="设置环境变量 BACKEND_BASE_URL", capability="memory_summarize")` |
| 记忆总结超时 (L269) | `{"error": "记忆总结超时", "result": ""}` | `error_result("记忆总结超时（30s）", error_type="timeout", suggestion="稍后重试", capability="memory_summarize")` |
| 记忆总结异常 (L272) | `{"error": f"记忆总结失败: {e}", "result": ""}` | `exception_result(e, capability="memory_summarize", context="记忆总结失败")` |
| MCP 无 tool_name (L294) | `{"error": "MCP 工具名称为空", "result": ""}` | `error_result("MCP 调用失败：工具名称为空", error_type="validation", suggestion="请在 params.tool 指定工具名", capability=server_name or "mcp")` |
| MCP 无 url (L297) | `{"error": "MCP server URL 未提供", "result": ""}` | `error_result("MCP 调用失败：server URL 未提供", error_type="config", suggestion="检查该 MCP server 的连接配置", capability=server_name or "mcp")` |
| MCP 异常 (L352) | `{"error": f"MCP 调用失败: {e}", "result": ""}` | `exception_result(e, capability=server_name or "mcp", context=f"MCP 调用失败 tool={tool_name}")` |
| `execute` 未知能力 (L399) | `{"error": f"未知能力: {capability}", "result": ""}` | `error_result(f"未知能力：{capability}", error_type="unknown_capability", suggestion="确认 capability 是否在当前能力清单中", capability=capability)` |

- [ ] **Step 4: 运行测试确认通过**

Run: `cd packages/guineapig-aiagent && uv run pytest test/agent_error_message_test.py -q`
Expected: PASS（9 passed）

- [ ] **Step 5: 提交**

```bash
git add packages/guineapig-aiagent/app/agent/executor/handlers.py packages/guineapig-aiagent/test/agent_error_message_test.py
git commit -m "feat(aiagent): specific layered error messages in capability handlers"
```

---

## Task 3: 引擎框架层兜底结构化 + 失败记录

**Files:**
- Modify: `packages/guineapig-aiagent/app/agent/executor/engine.py`（`_execute_step` 重试段 L443-539）
- Test: `packages/guineapig-aiagent/test/agent_error_message_test.py`（追加）

**Interfaces:**
- Consumes: `exception_result`、`StepFailure`
- Produces: 失败步骤写入 `self.step_results[step_id] = {"error","error_type","error_suggestion","result"}`；引擎新增实例属性 `self.failed_steps: list[StepFailure]`（初始为空）。

- [ ] **Step 1: 写失败测试**

追加：

```python
from app.agent.models import DAGDefinition, DAGStep
from app.agent.executor.engine import DAGExecutionEngine
from app.agent.executor import handlers as handlers_mod


@pytest.mark.asyncio
async def test_server_exception_becomes_structured_error(mocker, captured_logs):
    async def boom(capability, params):
        raise ValueError("kaboom")

    mocker.patch.object(handlers_mod.CapabilityHandlers, "execute", side_effect=boom)
    dag = DAGDefinition(
        steps=[DAGStep(step_id="s1", capability="web_search", action="x", max_retries=0)],
        original_intent="t",
    )
    engine = DAGExecutionEngine(dag, context={"session_id": ""})
    events = [e async for e in engine.execute()]

    assert any(e.event == "step_failed" for e in events)
    stored = engine.step_results["s1"]
    assert stored["error_type"] == "unknown"
    assert "kaboom" in stored["error"]
    assert any("能力执行异常" in m for m in captured_logs)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/guineapig-aiagent && uv run pytest test/agent_error_message_test.py::test_server_exception_becomes_structured_error -q`
Expected: FAIL — `KeyError: 's1'`（当前失败步骤不写入 `step_results`）

- [ ] **Step 3: 修改 engine.py**

顶部导入：

```python
from .errors import StepFailure, exception_result
```

`__init__` 增加：

```python
        self.failed_steps: list[StepFailure] = []
```

把 `_execute_step` 中 server 执行段（L443-539）的重试与失败处理改为：

```python
        # 执行（带重试）
        result = None
        last_error = ""
        last_error_type = "unknown"
        last_error_suggestion = ""
        for attempt in range(max(1, step.max_retries + 1)):
            if attempt > 0:
                logger.info(
                    f"[Engine] Retry step {step.step_id} "
                    f"(attempt {attempt + 1}/{step.max_retries + 1})"
                )
                yield self._event(
                    StreamEventType.LOG,
                    {
                        "step_id": step.step_id,
                        "level": "warning",
                        "message": f"重试第 {attempt + 1} 次",
                    },
                )
                entry.logs.append(
                    TimelineLog(
                        ts=datetime.now(timezone.utc).isoformat(),
                        level="warning",
                        msg=f"重试第 {attempt + 1} 次",
                    )
                )

            try:
                result = await asyncio.wait_for(
                    CapabilityHandlers.execute(step.capability, resolved_params),
                    timeout=step.timeout_seconds,
                )
                if "error" in result:
                    last_error = result["error"]
                    last_error_type = result.get("error_type", "tool_error")
                    last_error_suggestion = result.get("error_suggestion", "")
                    continue  # 重试
                last_error = ""
                break  # 成功
            except asyncio.TimeoutError:
                last_error = f"执行超时 ({step.timeout_seconds}s)"
                last_error_type = "timeout"
                last_error_suggestion = "可提高 timeout_seconds 或稍后重试"
                continue
            except Exception as e:
                err = exception_result(e, capability=step.capability, context="执行异常")
                last_error = err["error"]
                last_error_type = err["error_type"]
                last_error_suggestion = err["error_suggestion"]
                continue
```

失败分支（原 `else:` 段）末尾追加写入 `step_results`：

```python
            self.step_results[step.step_id] = {
                "error": last_error,
                "error_type": last_error_type,
                "error_suggestion": last_error_suggestion,
                "result": "",
            }
```

（插入位置：`self.timeline.append(entry)` 之后、`logger.error(...)` 之前。）

- [ ] **Step 4: 运行测试确认通过**

Run: `cd packages/guineapig-aiagent && uv run pytest test/agent_error_message_test.py test/executor_engine_test.py -q`
Expected: PASS（新增 1 条 + 既有引擎测试全绿；`test_step_with_unresolved_placeholder_fails` 仍通过）

- [ ] **Step 5: 提交**

```bash
git add packages/guineapig-aiagent/app/agent/executor/engine.py packages/guineapig-aiagent/test/agent_error_message_test.py
git commit -m "feat(aiagent): structured framework-level errors + failed step records"
```

---

## Task 4: re-plan 提示词与 Replanner

**Files:**
- Modify: `packages/guineapig-aiagent/app/agent/intent/prompts.py`
- Create: `packages/guineapig-aiagent/app/agent/executor/replanner.py`
- Test: `packages/guineapig-aiagent/test/agent_replan_test.py`

**Interfaces:**
- Consumes: `StepFailure`、`DAGGenerator._parse_steps`、`DAGGenerator._get_llm_client`、`DAGValidator.validate`
- Produces: `Replanner.replan(*, original_intent, capability_inventory, capabilities_formatted, step_results, failed, trace_id=None) -> list[DAGStep]`（仅返回 server 端、已通过校验的步骤，失败返回 `[]`）；`Replanner._call_llm(system, human, trace_id=None) -> str`（可被测试替换）

- [ ] **Step 1: 写失败测试**

Create `packages/guineapig-aiagent/test/agent_replan_test.py`:

```python
"""DAG 自纠错 re-plan 单元测试。"""

import json

import pytest

from app.agent.executor.errors import StepFailure
from app.agent.executor.replanner import Replanner
from app.agent.models import (
    CapabilityInfo,
    CapabilityInventory,
    CapabilityType,
    DAGStep,
    ExecutionLocation,
)


def _inventory():
    return CapabilityInventory(
        capabilities=[
            CapabilityInfo(
                type=CapabilityType.LLM_CHAT,
                name="llm_chat",
                description="LLM",
                execution_location=ExecutionLocation.SERVER,
            ),
        ]
    )


def test_replan_returns_validated_server_steps(mocker):
    raw = json.dumps(
        [
            {
                "step_id": "r1",
                "capability": "llm_chat",
                "action": "用已有信息直接回答",
                "params": {"prompt": "回答用户"},
                "execution_location": "server",
            }
        ]
    )
    mocker.patch.object(Replanner, "_call_llm", return_value=raw)
    steps = Replanner.replan(
        original_intent="查天气",
        capability_inventory=_inventory(),
        capabilities_formatted="`llm_chat`",
        step_results={"s1": {"error": "超时"}},
        failed=StepFailure("s1", "web_search", "search", "超时", "timeout", "重试"),
    )
    assert [s.step_id for s in steps] == ["r1"]


def test_replan_filters_client_steps(mocker):
    raw = json.dumps(
        [
            {"step_id": "c1", "capability": "cli", "action": "x", "execution_location": "client"},
            {"step_id": "r1", "capability": "llm_chat", "action": "y", "execution_location": "server", "params": {"prompt": "p"}},
        ]
    )
    mocker.patch.object(Replanner, "_call_llm", return_value=raw)
    steps = Replanner.replan(
        original_intent="t",
        capability_inventory=_inventory(),
        capabilities_formatted="",
        step_results={},
        failed=StepFailure("s1", "cli", "x", "err"),
    )
    assert [s.step_id for s in steps] == ["r1"]


def test_replan_returns_empty_on_llm_failure(mocker):
    mocker.patch.object(Replanner, "_call_llm", side_effect=RuntimeError("no llm"))
    steps = Replanner.replan(
        original_intent="t",
        capability_inventory=_inventory(),
        capabilities_formatted="",
        step_results={},
        failed=StepFailure("s1", "web_search", "x", "err"),
    )
    assert steps == []


def test_replan_returns_empty_on_invalid_plan(mocker):
    raw = json.dumps([{"step_id": "r1", "capability": "nope", "action": "x", "execution_location": "server"}])
    mocker.patch.object(Replanner, "_call_llm", return_value=raw)
    steps = Replanner.replan(
        original_intent="t",
        capability_inventory=_inventory(),
        capabilities_formatted="",
        step_results={},
        failed=StepFailure("s1", "web_search", "x", "err"),
    )
    assert steps == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/guineapig-aiagent && uv run pytest test/agent_replan_test.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agent.executor.replanner'`

- [ ] **Step 3: 追加提示词**

在 `packages/guineapig-aiagent/app/agent/intent/prompts.py` 末尾追加：

```python
# ═══════════════════════════════════════════════════
# 自纠错: Re-plan System Prompt
# ═══════════════════════════════════════════════════

REPLAN_SYSTEM = """你是一个 AI Agent 的自我纠错规划引擎。上一步执行失败，请根据失败信息提供一个修正后的执行计划（DAG 步骤数组）。

## 核心原则
1. 只生成尚未完成任务的**修正步骤**，不要重复已成功完成的步骤。
2. 分析失败原因并尽量规避同一错误（如更换检索词、补齐缺失参数、换用其它能力）。
3. **只能使用 server 端能力**（web_search / rag / llm_chat / memory / 远程 mcp），禁止 cli、文件系统等 client 端能力。
4. 参数引用规则与首次规划一致：`{{step_id.output_key}}` 或 `{{output_key}}`，且被引用步骤必须在 depends_on 中。
5. 如确实无法修正，返回空数组 []。

## 输出格式
JSON 数组，每项含 step_id/capability/action/params/output_key/depends_on/execution_location/max_retries/timeout_seconds。
"""

REPLAN_HUMAN_TEMPLATE = """## 可用能力
{capabilities}

## 原始任务
{original_intent}

## 已完成步骤的结果
{executed_summary}

## 失败步骤
step_id: {failed_step_id}
capability: {failed_capability}
action: {failed_action}
错误: {error}
建议: {suggestion}

## 任务
给出修正后的 server 端执行计划（JSON 数组）。如无法修正返回 []。"""
```

- [ ] **Step 4: 实现 replanner.py**

Create `packages/guineapig-aiagent/app/agent/executor/replanner.py`:

```python
"""DAG 自纠错 Replanner — 根据失败信息生成并校验修正步骤（仅 server 端）。"""

from __future__ import annotations

from app.core.log import logger
from app.core.llm_clients import call_with_retry
from app.agent.models import (
    CapabilityInventory,
    DAGDefinition,
    DAGStep,
    ExecutionLocation,
)

from .errors import StepFailure


class Replanner:
    """把一次终态失败回喂给 LLM，产出一份受约束的修正计划。"""

    @classmethod
    def _call_llm(cls, system: str, human: str, trace_id: str | None = None) -> str:
        from app.agent.dag.generator import DAGGenerator

        client, model_name = DAGGenerator._get_llm_client()
        completion = call_with_retry(
            client.chat.completions.create,
            model=model_name,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": human},
            ],
            temperature=0.1,
            max_tokens=2048,
            response_format={"type": "json_object"},
        )
        return completion.choices[0].message.content or ""

    @classmethod
    def replan(
        cls,
        *,
        original_intent: str,
        capability_inventory: CapabilityInventory | None,
        capabilities_formatted: str,
        step_results: dict,
        failed: StepFailure,
        trace_id: str | None = None,
    ) -> list[DAGStep]:
        from app.agent.dag.generator import DAGGenerator
        from app.agent.dag.validator import DAGValidator
        from app.agent.intent.prompts import REPLAN_SYSTEM, REPLAN_HUMAN_TEMPLATE

        executed_summary = (
            "\n".join(f"- {sid}: {str(res)[:300]}" for sid, res in step_results.items())
            or "(无)"
        )
        human = REPLAN_HUMAN_TEMPLATE.format(
            capabilities=capabilities_formatted or "(无)",
            original_intent=original_intent or "",
            executed_summary=executed_summary,
            failed_step_id=failed.step_id,
            failed_capability=failed.capability,
            failed_action=failed.action,
            error=failed.error,
            suggestion=failed.suggestion or "(无)",
        )

        logger.warning(
            f"[Replanner] 触发自纠错: failed={failed.step_id}/{failed.capability}, "
            f"error={failed.error[:120]}"
        )
        try:
            raw = cls._call_llm(REPLAN_SYSTEM, human, trace_id=trace_id)
        except Exception as e:
            logger.opt(exception=e).error(f"[Replanner] re-plan LLM 调用失败，放弃自纠错: {e}")
            return []

        steps = DAGGenerator._parse_steps(raw)
        server_steps = [
            s for s in steps if s.execution_location == ExecutionLocation.SERVER
        ]
        if len(server_steps) != len(steps):
            logger.warning(
                f"[Replanner] 过滤 {len(steps) - len(server_steps)} 个 client 端修正步骤"
            )
        if not server_steps:
            logger.warning("[Replanner] 修正计划为空，放弃自纠错")
            return []

        dag = DAGDefinition(
            steps=server_steps,
            original_intent=original_intent,
            estimated_total_steps=len(server_steps),
        )
        valid, errors = DAGValidator.validate(dag, capability_inventory)
        if not valid:
            logger.warning(f"[Replanner] 修正计划验证失败: {errors}")
            return []

        logger.info(
            f"[Replanner] 修正计划通过: {len(server_steps)} 步: "
            f"{[f'{s.step_id}:{s.capability}' for s in server_steps]}"
        )
        return server_steps
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd packages/guineapig-aiagent && uv run pytest test/agent_replan_test.py -q`
Expected: PASS（4 passed）

- [ ] **Step 6: 提交**

```bash
git add packages/guineapig-aiagent/app/agent/intent/prompts.py packages/guineapig-aiagent/app/agent/executor/replanner.py packages/guineapig-aiagent/test/agent_replan_test.py
git commit -m "feat(aiagent): add DAG replanner with validated server-only corrective plans"
```

---

## Task 5: 新增 re-plan 事件类型与配置

**Files:**
- Modify: `packages/guineapig-aiagent/app/agent/models.py`（`StreamEventType` L204-215）
- Modify: `packages/guineapig-aiagent/app/config.py`（LLM 配置段之后）
- Test: `packages/guineapig-aiagent/test/agent_replan_test.py`（追加）

**Interfaces:**
- Produces: `StreamEventType.REPLAN_STARTED/REPLAN_GENERATED/REPLAN_FAILED`；`settings.AGENT_REPLAN_ENABLED: bool`、`settings.AGENT_REPLAN_MAX: int`

- [ ] **Step 1: 写失败测试**

追加：

```python
def test_replan_event_types_exist():
    from app.agent.models import StreamEventType

    assert StreamEventType.REPLAN_STARTED.value == "replan_started"
    assert StreamEventType.REPLAN_GENERATED.value == "replan_generated"
    assert StreamEventType.REPLAN_FAILED.value == "replan_failed"


def test_replan_settings_defaults():
    from app.config import settings

    assert settings.AGENT_REPLAN_ENABLED is False
    assert settings.AGENT_REPLAN_MAX == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/guineapig-aiagent && uv run pytest test/agent_replan_test.py -q`
Expected: FAIL — `AttributeError: REPLAN_STARTED`

- [ ] **Step 3: 修改 models.py 与 config.py**

在 `models.py` 的 `StreamEventType` 中，`LOG = "log"` 之后追加：

```python
    REPLAN_STARTED = "replan_started"  # 步骤失败，触发自纠错
    REPLAN_GENERATED = "replan_generated"  # 已生成修正计划
    REPLAN_FAILED = "replan_failed"  # 自纠错未能产出修正计划
```

在 `config.py` 的 LLM 配置段（`LLM_RETRY_BACKOFF` 之后）追加：

```python
    # DAG 自纠错：步骤终态失败后，回喂错误给 re-planner 生成修正步骤（仅 server 端）
    AGENT_REPLAN_ENABLED: bool = False
    AGENT_REPLAN_MAX: int = 1
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd packages/guineapig-aiagent && uv run pytest test/agent_replan_test.py -q`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
git add packages/guineapig-aiagent/app/agent/models.py packages/guineapig-aiagent/app/config.py packages/guineapig-aiagent/test/agent_replan_test.py
git commit -m "feat(aiagent): add replan stream events and config toggles"
```

---

## Task 6: 引擎接入有界自纠错

**Files:**
- Modify: `packages/guineapig-aiagent/app/agent/executor/engine.py`（`execute()` 执行段 L157-213）
- Modify: `packages/guineapig-aiagent/app/routers/agent.py`（`context` 构造 L868-878）
- Test: `packages/guineapig-aiagent/test/agent_replan_test.py`（追加）

**Interfaces:**
- Consumes: `Replanner`、`StreamEventType.REPLAN_*`、`settings.AGENT_REPLAN_*`、`self.failed_steps`
- Produces: `engine.execute()` 在失败且满足条件时执行修正步骤，`execution_complete.data` 新增 `replanned: bool`；`engine.context` 支持 `capabilities_formatted` 与 `trace_id`。

- [ ] **Step 1: 写失败测试**

追加：

```python
from app.agent.executor.engine import DAGExecutionEngine
from app.agent.executor import handlers as handlers_mod
from app.agent.executor.replanner import Replanner
from app.agent.executor import engine as engine_mod
from app.agent.models import DAGDefinition, DAGStep, StreamEventType
from app.config import settings


@pytest.mark.asyncio
async def test_engine_replans_after_failure(mocker):
    async def fake_execute(capability, params):
        if capability == "web_search":
            return {"error": "超时", "error_type": "timeout", "error_suggestion": "重试", "result": ""}
        return {"result": "修正后的答案", "char_count": 6}

    mocker.patch.object(handlers_mod.CapabilityHandlers, "execute", side_effect=fake_execute)
    mocker.patch.object(
        engine_mod.Replanner,
        "replan",
        return_value=[DAGStep(step_id="r1", capability="llm_chat", action="answer", params={"prompt": "p"})],
    )
    mocker.patch.object(settings, "AGENT_REPLAN_ENABLED", True)
    mocker.patch.object(settings, "AGENT_REPLAN_MAX", 1)

    dag = DAGDefinition(
        steps=[DAGStep(step_id="s1", capability="web_search", action="search", max_retries=0)],
        original_intent="查一下",
    )
    engine = DAGExecutionEngine(dag, context={"session_id": "conv_1", "capabilities_formatted": "`llm_chat`"})
    events = [e async for e in engine.execute(session_id="conv_1")]
    types = [e.event for e in events]

    assert StreamEventType.REPLAN_STARTED.value in types
    assert StreamEventType.REPLAN_GENERATED.value in types
    assert StreamEventType.STEP_COMPLETED.value in types
    complete = [e for e in events if e.event == StreamEventType.EXECUTION_COMPLETE.value][-1]
    assert complete.data["status"] == "completed"
    assert complete.data["replanned"] is True
    assert "r1" in engine.step_results


@pytest.mark.asyncio
async def test_engine_no_replan_without_session(mocker):
    async def fake_execute(capability, params):
        return {"error": "超时", "error_type": "timeout", "result": ""}

    mocker.patch.object(handlers_mod.CapabilityHandlers, "execute", side_effect=fake_execute)
    replan = mocker.patch.object(engine_mod.Replanner, "replan")
    mocker.patch.object(settings, "AGENT_REPLAN_ENABLED", True)

    dag = DAGDefinition(
        steps=[DAGStep(step_id="s1", capability="web_search", action="x", max_retries=0)],
        original_intent="t",
    )
    engine = DAGExecutionEngine(dag)
    _ = [e async for e in engine.execute()]
    replan.assert_not_called()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/guineapig-aiagent && uv run pytest test/agent_replan_test.py::test_engine_replans_after_failure -q`
Expected: FAIL — 事件中无 `replan_started`

- [ ] **Step 3: 修改 engine.py**

顶部导入（在 `.errors` 导入旁）：

```python
from .replanner import Replanner
```

将 `execute()` 中「4. 按拓扑顺序逐个执行」到「5. 执行完成」前的执行循环（L157-196）替换为：

```python
        # 4. 执行（支持有界自纠错 re-plan）
        pending = list(sorted_steps)
        replan_round = 0
        completed = 0

        while pending:
            self.failed_steps = []
            async for event in self._execute_batch(pending, inventory):
                yield event
            completed += sum(
                1
                for s in pending
                if "error" not in (self.step_results.get(s.step_id) or {})
            )

            if not self.failed_steps:
                break
            if not self._can_replan(session_id, replan_round):
                break

            replan_round += 1
            failed = self.failed_steps[0]
            logger.warning(
                f"[Engine] 步骤失败，进入自纠错: "
                f"{failed.step_id}/{failed.capability}: {failed.error[:120]}"
            )
            yield self._event(
                StreamEventType.REPLAN_STARTED,
                {
                    "round": replan_round,
                    "failed_step": failed.step_id,
                    "error": failed.error[:200],
                },
            )
            corrective = await asyncio.to_thread(
                Replanner.replan,
                original_intent=self.dag.original_intent,
                capability_inventory=inventory,
                capabilities_formatted=self.context.get("capabilities_formatted", ""),
                step_results=self.step_results,
                failed=failed,
                trace_id=self.context.get("trace_id"),
            )
            if not corrective:
                yield self._event(
                    StreamEventType.REPLAN_FAILED, {"round": replan_round}
                )
                break

            yield self._event(
                StreamEventType.REPLAN_GENERATED,
                {
                    "round": replan_round,
                    "steps": [self._step_summary(s) for s in corrective],
                },
            )
            pending = corrective

        failed = bool(self.failed_steps)
```

在 `EXECUTION_COMPLETE` 的 data 中，`"summary"` 之前追加：

```python
                "replanned": replan_round > 0,
```

在 `_execute_step` 之后新增两个方法：

```python
    async def _execute_batch(
        self,
        steps: list[DAGStep],
        inventory: CapabilityInventory | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """执行一批步骤，记录终态失败（供 re-plan 决策）。"""
        for step in steps:
            if not self._dependencies_resolved(step):
                yield self._event(
                    StreamEventType.STEP_FAILED,
                    {
                        "step_id": step.step_id,
                        "error": "前置步骤未完成或已失败",
                        "step": self._step_summary(step),
                    },
                )
                self.failed_steps.append(
                    StepFailure(
                        step.step_id,
                        step.capability,
                        step.action,
                        "前置步骤未完成或已失败",
                        "dependency",
                    )
                )
                break

            step_failed_error = None
            async for event in self._execute_step(step, inventory):
                if event.event == StreamEventType.STEP_FAILED.value:
                    step_failed_error = event.data.get("error", "")
                yield event
                if (
                    event.event == StreamEventType.STEP_FAILED.value
                    and step.fallback_action
                ):
                    async for fallback_event in self._execute_fallback(
                        step, step.fallback_action
                    ):
                        yield fallback_event

            final_res = self.step_results.get(step.step_id)
            if step_failed_error is not None and (
                final_res is None or "error" in final_res
            ):
                self.failed_steps.append(
                    StepFailure(
                        step.step_id,
                        step.capability,
                        step.action,
                        step_failed_error,
                        (final_res or {}).get("error_type", "unknown"),
                        (final_res or {}).get("error_suggestion", ""),
                        dict(step.params),
                    )
                )

    def _can_replan(self, session_id: str, round_index: int) -> bool:
        """判断是否允许再发起一轮自纠错。"""
        if not settings.AGENT_REPLAN_ENABLED:
            return False
        if not session_id:
            return False
        return round_index < max(0, settings.AGENT_REPLAN_MAX)
```

（顶部导入需补 `from app.config import settings`；当前 `engine.py` 未导入 settings。同时保留 `StreamEventType`、`AsyncGenerator` 已有导入。）

- [ ] **Step 4: 修改 agent.py 注入 context**

在 `agent.py` 构造 `context` 的 dict（L868-878）中，`"mcp_servers"` 之后追加：

```python
                    "capabilities_formatted": pipeline_result.get(
                        "capabilities_formatted", ""
                    ),
                    "trace_id": trace_id,
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd packages/guineapig-aiagent && uv run pytest test/agent_replan_test.py test/executor_engine_test.py -q`
Expected: PASS（两个自纠错引擎测试 + 全部既有引擎测试）

- [ ] **Step 6: 运行整个 aiagent 测试套件**

Run: `cd packages/guineapig-aiagent && uv run pytest -q --ignore=test/routers_agent_test.py`
Expected: PASS（无回归）

- [ ] **Step 7: 提交**

```bash
git add packages/guineapig-aiagent/app/agent/executor/engine.py packages/guineapig-aiagent/app/routers/agent.py packages/guineapig-aiagent/test/agent_replan_test.py
git commit -m "feat(aiagent): bounded DAG self-correction via error-as-message replan"
```

---

## Self-Review

- **Spec coverage:** #1 错误即消息 → Task 3（失败写入 step_results，供总结/re-plan）+ Task 6（re-plan 回喂）；#2 错误分层 → Task 1（分层工具）+ Task 2（工具层具体化）+ Task 3（框架层兜底 traceback）；日志要求 → Task 1/3 的 `logger.log`/`logger.opt(exception=...)` 与测试断言。
- **Placeholder scan:** 无 TODO/"类似 Task" 占位；handlers 全部错误返回以表格给出确切替换文本。
- **Type consistency:** `error_result`/`exception_result` 返回键 `error/error_type/error_suggestion/result` 在 Task 2/3/6 一致；`StepFailure` 字段顺序在 `errors.py`、`engine.py` 构造处一致。
- **行为兼容:** 默认 `AGENT_REPLAN_ENABLED=False` + `_can_replan` 要求 `session_id`，既有单测（无 session）不受影响；`execution_complete` 仅新增字段。

## Open Questions

- [ ] re-plan 修正步骤是否需要再次用户确认？（当前设计：不做二次确认，因已授权整体任务；对 client 端步骤直接过滤）
- [ ] re-plan 的 token 成本是否纳入 `otel_service` 指标上报？（当前未纳入，可后续补）
