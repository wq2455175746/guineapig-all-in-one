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
