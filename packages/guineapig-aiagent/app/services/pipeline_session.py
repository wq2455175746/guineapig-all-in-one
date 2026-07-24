"""
single_round_llm — 单轮 LLM 调用 + 命令解析，无 Redis 依赖。

替换旧 PipelineSession（多轮 ReAct + Redis pause/resume）。
每条 SSE 连接只做一次 LLM 调用 → 解析 commands → 返回 done。
无 Redis 依赖，无需跨实例路由。
"""

import json

from app.core.log import logger
from app.services.llm_pipeline import (
    PipelineContext,
    LLMStreamProcessor,
    CommandParsingProcessor,
)


async def single_round_llm(ctx: PipelineContext):
    """
    单轮 LLM 调用 async generator。

    流程：
    1. LLMStreamProcessor — yield content chunks
    2. CommandParsingProcessor — 解析 commands
    3. 最终 yield done{commands}

    每条 SSE = 一次 LLM 调用 = 一条独立消息。
    无 Redis 依赖，无多轮循环，无跨实例路由。
    """
    logger.info("[single_round_llm] 开始单轮 LLM 调用")

    # 1) 运行 LLMStreamProcessor
    llm_streamer = LLMStreamProcessor()
    async for event in llm_streamer.process(ctx):
        yield event

    # 2) 解析 commands
    cmd_parser = CommandParsingProcessor()
    await cmd_parser.process(ctx)

    # 3) done 事件（携带 commands 供 client 执行）
    result = {"done": True}
    if ctx.commands:
        result["commands"] = ctx.commands
    yield f"data: {json.dumps(result)}\n\n"
    logger.info("[single_round_llm] 流式请求完成")
