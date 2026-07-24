"""
LLM Pipeline — 有序的 Processor 链，用于流式 LLM 调用的前置/后置处理。

每个 Processor 实现 async process(ctx) 方法，读取和修改 PipelineContext。
Pipeline 按序串行执行 Processors，任何 Processor 设置 ctx.error 会短路后续流程。

新增能力（MCP、RAG、知识库等）只需：
1. 创建新的 Processor 类
2. 在 Pipeline 的 processors 列表中按序插入
"""

import json
import inspect
from dataclasses import dataclass, field
from typing import Optional

from app.core.log import logger


@dataclass
class PipelineContext:
    """Pipeline 共享上下文 — Processors 通过修改此对象交换数据。"""

    # 原始请求数据
    messages: list[dict]
    api_key: str
    base_url: str
    model_name: str
    temperature: float = 0.7
    max_tokens: int = 2048

    # 可选标志和数据
    skills: Optional[list] = None
    user_id: Optional[int] = None
    web_search_enabled: bool = False
    rag_context: Optional[dict] = None

    # Processor 输出状态
    full_content: str = ""
    commands: list[dict] = field(default_factory=list)
    error: Optional[str] = None

    # 内部状态（Processors 间传递）
    _selected_skill_names: list = field(default_factory=list)
    _skill_context_loaded: bool = False

    def has_error(self) -> bool:
        return self.error is not None


class BaseProcessor:
    """所有 Processor 的基类。默认 process() 为空操作。"""

    async def process(self, ctx: PipelineContext):
        pass


class SkillSelectionProcessor(BaseProcessor):
    """Phase 1: 用 LLM 从启用列表中选择与用户消息相关的技能。"""

    async def process(self, ctx: PipelineContext) -> None:
        if not ctx.skills or not ctx.user_id:
            return

        user_message = ""
        for msg in reversed(ctx.messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break

        if not user_message:
            return

        from app.services.skill_load_service import select_relevant_skills

        try:
            selected = await select_relevant_skills(
                user_message=user_message,
                skills=ctx.skills,
                api_key=ctx.api_key,
                base_url=ctx.base_url,
                model=ctx.model_name,
            )
            logger.info(f"[Pipeline] 选中技能: {selected}")
            ctx._selected_skill_names = selected
        except Exception as e:
            logger.error(f"[Pipeline] 技能选择失败: {e}")
            ctx._selected_skill_names = []


class SkillContextProcessor(BaseProcessor):
    """Phase 2: 从 S3 加载选中技能内容并注入 system prompt。"""

    async def process(self, ctx: PipelineContext) -> None:
        if not ctx._selected_skill_names:
            ctx._skill_context_loaded = False
            return

        from app.services.skill_load_service import load_skill_context, inject_skill_system_prompt

        try:
            skill_context = await load_skill_context(
                skill_names=ctx._selected_skill_names,
                user_id=ctx.user_id,
                skills=ctx.skills,
            )
            if skill_context:
                ctx.messages = inject_skill_system_prompt(ctx.messages, skill_context)
                ctx._skill_context_loaded = True
                logger.info(f"[Pipeline] 注入 {len(ctx._selected_skill_names)} 个技能")
                return
        except Exception as e:
            logger.error(f"[Pipeline] 技能上下文加载失败: {e}")

        ctx._skill_context_loaded = False


class NetworkSearchProcessor(BaseProcessor):
    """
    联网搜索 Processor：当 web_search_enabled=True 时，
    用用户最后一条消息调用 SearXNG，将结果注入 system prompt。
    """

    async def process(self, ctx: PipelineContext) -> None:
        if not ctx.web_search_enabled:
            return

        user_message = ""
        for msg in reversed(ctx.messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break
        if not user_message:
            return

        from app.services.network_search_service import search_web

        search_results = await search_web(user_message, max_results=5)
        if not search_results:
            logger.info("[Pipeline] 无联网搜索结果可注入")
            return

        search_block = (
            "\n\n## 网络搜索结果\n"
            f"{search_results}\n\n"
            "请参考以上网络搜索结果回答用户问题。如果结果相关，请在回答中引用；"
            "如果不相关或为空，忽略它们并正常回答。"
        )

        # 注入到已有的 system message 中
        for msg in ctx.messages:
            if msg.get("role") == "system":
                msg["content"] += search_block
                logger.info("[Pipeline] 已将联网搜索结果注入 system prompt")
                return

        # 没有 system message 时新建一个
        ctx.messages.insert(0, {"role": "system", "content": search_block})


class DefaultSkillInjector(BaseProcessor):
    """回退：未加载技能时注入 Command Generation Rules。"""

    async def process(self, ctx: PipelineContext) -> None:
        if not ctx._skill_context_loaded:
            from app.services.skill_load_service import inject_skill_system_prompt

            ctx.messages = inject_skill_system_prompt(ctx.messages, "")


class RAGRetrievalProcessor(BaseProcessor):
    """
    知识库检索 Processor：当 rag_context 存在时，
    对用户最新消息执行向量搜索，重排后注入 system prompt。
    NetworkSearchProcessor 之后执行，允许多源注入。
    """

    async def process(self, ctx: PipelineContext) -> None:
        rag_ctx = ctx.rag_context
        if not rag_ctx:
            return

        user_message = ""
        for msg in reversed(ctx.messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break
        if not user_message:
            return

        from app.services.rag_retrieval_service import retrieve_rag_context
        from app.config import settings

        try:
            rag_content = retrieve_rag_context(
                rag_names=rag_ctx["rag_names"],
                user_id=ctx.user_id,
                query=user_message,
                embedding_api_url=rag_ctx["embedding_api_url"],
                embedding_api_key=rag_ctx["embedding_api_key"],
                embedding_model_name=rag_ctx["embedding_model_name"],
                reranker_api_url=rag_ctx["reranker_api_url"],
                reranker_api_key=rag_ctx["reranker_api_key"],
                reranker_model_name=rag_ctx["reranker_model_name"],
                milvus_host=settings.MILVUS_HOST,
                milvus_port=settings.MILVUS_PORT,
                top_k=rag_ctx.get("top_k", 20),
                rerank_top_k=rag_ctx.get("rerank_top_k", 3),
            )

            if not rag_content:
                logger.info("[Pipeline] 无 RAG 知识库检索结果")
                return

            # 追加到已有 system message
            for msg in ctx.messages:
                if msg.get("role") == "system":
                    msg["content"] += rag_content
                    logger.info("[Pipeline] 已将 RAG 检索结果注入 system prompt")
                    return

            # 无 system message 时新建
            ctx.messages.insert(0, {"role": "system", "content": rag_content})
        except Exception as e:
            logger.error(f"[Pipeline] RAG 知识库检索失败: {e}")
            # 不阻断流水线，静默返回


class LLMStreamProcessor(BaseProcessor):
    """Phase 3: 调用 LLM 流式接口，逐 chunk 生成 SSE 事件。"""

    async def process(self, ctx: PipelineContext):
        from app.services.handle_llmservice import get_llm_response_stream

        async for chunk in get_llm_response_stream(
            messages=ctx.messages,
            api_key=ctx.api_key,
            base_url=ctx.base_url,
            model_name=ctx.model_name,
            temperature=ctx.temperature,
            max_tokens=ctx.max_tokens,
        ):
            ctx.full_content += chunk
            yield f"data: {json.dumps({'content': chunk})}\n\n"


class CommandParsingProcessor(BaseProcessor):
    """Phase 4: 从 LLM 完整回复中解析 <commands> 标签。"""

    async def process(self, ctx: PipelineContext) -> None:
        from app.services.skill_load_service import parse_commands

        clean_content, commands = parse_commands(ctx.full_content)
        ctx.full_content = clean_content
        ctx.commands = commands


class Pipeline:
    """
    有序 Processor 链。

    - 普通 Processor（async function）：process() 的返回值 await 等待完成。
    - 流式 Processor（async generator）：process() 返回 async generator，
      run_and_yield() 会遍历 yield 的所有事件并透传给上游。

    process() 不是 async 的函数会被当作普通函数调用（同步兼容）。
    """

    def __init__(self, processors: list):
        self.processors = processors

    async def run_and_yield(self, ctx: PipelineContext):
        """
        执行所有 Processors 并按序 yield 事件。

        流式 Processor（如 LLMStreamProcessor）的 SSE 事件被逐条透传。
        所有 Processor 完成后 yield done 事件（携带 commands 供 client 执行）。
        """
        for processor in self.processors:
            if ctx.has_error():
                yield f"data: {json.dumps({'error': ctx.error})}\n\n"
                return

            try:
                result = processor.process(ctx)
                if result is None:
                    continue

                if inspect.isasyncgen(result):
                    async for event in result:
                        yield event
                elif inspect.iscoroutine(result):
                    await result
                else:
                    # 同步调用的结果也可能是一个 generator
                    for item in result:
                        yield item
            except Exception as e:
                ctx.error = str(e)
                logger.error(f"[Pipeline] Processor {processor.__class__.__name__} 失败: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                return

        # 兼容旧流程：没有 LLMStreamProcessor 时直接 done
        result = {"done": True}
        if ctx.commands:
            result["commands"] = ctx.commands
        yield f"data: {json.dumps(result)}\n\n"
        logger.info("[Pipeline] 流式请求完成")
