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
from app.agent.executor.handlers import CapabilityHandlers


@pytest.fixture
def captured_logs():
    records = []
    sink_id = app_logger.add(lambda m: records.append(m.record["message"]), level="DEBUG")
    try:
        yield records
    finally:
        app_logger.remove(sink_id)


@pytest.fixture
def captured_records():
    records = []
    sink_id = app_logger.add(lambda m: records.append(m.record), level="DEBUG")
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


def test_exception_result_logs_traceback_and_shape(captured_records):
    r = exception_result(ValueError("bad"), capability="rag", context="执行异常")
    assert r["error_type"] == "unknown"
    assert "bad" in r["error"]
    assert r["result"] == ""
    assert any("能力执行异常" in rec["message"] for rec in captured_records)
    assert any(
        rec["exception"] is not None and rec["exception"].type is ValueError
        for rec in captured_records
    )


def test_step_failure_defaults():
    f = StepFailure("s1", "web_search", "search", "超时")
    assert f.error_type == "unknown"
    assert f.suggestion == ""
    assert f.params == {}


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
