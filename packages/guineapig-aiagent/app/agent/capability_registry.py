"""
能力注册表 — 实时扫描当前可用能力，格式化输出给 LLM。

扫描来源：
- MCP: 从调用方传入的 MCP 服务列表（backend 从 MySQL 加载后传入）；
        对非 stdio 的服务主动调用 list_tools() 获取完整 inputSchema
- CLI: 固定可用（aiagent 认定 CLI 能力存在）
- Skill: 从调用方传入的 skills 列表
- Web Search: 依赖 SEARXNG_URL 配置
- RAG: 依赖 MILVUS_HOST 配置
- Memory: 总是可用
- LLM: 总是可用
"""

import asyncio

from datetime import datetime, timezone

from app.config import settings
from app.core.log import logger

from .models import (
    CapabilityInfo,
    CapabilityInventory,
    CapabilityType,
    ExecutionLocation,
    MCPToolInfo,
)

# 单服务器 list_tools 超时（秒）
_MCP_LIST_TOOLS_TIMEOUT = 10


class CapabilityRegistry:
    """能力注册表 — 每次调用时实时扫描当前可用能力。"""

    @classmethod
    async def scan(
        cls,
        mcp_servers: list[MCPToolInfo] | None = None,
        skills: list[dict] | None = None,
        rag_context: dict | None = None,
    ) -> CapabilityInventory:
        """
        扫描并返回当前完整能力清单。

        对非 stdio MCP 服务器主动调用 list_tools() 获取完整
        inputSchema（参数名称、类型、描述、必填），
        让 LLM 能理解每个工具的正确调用方式。

        Args:
            mcp_servers: 已注册的 MCP 服务列表（由 backend 传入）
            skills: 用户已开启的 Skill 列表（由 backend 传入）
            rag_context: RAG 上下文配置（不为空表示 RAG 可用）

        Returns:
            当前可用的完整能力清单
        """
        capabilities: list[CapabilityInfo] = []

        # 1. MCP — 从传入列表扫描 + 主动拉取完整 schema
        if mcp_servers:
            for srv in mcp_servers:
                loc = (
                    ExecutionLocation.CLIENT
                    if srv.transport_type == "stdio"
                    else ExecutionLocation.SERVER
                )
                tools = list(srv.tools)  # 默认使用传入的工具列表

                # 非 stdio 类型且有 URL → 主动调用 list_tools()
                if srv.transport_type != "stdio" and srv.mcp_url:
                    try:
                        full_tools = await asyncio.wait_for(
                            cls._fetch_mcp_tools(srv),
                            timeout=_MCP_LIST_TOOLS_TIMEOUT,
                        )
                        if full_tools:
                            logger.info(
                                f"[CapabilityRegistry] {srv.server_name} "
                                f"list_tools() 获取 {len(full_tools)} 个工具（含 inputSchema）"
                            )
                            tools = full_tools
                    except asyncio.TimeoutError:
                        logger.warning(
                            f"[CapabilityRegistry] {srv.server_name} "
                            f"list_tools() 超时（{_MCP_LIST_TOOLS_TIMEOUT}s），"
                            "使用已缓存工具信息"
                        )
                    except Exception as e:
                        logger.warning(
                            f"[CapabilityRegistry] {srv.server_name} "
                            f"list_tools() 失败: {e}，使用已缓存工具信息"
                        )

                capabilities.append(
                    CapabilityInfo(
                        type=CapabilityType.MCP,
                        name=f"mcp_{srv.server_name}",
                        description=f"MCP [{srv.server_name}]({srv.transport_type})",
                        execution_location=loc,
                        tools=tools,
                    )
                )

        # 2. CLI — 始终可用
        capabilities.append(
            CapabilityInfo(
                type=CapabilityType.CLI,
                name="cli",
                description="CLI 命令行: 可执行任意 shell 命令",
                execution_location=ExecutionLocation.CLIENT,
            )
        )

        # 3. Skill — 从传入列表扫描
        if skills:
            for sk in skills:
                sk_name = sk.get("name", "") if isinstance(sk, dict) else getattr(sk, "name", "")
                if sk_name:
                    capabilities.append(
                        CapabilityInfo(
                            type=CapabilityType.SKILL,
                            name=f"skill_{sk_name}",
                            description=f"Skill [{sk_name}]",
                            execution_location=ExecutionLocation.CLIENT,
                        )
                    )

        # 4. Web Search — 依赖 SearXNG 配置
        web_search_available = bool(settings.SEARXNG_URL)
        if web_search_available:
            capabilities.append(
                CapabilityInfo(
                    type=CapabilityType.WEB_SEARCH,
                    name="web_search",
                    description="联网搜索: 通过 SearXNG 搜索互联网信息",
                    execution_location=ExecutionLocation.SERVER,
                )
            )

        # 5. RAG — 依赖 Milvus 配置 + 传入的 rag_context
        rag_available = bool(settings.MILVUS_HOST) and rag_context is not None
        if rag_available:
            kb_list = rag_context.get("rag_names", []) if isinstance(rag_context, dict) else []
            kb_desc = ", ".join(kb_list) if kb_list else "已配置的知识库"
            capabilities.append(
                CapabilityInfo(
                    type=CapabilityType.RAG,
                    name="rag",
                    description=f"RAG 知识库检索 [{kb_desc}]",
                    execution_location=ExecutionLocation.SERVER,
                )
            )

        # 6. Memory — 始终可用
        capabilities.append(
            CapabilityInfo(
                type=CapabilityType.MEMORY,
                name="memory",
                description="情景记忆: 回顾历史对话和经验",
                execution_location=ExecutionLocation.SERVER,
            )
        )

        # 7. LLM — 始终可用
        capabilities.append(
            CapabilityInfo(
                type=CapabilityType.LLM_CHAT,
                name="llm_chat",
                description="LLM 对话: 通用问答和文本处理",
                execution_location=ExecutionLocation.SERVER,
            )
        )

        inventory = CapabilityInventory(
            capabilities=capabilities,
            scanned_at=datetime.now(timezone.utc).isoformat(),
        )

        logger.debug(f"[CapabilityRegistry] 扫描完成: {len(capabilities)} 个能力")
        return inventory

    @classmethod
    async def _fetch_mcp_tools(cls, srv: MCPToolInfo) -> list[dict]:
        """
        通过 MCP Python SDK 连接服务器，调用 list_tools() 获取完整工具 schema。

        Returns:
            每项含 name / description / input_schema 的字典列表。
            失败时返回空列表（由调用方处理降级）。
        """
        from mcp import ClientSession

        headers = srv.headers or {}
        transport_type = srv.transport_type

        try:
            if transport_type == "sse":
                from mcp.client.sse import sse_client

                async with sse_client(url=srv.mcp_url, headers=headers) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.list_tools()
            else:
                # streamable_http
                try:
                    from mcp.client.streamable_http import (
                        streamablehttp_client as make_transport,
                    )
                except ImportError:
                    from mcp.client.streamable_http import (
                        streamable_http_client as make_transport,
                    )
                async with make_transport(url=srv.mcp_url, headers=headers) as (
                    read,
                    write,
                    _,
                ):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.list_tools()

            # 格式化为含完整 input_schema 的 dict 列表
            tool_list = []
            for tool in result.tools:
                tool_dict = {
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": tool.inputSchema if hasattr(tool, "inputSchema") else {},
                }
                tool_list.append(tool_dict)
            return tool_list

        except Exception as e:
            logger.warning(
                f"[CapabilityRegistry] _fetch_mcp_tools 失败: "
                f"server={srv.server_name}, transport={transport_type}, err={e}"
            )
            return []

    @classmethod
    def format_for_llm(cls, inventory: CapabilityInventory) -> str:
        """
        将能力清单格式化为 LLM 可读的文本。

        对于包含 input_schema 的 MCP 工具，显示完整的参数签名，
        让 LLM 知道每个参数的名称、类型、描述、是否必填。

        Returns:
            格式化字符串，可直接注入 LLM system prompt
        """
        lines = ["## 当前你可用的能力"]
        for cap in inventory.capabilities:
            if not cap.enabled:
                continue
            tools_part = ""
            if cap.tools:
                tool_descs = []
                for t in cap.tools:
                    if isinstance(t, dict):
                        name = t.get("name", "")
                        desc = t.get("description", "")
                        input_schema = t.get("input_schema", {})

                        if input_schema and isinstance(input_schema, dict) and input_schema.get("properties"):
                            # 有完整 input_schema → 生成参数签名
                            params_display = cls._format_params(input_schema)
                            if desc:
                                tool_descs.append(f"{name}({params_display}) - {desc}")
                            else:
                                tool_descs.append(f"{name}({params_display})")
                        elif name and desc:
                            tool_descs.append(f"{name}({desc})")
                        elif name:
                            tool_descs.append(name)
                    else:
                        tool_descs.append(str(t))
                tools_part = "\n    Tools: " + "\n    \u2022 ".join(tool_descs)
            loc_mark = "\U0001f5b0\ufe0f" if cap.execution_location == ExecutionLocation.SERVER else "\U0001f4bb"
            lines.append(f"- {loc_mark} {cap.description}{tools_part}")

        if len(lines) == 1:
            lines.append("  (当前无可用能力)")

        return "\n".join(lines)

    @classmethod
    def _format_params(cls, input_schema: dict) -> str:
        """
        从 input_schema (JSON Schema) 生成参数字符串。

        Example:
            input_schema = {
                "properties": {
                    "city": {"type": "string", "description": "城市名"},
                    "days": {"type": "integer", "description": "天数"},
                },
                "required": ["city"]
            }
            -> "city: string[required], days: integer[optional]"
        """
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])
        if not properties:
            return ""

        parts = []
        for param_name, param_schema in properties.items():
            if isinstance(param_schema, dict):
                param_type = param_schema.get("type", "any")
                param_desc = param_schema.get("description", "")
                is_required = param_name in required
                req_str = "required" if is_required else "optional"
                if param_desc:
                    parts.append(f"{param_name}: {param_type}[{req_str}] ({param_desc})")
                else:
                    parts.append(f"{param_name}: {param_type}[{req_str}]")
            else:
                parts.append(f"{param_name}: any")

        return ", ".join(parts)
