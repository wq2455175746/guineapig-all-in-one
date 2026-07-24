"""
Agent 异步事件管理器 — 管理 SSE 执行引擎的确认/取消/委托执行信号。

工作方式：
- 每个 session 在 executor 启动时注册到 EventManager
- executor 在需要等待用户输入的地方 await 对应事件
- 控制端点 (agent_control.py) 收到 HTTP 请求后设置事件解除阻塞
- session 完成后自动清理

架构：
  Backend WS → Backend Go HTTP → AiAgent HTTP → AgentEventManager → Executor asyncio
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from app.core.log import logger


class AgentEventManager:
    """
    异步事件管理器 — 管理每个 session 的确认/取消/委托执行信号。

    线程安全：所有操作使用 asyncio.Event，可在协程间安全共享。
    session 在 executor 完成后通过 cleanup() 清理。

    Session 数据结构:
    {
        "confirm_event": asyncio.Event(),        # 用户确认事件
        "cancel_event": asyncio.Event(),          # 用户取消事件
        "cancelled": False,                       # 是否已取消
        "pending_delegates": {                     # 待处理的 delegate 事件
            "step_id": asyncio.Event()
        },
        "delegate_results": {                      # delegate 执行结果
            "step_id": {"result": {...}, "error": ""}
        },
        "created_at": "ISO timestamp",
    }
    """

    _sessions: dict[str, dict] = {}
    _lock = asyncio.Lock()

    # ── Session 生命周期 ──

    @classmethod
    async def register_session(cls, session_id: str) -> None:
        """注册一个新 session，创建必要的同步原语"""
        async with cls._lock:
            if session_id not in cls._sessions:
                cls._sessions[session_id] = {
                    "confirm_event": asyncio.Event(),
                    "cancel_event": asyncio.Event(),
                    "cancelled": False,
                    "pending_delegates": {},
                    "delegate_results": {},
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                logger.info(f"[EventManager] 注册 session: {session_id}")

    @classmethod
    async def cleanup(cls, session_id: str) -> None:
        """清理 session 数据"""
        async with cls._lock:
            if session_id in cls._sessions:
                del cls._sessions[session_id]
                logger.info(f"[EventManager] 清理 session: {session_id}")

    @classmethod
    async def is_cancelled(cls, session_id: str) -> bool:
        """检查 session 是否已被取消"""
        async with cls._lock:
            session = cls._sessions.get(session_id)
            return session is not None and session.get("cancelled", False)

    # ── 确认/取消事件 ──

    @classmethod
    async def wait_for_confirmation(
        cls, session_id: str, timeout: int = 300
    ) -> bool:
        """
        等待用户确认执行。

        Args:
            session_id: 会话 ID
            timeout: 超时秒数 (默认 300s = 5min)

        Returns:
            True = 用户确认, False = 用户取消/超时
        """
        session = cls._sessions.get(session_id)
        if not session:
            logger.warning(f"[EventManager] session 不存在: {session_id}")
            return False

        confirm_event: asyncio.Event = session["confirm_event"]
        cancel_event: asyncio.Event = session["cancel_event"]

        try:
            # 等待确认或取消事件，任一触发即返回
            confirm_task = asyncio.ensure_future(confirm_event.wait())
            cancel_task = asyncio.ensure_future(cancel_event.wait())
            done, pending = await asyncio.wait(
                [confirm_task, cancel_task],
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )

            # 取消未完成的任务
            for task in pending:
                task.cancel()

            if cancel_event.is_set():
                async with cls._lock:
                    session["cancelled"] = True
                logger.info(f"[EventManager] session {session_id} 取消执行")
                return False

            if confirm_event.is_set():
                logger.info(f"[EventManager] session {session_id} 确认执行")
                return True

            # 超时
            logger.warning(f"[EventManager] session {session_id} 等待确认超时")
            return False

        except asyncio.CancelledError:
            logger.info(f"[EventManager] session {session_id} 确认等待被取消")
            return False

    @classmethod
    async def confirm(cls, session_id: str) -> None:
        """用户确认执行 — 设置 confirm_event 解除阻塞"""
        async with cls._lock:
            session = cls._sessions.get(session_id)
            if session and not session["confirm_event"].is_set():
                session["confirm_event"].set()
                logger.info(f"[EventManager] confirm: {session_id}")

    @classmethod
    async def cancel(cls, session_id: str) -> None:
        """用户取消执行 — 设置 cancel_event 解除阻塞"""
        async with cls._lock:
            session = cls._sessions.get(session_id)
            if session:
                session["cancelled"] = True
                session["cancel_event"].set()
                logger.info(f"[EventManager] cancel: {session_id}")

    # ── Delegate 事件 ──

    @classmethod
    async def wait_for_delegate(
        cls, session_id: str, step_id: str, timeout: int = 600
    ) -> Optional[dict]:
        """
        等待客户端的 delegate 执行结果。

        Args:
            session_id: 会话 ID
            step_id: 步骤 ID
            timeout: 超时秒数 (默认 600s = 10min)

        Returns:
            dict 包含 result 和 error 字段, 或 None (超时/取消)
        """
        session = cls._sessions.get(session_id)
        if not session:
            logger.warning(f"[EventManager] delegate: session 不存在 {session_id}")
            return None

        # 创建该 step 的 delegate event
        delegate_event = asyncio.Event()
        async with cls._lock:
            session["pending_delegates"][step_id] = delegate_event

        try:
            # 等待 delegate 结果或取消
            delegate_task = asyncio.ensure_future(delegate_event.wait())
            cancel_task = asyncio.ensure_future(session["cancel_event"].wait())
            done, pending = await asyncio.wait(
                [delegate_task, cancel_task],
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()

            if session["cancel_event"].is_set():
                logger.info(
                    f"[EventManager] session {session_id} delegate {step_id} 被取消"
                )
                return None

            # 获取结果
            async with cls._lock:
                result = session["delegate_results"].get(step_id)

            if result is not None:
                logger.info(
                    f"[EventManager] session {session_id} delegate {step_id} 收到结果"
                )
                return result

            # 超时
            logger.warning(
                f"[EventManager] session {session_id} delegate {step_id} 超时"
            )
            return None

        except asyncio.CancelledError:
            logger.info(
                f"[EventManager] session {session_id} delegate {step_id} 等待被取消"
            )
            return None
        finally:
            # 清理该 step 的 delegate 数据
            async with cls._lock:
                session["pending_delegates"].pop(step_id, None)
                session["delegate_results"].pop(step_id, None)

    @classmethod
    async def deliver_delegate(
        cls, session_id: str, step_id: str, result: dict
    ) -> bool:
        """
        投递 delegate 执行结果，解除等待。

        Args:
            session_id: 会话 ID
            step_id: 步骤 ID
            result: 执行结果（包含 result 和 error 字段）

        Returns:
            bool 是否成功投递（session/step 是否存在）
        """
        async with cls._lock:
            session = cls._sessions.get(session_id)
            if not session:
                return False

            # 存储结果
            session["delegate_results"][step_id] = result

            # 设置事件
            delegate_event = session["pending_delegates"].get(step_id)
            if delegate_event:
                delegate_event.set()
                logger.info(
                    f"[EventManager] deliver delegate: "
                    f"session={session_id}, step={step_id}"
                )
                return True

            logger.warning(
                f"[EventManager] deliver delegate: "
                f"session={session_id}, step={step_id} 无等待中的 delegate"
            )
            return False
