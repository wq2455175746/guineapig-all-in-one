"""
可观察指标服务 — 将 Agent 对话指标写入 Redis Hash。

使用同步 Redis 客户端在线程中执行，socket·connect·timeout 在 C 层生效，
确保 TCP 建连超时正常工作。避免 asyncio + redis-py 下 wait_for 无法取消
TCP 建连协程的问题（Python 3.13+ asyncio 改动）。

数据流:
  Agent 执行完成后 → 收集指标 → HINCRBY 累加到 Redis Hash
  → Backend 定时读取 Hash → 写入 MySQL chat_otel 表

Redis Key:
  Hash: otel:metrics:{YYYYMMDD}:{user_id}  — 指标累计值
  Set:  otel:metrics:{YYYYMMDD}:{user_id}:conversations — conversation IDs (SADD)
"""

import asyncio
import traceback
from datetime import datetime

import redis as sync_redis

from app.config import settings
from app.core.log import logger

# Redis 操作超时（秒）— 同步客户端 socket.timeout 与 asyncio.wait_for 双重保护
_REDIS_TIMEOUT = 5.0


def _execute_pipeline(
    host: str,
    port: int,
    db: int,
    password: str | None,
    user_id: int,
    conversation_id: int,
    input_token: int,
    output_token: int,
    request_count: int,
    agent_mode_count: int,
    web_search_count: int,
    rag_count: int,
) -> None:
    """在线程中执行的同步 Redis pipeline 写操作。

    使用同步 redis.Redis 客户端，socket·connect·timeout 在 POSIX 层生效，
    TCP 建连超时会可靠地抛出 TimeoutError。
    """
    today = datetime.now().strftime("%Y%m%d")
    key = f"otel:metrics:{today}:{user_id}"
    conv_set_key = f"{key}:conversations"

    r = sync_redis.Redis(
        host=host,
        port=port,
        db=db,
        password=password or None,
        decode_responses=True,
        socket_connect_timeout=_REDIS_TIMEOUT,
        socket_timeout=_REDIS_TIMEOUT,
    )

    try:
        pipe = r.pipeline()
        if input_token > 0:
            pipe.hincrby(key, "input_token", input_token)
        if output_token > 0:
            pipe.hincrby(key, "output_token", output_token)
        if request_count > 0:
            pipe.hincrby(key, "request_count", request_count)
        if agent_mode_count > 0:
            pipe.hincrby(key, "agent_mode_count", agent_mode_count)
        if web_search_count > 0:
            pipe.hincrby(key, "web_search_count", web_search_count)
        if rag_count > 0:
            pipe.hincrby(key, "rag_count", rag_count)

        # conversation IDs 使用 Set，天然去重，无需先读后写
        pipe.sadd(conv_set_key, str(conversation_id))
        pipe.expire(conv_set_key, 172800)
        pipe.expire(key, 172800)

        pipe.execute()
    finally:
        r.close()


class OtelService:
    """可观察指标服务 — 在线程中执行同步 Redis 写入"""

    async def report_metrics(
        self,
        user_id: int,
        conversation_id: int,
        *,
        input_token: int = 0,
        output_token: int = 0,
        request_count: int = 1,
        agent_mode_count: int = 0,
        web_search_count: int = 0,
        rag_count: int = 0,
        name: str = "",  # 保留参数保持兼容
    ) -> None:
        """报告一次对话的指标数据。

        在默认线程池 (ThreadPoolExecutor) 中执行同步 Redis pipeline，
        双重超时保护:
          1. 同步客户端 socket·connect·timeout（C 层，可靠）
          2. asyncio.wait_for 包装 run_in_executor（Python 层兜底）
        """
        if user_id <= 0:
            logger.warning("[OtelService] user_id 无效，跳过指标上报")
            return

        host = settings.REDIS_HOST
        port = settings.REDIS_PORT
        db = settings.REDIS_DB
        password = settings.REDIS_PASSWORD

        try:
            logger.info(
                f"[OtelService] 准备写入指标: "
                f"user_id={user_id}, conv_id={conversation_id}, "
                f"input_token={input_token}, output_token={output_token}, "
                f"Redis={host}:{port}"
            )

            loop = asyncio.get_running_loop()

            # 在线程中执行同步 Redis 操作
            await asyncio.wait_for(
                loop.run_in_executor(
                    None,  # 默认 ThreadPoolExecutor
                    _execute_pipeline,
                    host,
                    port,
                    db,
                    password,
                    user_id,
                    conversation_id,
                    input_token,
                    output_token,
                    request_count,
                    agent_mode_count,
                    web_search_count,
                    rag_count,
                ),
                timeout=_REDIS_TIMEOUT,
            )

            logger.info(
                f"[OtelService] 指标上报完成: "
                f"user_id={user_id}, conv_id={conversation_id}, "
                f"input_token={input_token}, output_token={output_token}"
            )

        except asyncio.TimeoutError:
            logger.error(
                f"[OtelService] 指标上报超时({_REDIS_TIMEOUT}s, run_in_executor): "
                f"host={host}:{port}, user_id={user_id}"
            )
        except Exception as e:
            logger.error(
                f"[OtelService] 指标上报失败: user_id={user_id}, err={e}\n"
                f"traceback:\n{''.join(traceback.format_exc())}"
            )

    async def close(self) -> None:
        """（兼容接口）线程池由事件循环管理，无需手动关闭"""
        pass


# 全局单例
otel_service = OtelService()
