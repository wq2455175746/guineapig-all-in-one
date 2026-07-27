"""
Langfuse 可观测性集成 — LLM Trace/Span 追踪。

提供 Langfuse 客户端的初始化和生命周期管理。
手动 generation span 使用 `langfuse.start_observation(as_type="generation")` API。

用法:
    from app.services.langfuse_client import init_langfuse, flush_langfuse, close_langfuse, get_langfuse

    # 在应用启动时
    init_langfuse()

    # 在需要手动创建 generation span 时
    langfuse = get_langfuse()
    if langfuse:
        gen = langfuse.start_observation(name="llm-call", as_type="generation", ...)
        # ... call LLM ...
        gen.update(output=response_text, usage_details={"input": 10, "output": 20})
        gen.end()
"""

from contextlib import contextmanager
from typing import Any

from app.config import settings
from app.core.log import logger

_langfuse_instance = None


def init_langfuse():
    """初始化 Langfuse 客户端（从 settings 读取配置）"""
    global _langfuse_instance

    if not settings.LANGFUSE_ENABLE:
        logger.info("[Langfuse] 已禁用 (LANGFUSE_ENABLE=false)")
        return

    if not settings.LANGFUSE_SECRET_KEY or not settings.LANGFUSE_PUBLIC_KEY:
        logger.warning(
            "[Langfuse] LANGFUSE_SECRET_KEY 或 LANGFUSE_PUBLIC_KEY 未配置，跳过初始化"
        )
        return

    try:
        from langfuse import Langfuse

        _langfuse_instance = Langfuse(
            secret_key=settings.LANGFUSE_SECRET_KEY,
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            host=settings.LANGFUSE_BASE_URL,
        )
        logger.info(
            f"[Langfuse] 客户端初始化成功: base_url={settings.LANGFUSE_BASE_URL}"
        )
    except ImportError:
        logger.warning("[Langfuse] langfuse 包未安装，跳过初始化")
    except Exception as e:
        logger.warning(f"[Langfuse] 初始化失败: {e}")


def flush_langfuse():
    """Flush 所有未发送的 Langfuse 事件"""
    global _langfuse_instance
    if _langfuse_instance:
        try:
            _langfuse_instance.flush()
            logger.debug("[Langfuse] flush 完成")
        except Exception as e:
            logger.warning(f"[Langfuse] flush 失败: {e}")


def close_langfuse():
    """关闭 Langfuse 客户端（flush + 清理）"""
    global _langfuse_instance
    flush_langfuse()
    _langfuse_instance = None
    logger.info("[Langfuse] 客户端已关闭")


def get_langfuse():
    """获取 Langfuse 客户端实例"""
    return _langfuse_instance


def is_langfuse_enabled() -> bool:
    """Langfuse 是否已启用"""
    return _langfuse_instance is not None


@contextmanager
def langfuse_generation(name: str, model: str, input: Any = None, **kwargs):
    """
    创建 LLM generation span 的上下文管理器（Langfuse SDK v4 API）。

    用法:
        with langfuse_generation("llm-call", "deepseek-chat", input=messages) as gen:
            response = client.chat.completions.create(...)
            if gen:
                gen.update(output=response)
    """
    langfuse = get_langfuse()
    if not langfuse:
        yield None
        return

    generation = langfuse.start_observation(
        name=name,
        as_type="generation",
        model=model,
        input=input,
        **kwargs,
    )
    try:
        yield generation
    except Exception as e:
        try:
            generation.update(level="ERROR", status_message=str(e), metadata={"error": str(e)})
        except Exception:
            pass
        raise
    finally:
        try:
            generation.end()
        except Exception:
            pass
