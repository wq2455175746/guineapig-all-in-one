"""
能力执行处理器 — Server 端能力的实际执行逻辑。

每个处理器函数接受 DAGStep params，返回执行结果 dict。

Client 端能力（cli/skill/stdio MCP）返回 awaiting_client 信号，
由 executor engine 封装为 STEP_AWAITING_CLIENT 事件。
集成 Langfuse 可观测性：追踪每个 DAG 步骤的执行。
"""

import asyncio
import json
from typing import Any

import httpx

from app.config import settings
from app.core.log import logger
from app.services.rag_retrieval_service import retrieve_rag_context
from app.services.handle_llmservice import get_llm_response
from app.services.langfuse_client import get_langfuse, is_langfuse_enabled


class CapabilityHandlers:
    """Server 端能力处理器 — 统一接口: handle(step_params: dict) -> dict"""

    # Client 端能力类型列表（这些能力 executor 不做实际执行）
    CLIENT_ONLY_CAPABILITIES = {"cli", "skill"}

    # ── Web Search ──

    @staticmethod
    async def handle_web_search(params: dict) -> dict:
        """联网搜索 — 通过 SearXNG"""
        query = params.get("query", params.get("q", ""))
        max_results = int(params.get("max_results", params.get("maxResults", 5)))

        if not query:
            return {"error": "搜索关键词为空", "result": ""}

        if not settings.SEARXNG_URL:
            return {"error": "SearXNG 未配置", "result": ""}

        url = f"{settings.SEARXNG_URL}/search"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    url,
                    params={"q": query, "format": "json", "language": "zh"},
                )
                resp.raise_for_status()
                data = resp.json()

            results = data.get("results", [])
            if not results:
                return {"result": "未找到相关结果", "count": 0}

            lines = [f"## 联网搜索结果: {query}"]
            for i, r in enumerate(results[:max_results], 1):
                title = r.get("title", "")
                snippet = r.get("content", "")
                link = r.get("url", "")
                lines.append(f"{i}. **{title}**")
                if snippet:
                    lines.append(f"   {snippet}")
                if link:
                    lines.append(f"   [{link}]({link})")

            result_text = "\n".join(lines)
            return {"result": result_text, "count": len(results[:max_results])}

        except httpx.TimeoutException:
            logger.warning(f"[Handler] Web search timeout: query={query}")
            return {"error": "联网搜索超时", "result": ""}
        except Exception as e:
            logger.error(f"[Handler] Web search failed: {e}")
            return {"error": f"联网搜索失败: {e}", "result": ""}

    # ── RAG ──

    @staticmethod
    async def handle_rag(params: dict) -> dict:
        """知识库检索 — 通过 Milvus"""
        query = params.get("query", params.get("q", ""))
        rag_names = params.get("rag_names", params.get("collection_names", []))

        if not query:
            return {"error": "检索关键词为空", "result": ""}

        if not rag_names:
            return {"error": "未指定知识库名称", "result": ""}

        try:
            # 同步调用包装为 async
            result = await asyncio.to_thread(
                retrieve_rag_context,
                rag_names=rag_names,
                user_id=params.get("user_id", 0),
                query=query,
                embedding_api_url=settings.LLM_BASE_URL,
                embedding_api_key=settings.LLM_API_KEY,
                embedding_model_name=settings.LLM_MODEL_NAME,
                reranker_api_url=settings.LLM_BASE_URL,
                reranker_api_key=settings.LLM_API_KEY,
                reranker_model_name=settings.LLM_MODEL_NAME,
                milvus_host=settings.MILVUS_HOST,
                milvus_port=settings.MILVUS_PORT,
                top_k=params.get("top_k", 20),
                rerank_top_k=params.get("rerank_top_k", 3),
            )

            return {"result": result, "has_result": bool(result)}

        except Exception as e:
            logger.error(f"[Handler] RAG search failed: {e}")
            return {"error": f"知识库检索失败: {e}", "result": ""}

    # ── LLM Chat ──

    @staticmethod
    async def handle_llm_chat(params: dict) -> dict:
        """LLM 对话 — 非流式调用"""
        prompt = params.get("prompt", params.get("text", params.get("query", "")))
        system_prompt = params.get("system_prompt", "")

        if not prompt:
            return {"error": "提示词为空", "result": ""}

        try:
            # 构建带 system prompt 的消息
            if system_prompt:
                # 用完整的消息结构调用
                from openai import OpenAI

                client = OpenAI(
                    api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL
                )
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ]

                # ── Langfuse Generation Span (SDK v4) ──
                langfuse_gen = None
                if is_langfuse_enabled():
                    langfuse = get_langfuse()
                    langfuse_gen = langfuse.start_observation(
                        name="handler-llm-chat",
                        as_type="generation",
                        model=settings.LLM_MODEL_NAME,
                        input=messages,
                        metadata={"handler": "handle_llm_chat", "has_system_prompt": True},
                    )

                completion = client.chat.completions.create(
                    model=settings.LLM_MODEL_NAME,
                    messages=messages,
                    temperature=params.get("temperature", 0.7),
                    max_tokens=params.get("max_tokens", 2048),
                )
                response_text = completion.choices[0].message.content or ""

                # ── 结束 Langfuse Generation Span (SDK v4) ──
                if langfuse_gen:
                    usage = completion.usage
                    update_kwargs = {"output": response_text}
                    if usage:
                        update_kwargs["usage_details"] = {
                            "input": usage.prompt_tokens,
                            "output": usage.completion_tokens,
                        }
                    langfuse_gen.update(**update_kwargs)
                    langfuse_gen.end()
            else:
                response_text = get_llm_response(prompt)

            return {"result": response_text, "char_count": len(response_text)}

        except Exception as e:
            logger.error(f"[Handler] LLM chat failed: {e}")
            return {"error": f"LLM 对话失败: {e}", "result": ""}

    # ── Memory Retrieve ──

    @staticmethod
    async def handle_memory_retrieve(params: dict) -> dict:
        """记忆检索 — 通过 Backend API"""
        query = params.get("query", params.get("text", ""))
        user_id = params.get("user_id", 0)

        if not query:
            return {"error": "记忆检索关键词为空", "result": ""}

        if not settings.BACKEND_BASE_URL:
            return {"error": "Backend URL 未配置", "result": ""}

        try:
            url = f"{settings.BACKEND_BASE_URL}/api/v1/memory/search"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    json={
                        "user_id": user_id,
                        "query": query,
                        "limit": params.get("limit", 10),
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            memories = data.get("result", data.get("data", []))
            if not memories:
                return {"result": "未找到相关记忆", "count": 0}

            lines = ["## 历史记忆检索结果"]
            for m in memories:
                content = m.get("content", m.get("text", ""))
                created = m.get("created_at", m.get("timestamp", ""))
                mtype = m.get("type", m.get("memory_type", "unknown"))
                lines.append(f"- [{mtype}] {content} ({created})")

            return {"result": "\n".join(lines), "count": len(memories)}

        except httpx.TimeoutException:
            return {"error": "记忆检索超时", "result": ""}
        except Exception as e:
            logger.warning(
                f"[Handler] Memory retrieve failed (may not be implemented): {e}"
            )
            return {"error": f"记忆检索失败: {e}", "result": ""}

    # ── Memory Summarize ──

    @staticmethod
    async def handle_memory_summarize(params: dict) -> dict:
        """记忆总结 — 通过 Backend API"""
        content = params.get("content", params.get("text", ""))
        user_id = params.get("user_id", 0)

        if not content:
            return {"error": "总结内容为空", "result": ""}

        if not settings.BACKEND_BASE_URL:
            return {"error": "Backend URL 未配置", "result": ""}

        try:
            url = f"{settings.BACKEND_BASE_URL}/api/v1/memory/summarize"
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    url,
                    json={
                        "user_id": user_id,
                        "content": content,
                        "session_id": params.get("session_id", ""),
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            return {
                "result": data.get("result", data.get("summary", "总结完成")),
                "success": True,
            }

        except httpx.TimeoutException:
            return {"error": "记忆总结超时", "result": ""}
        except Exception as e:
            logger.warning(f"[Handler] Memory summarize failed: {e}")
            return {"error": f"记忆总结失败: {e}", "result": ""}

    # ── MCP Server (sse/streamable_http) ──

    @staticmethod
    async def handle_mcp_call(params: dict, server_name: str = "") -> dict:
        """MCP 工具调用 — 通过 MCP Python SDK（支持 streamable-http 和 SSE）"""
        from mcp import ClientSession

        tool_name = params.get("tool", params.get("tool_name", ""))
        tool_args = params.get(
            "args", params.get("arguments", params.get("params", {}))
        )
        if not isinstance(tool_args, dict):
            tool_args = {}
        mcp_url = params.get("mcp_url", params.get("server_url", ""))
        headers = params.get("headers", {})
        transport_type = params.get(
            "transport_type", "streamable-http"
        )

        if not tool_name:
            return {"error": "MCP 工具名称为空", "result": ""}

        if not mcp_url:
            return {"error": "MCP server URL 未提供", "result": ""}

        try:
            if transport_type == "sse":
                from mcp.client.sse import sse_client

                async with sse_client(url=mcp_url, headers=headers) as (
                    read,
                    write,
                ):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(
                            tool_name, arguments=tool_args
                        )
            else:
                # streamable-http (默认，SSE 已废弃)
                # mcp>=1.20.0 用 streamablehttp_client, 1.8~1.19 用 streamable_http_client
                try:
                    from mcp.client.streamable_http import (
                        streamablehttp_client as make_streamable_http,
                    )
                except ImportError:
                    from mcp.client.streamable_http import (
                        streamable_http_client as make_streamable_http,
                    )

                async with make_streamable_http(
                    url=mcp_url, headers=headers
                ) as (read, write, _get_session_id):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(
                            tool_name, arguments=tool_args
                        )

            # 解析 result.content
            text_parts = []
            for item in result.content or []:
                if hasattr(item, "text") and item.text:
                    text_parts.append(item.text)
                else:
                    text_parts.append(str(item))

            return {
                "result": "\n".join(text_parts),
                "tool": tool_name,
                "success": not getattr(result, "is_error", False),
            }

        except Exception as e:
            logger.error(
                f"[Handler] MCP call failed: server={server_name}, tool={tool_name}, "
                f"transport={transport_type}, err={e}"
            )
            return {"error": f"MCP 调用失败: {e}", "result": ""}

    # ── 通用分发 ──

    @classmethod
    async def execute(cls, capability: str, params: dict) -> dict:
        """
        根据能力名称自动分发到对应处理器。

        Args:
            capability: 能力名称 (如 web_search, rag, llm_chat, mcp_filesystem)
            params: 执行参数

        Returns:
            执行结果 dict
        """
        # 检查是否为 client 端能力
        if capability in cls.CLIENT_ONLY_CAPABILITIES:
            return {
                "action": "awaiting_client",
                "reason": f"'{capability}' 需要在 Client 端执行",
            }

        # MCP 能力
        if capability.startswith("mcp_"):
            server_name = capability[4:]  # 去掉 "mcp_" 前缀
            # 安全检查：transport_type=stdio 的 MCP 应已在 engine 层被拦截
            if params.get("transport_type") == "stdio":
                return {
                    "action": "awaiting_client",
                    "reason": f"MCP '{server_name}' (stdio) 需要在 Client 端执行",
                }
            return await cls.handle_mcp_call(params, server_name=server_name)

        # 按能力名称分发
        handler_map = {
            "web_search": cls.handle_web_search,
            "rag": cls.handle_rag,
            "llm_chat": cls.handle_llm_chat,
            "llm_analysis": cls.handle_llm_chat,
            "memory": cls.handle_memory_retrieve,
            "memory_retrieve": cls.handle_memory_retrieve,
            "memory_summarize": cls.handle_memory_summarize,
        }

        handler = handler_map.get(capability)
        if handler is None:
            return {"error": f"未知能力: {capability}", "result": ""}

        return await handler(params)
