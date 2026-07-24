"""
LLM 原子能力 — 将文本发送到 DeepSeek 大模型获取回复
"""

from typing import AsyncGenerator

from openai import AsyncOpenAI, OpenAI

from app.config import settings
from app.core.log import logger

_llm_client = None
_model_name = None


def _ensure_llm_client():
    """确保 LLM 客户端已初始化（惰性加载）"""
    global _llm_client, _model_name

    if _llm_client is not None:
        return _llm_client, _model_name

    if not settings.LLM_API_KEY:
        raise ValueError("LLM_API_KEY not set in .env")

    _llm_client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)
    _model_name = settings.LLM_MODEL_NAME
    logger.info(f"[LLM] 客户端就绪: model={_model_name}")
    return _llm_client, _model_name


def get_llm_response(text: str) -> str:
    """
    将文本发送到 DeepSeek LLM，返回回复内容。

    Args:
        text: 用户输入的文本（ASR 识别结果）

    Returns:
        LLM 回复文本
    """
    client, model_name = _ensure_llm_client()

    messages = [
        {"role": "system", "content": "你是一个有用的语音助手。"},
        {
            "role": "user",
            "content": (
                "你的回复将会用 TTS 模型转为中文语音，请把回答控制在 100 字以内。"
                "标点符号仅包含逗号和句号，将数字转为文字回答。"
                "请用自然的口语化方式回答。"
            ),
        },
        {"role": "assistant", "content": "好的，我会用口语化的方式回答，控制在 100 字以内。"},
    ]

    logger.info(f"[LLM] 请求中... 输入: {text}")
    completion = client.chat.completions.create(
        model=model_name,
        messages=messages + [{"role": "user", "content": text}],
    )
    response_text = completion.choices[0].message.content
    logger.info(f"[LLM] 回复: {response_text}")
    return response_text


async def get_llm_response_stream(
    messages: list[dict],
    api_key: str,
    base_url: str,
    model_name: str,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> AsyncGenerator[str, None]:
    """
    流式 LLM 调用 — 使用调用方传入的动态模型参数，逐 chunk 产出内容。

    与同步的 get_llm_response() 不同：
    - 使用 AsyncOpenAI 客户端实现 async 流式调用
    - 模型参数由调用方传入（每个用户可使用自己的 AI 模型配置）
    - 产出文本 chunks，由调用方组装

    Args:
        messages: 完整消息上下文 [{"role":"system","content":"..."}, ...]
        api_key: 调用方解密后的 API Key
        base_url: API 地址（如 https://api.deepseek.com/v1）
        model_name: 模型名称（如 deepseek-chat）
        temperature: 温度参数
        max_tokens: 最大 token 数

    Yields:
        逐 chunk 的文本内容
    """
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    logger.info(f"[LLM-Stream] 开始流式调用: model={model_name}, messages={len(messages)}")

    stream = await client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield delta.content

    logger.info(f"[LLM-Stream] 流式调用完成")
