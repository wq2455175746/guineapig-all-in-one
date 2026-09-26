"""
能力注册表 — 实时扫描当前可用能力，格式化输出给 LLM。

扫描来源：
- MCP: 从调用方传入的 MCP 服务列表（backend 从数据库读取完整快照后传入，
        含 name / description / input_schema）。默认不主动调用 list_tools() 刷新 ——
        MCP tools 由 client 注册时同步到数据库，一般不会频繁变化。
        如需强制刷新可配置 MCP_TOOLS_REFRESH=true。
- CLI: 固定可用（aiagent 认定 CLI 能力存在）
- Skill: 从调用方传入的 skills 列表
- Web Search: 依赖 SEARXNG_URL 配置
- RAG: 依赖 MILVUS_HOST 配置
- Memory: 总是可用
- LLM: 总是可用
"""

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

    # ── 轻量清单（零网络，默认路径） ──

    @classmethod
    async def scan_light(
        cls,
        mcp_servers: list[MCPToolInfo] | None = None,
        skills: list[dict] | None = None,
        rag_context: dict | None = None,
    ) -> CapabilityInventory:
        """
        轻量能力扫描 — 零网络调用（默认路径）。

        直接使用调用方传入的 tools（含完整 input_schema，由 backend 从数据库同步），
        不调用 list_tools()。MCP tools 接口一般不常变，数据库快照足够。

        Args:
            mcp_servers: 已注册的 MCP 服务列表（由 backend 传入）
            skills: 用户已开启的 Skill 列表
            rag_context: RAG 上下文配置（不为空表示 RAG 可用）

        Returns:
            当前可用的完整能力清单
        """
        capabilities: list[CapabilityInfo] = []

        # 1. MCP — 从传入列表注册（直接用传入的 tools，零网络）
        if mcp_servers:
            for srv in mcp_servers:
                loc = (
                    ExecutionLocation.CLIENT
                    if srv.transport_type == "stdio"
                    else ExecutionLocation.SERVER
                )
                tools = await cls._maybe_refresh_tools(srv)
                capabilities.append(
                    CapabilityInfo(
                        type=CapabilityType.MCP,
                        name=f"mcp_{srv.server_name}",
                        description=f"MCP [{srv.server_name}]({srv.transport_type})",
                        execution_location=loc,
                        tools=tools,
                    )
                )

                # 日志：每个 MCP server 的工具加载明细
                tool_names = []
                with_schema = 0
                for t in tools:
                    if isinstance(t, dict):
                        tname = t.get("name", "")
                        if tname:
                            tool_names.append(tname)
                        if t.get("input_schema"):
                            with_schema += 1
                    else:
                        tool_names.append(str(t))
                logger.info(
                    f"[CapabilityRegistry] MCP server '{srv.server_name}' "
                    f"加载 {len(tools)} 个工具, "
                    f"{with_schema}/{len(tools)} 含 input_schema, "
                    f"transport={srv.transport_type}, loc={loc.value}"
                )
                logger.debug(
                    f"[CapabilityRegistry] MCP server '{srv.server_name}' "
                    f"tools: {tool_names}"
                )

        capabilities.extend(cls._build_local_capabilities(skills, rag_context))

        inventory = CapabilityInventory(
            capabilities=capabilities,
            scanned_at=datetime.now(timezone.utc).isoformat(),
        )

        cap_summary = [
            f"{c.name}({len(c.tools)} tools)"
            if c.tools else c.name
            for c in capabilities
        ]
        logger.info(
            f"[CapabilityRegistry] 扫描完成: {len(capabilities)} 个能力: "
            f"{', '.join(cap_summary)}"
        )
        return inventory

    # ── 富化清单（默认纯透传数据库快照） ──

    @classmethod
    async def enrich_mcp(
        cls,
        mcp_servers: list[MCPToolInfo] | None = None,
    ) -> list[MCPToolInfo]:
        """
        富化 MCP 服务器工具信息 — 默认直接透传 backend 传入的数据库快照。

        不主动调用 list_tools()：MCP tools 由 client 注册时同步到数据库
        （含完整 input_schema），接口一般不常变。仅当 MCP_TOOLS_REFRESH=true 时
        才对 remote 类型主动刷新。

        Args:
            mcp_servers: 已注册的 MCP 服务列表（由 backend 传入）

        Returns:
            富化后的 MCP 服务列表（原对象拷贝）
        """
        if not mcp_servers:
            return []

        enriched: list[MCPToolInfo] = []
        for srv in mcp_servers:
            new_srv = srv.model_copy(deep=True)
            # 默认不刷新：保留 backend 传入的数据库快照 tools
            new_srv.tools = await cls._maybe_refresh_tools(srv)
            enriched.append(new_srv)
        return enriched

    @classmethod
    async def _maybe_refresh_tools(cls, srv: MCPToolInfo) -> list[dict]:
        """
        按 MCP_TOOLS_REFRESH 配置决定是否刷新 tools。

        默认（False）直接返回传入快照；仅 True 时对 remote 类型调用 list_tools()。
        刷新失败时降级使用传入快照。
        """
        if settings.MCP_TOOLS_REFRESH and srv.transport_type != "stdio" and srv.mcp_url:
            try:
                full_tools = await cls._fetch_mcp_tools(srv)
                if full_tools:
                    logger.info(
                        f"[CapabilityRegistry] {srv.server_name} "
                        f"list_tools() 刷新 {len(full_tools)} 个工具（含 input_schema）"
                    )
                    return full_tools
            except Exception as e:
                logger.warning(
                    f"[CapabilityRegistry] {srv.server_name} list_tools() 刷新失败: {e}，"
                    "使用 backend 传入的数据库快照 tools"
                )
        return list(srv.tools)

    # ── 本地能力组合（零网络） ──

    @classmethod
    def _build_local_capabilities(
        cls,
        skills: list[dict] | None = None,
        rag_context: dict | None = None,
    ) -> list[CapabilityInfo]:
        """组装纯本地能力：CLI / Skill / WebSearch / RAG / Memory / LLM。"""
        capabilities: list[CapabilityInfo] = []

        # CLI — 始终可用
        capabilities.append(
            CapabilityInfo(
                type=CapabilityType.CLI,
                name="cli",
                description="CLI 命令行: 可执行任意 shell 命令",
                execution_location=ExecutionLocation.CLIENT,
            )
        )

        # Skill — 从传入列表扫描
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

        # Web Search — 依赖 SearXNG 配置
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

        # RAG — 依赖 Milvus 配置 + 传入的 rag_context
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

        # Memory — 始终可用
        capabilities.append(
            CapabilityInfo(
                type=CapabilityType.MEMORY,
                name="memory",
                description="情景记忆: 回顾历史对话和经验",
                execution_location=ExecutionLocation.SERVER,
            )
        )

        # LLM — 始终可用
        capabilities.append(
            CapabilityInfo(
                type=CapabilityType.LLM_CHAT,
                name="llm_chat",
                description="LLM 对话: 通用问答和文本处理",
                execution_location=ExecutionLocation.SERVER,
            )
        )

        return capabilities

    @classmethod
    async def scan(
        cls,
        mcp_servers: list[MCPToolInfo] | None = None,
        skills: list[dict] | None = None,
        rag_context: dict | None = None,
    ) -> CapabilityInventory:
        """
        完整能力扫描 — 兼容原有调用方。

        默认直接用 backend 传入的数据库快照 tools（含 input_schema），
        不主动调 list_tools()。仅 MCP_TOOLS_REFRESH=true 时刷新。
        """
        return await cls.scan_light(
            mcp_servers=mcp_servers,
            skills=skills,
            rag_context=rag_context,
        )

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
        logger.info(
            f"[CapabilityRegistry] format_for_llm 开始: "
            f"{len(inventory.capabilities)} 个能力"
        )
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
            # 展示确切能力标识符，DAG 生成时 capability 字段必须原样使用它
            lines.append(f"- {loc_mark} `{cap.name}` — {cap.description}{tools_part}")

        if len(lines) == 1:
            lines.append("  (当前无可用能力)")

        result_text = "\n".join(lines)
        logger.info(
            f"[CapabilityRegistry] format_for_llm 完成: "
            f"{len(result_text)} 字符, {len(lines) - 1} 个能力"
        )
        return result_text

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