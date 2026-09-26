"""
CapabilityRegistry 两级能力清单测试 — scan_light 零网络 + enrich_mcp 默认纯透传。
"""

import pytest

from app.agent.capability_registry import CapabilityRegistry
from app.agent.models import MCPToolInfo


def _srv(name="amap", transport="sse", url="http://mcp:9000", tools=None):
    return MCPToolInfo(
        server_name=name,
        transport_type=transport,
        mcp_url=url,
        tools=tools
        or [{"name": f"{name}_tool", "description": "desc", "input_schema": {"type": "object"}}],
    )


class TestScanLight:
    @pytest.mark.asyncio
    async def test_scan_light_no_network(self, mocker):
        """scan_light 不应触发 _fetch_mcp_tools（零网络）"""
        spy = mocker.spy(CapabilityRegistry, "_fetch_mcp_tools")
        inv = await CapabilityRegistry.scan_light(
            mcp_servers=[_srv(transport="sse"), _srv("cli_srv", transport="stdio", url="")],
        )
        assert not spy.called
        names = {c.name for c in inv.capabilities}
        assert "mcp_amap" in names
        assert "mcp_cli_srv" in names
        # stdio 工具保留传入的 input_schema
        mcp_caps = [c for c in inv.capabilities if c.name == "mcp_cli_srv"]
        assert mcp_caps[0].tools[0]["input_schema"] is not None

    @pytest.mark.asyncio
    async def test_scan_light_includes_local(self):
        """scan_light 应包含本地能力（cli/web_search/memory/llm）"""
        inv = await CapabilityRegistry.scan_light()
        names = {c.name for c in inv.capabilities}
        assert "cli" in names
        assert "web_search" in names
        assert "memory" in names
        assert "llm_chat" in names


class TestEnrichMcp:
    @pytest.mark.asyncio
    async def test_enrich_default_passthrough_no_list_tools(self, mocker):
        """默认不调 list_tools，直接透传 backend 传入的数据库快照 tools"""
        from app.config import settings

        fetch = mocker.patch.object(CapabilityRegistry, "_fetch_mcp_tools")
        mocker.patch.object(settings, "MCP_TOOLS_REFRESH", False)
        tools = [{"name": "snapshot_tool", "input_schema": {"type": "object"}}]
        srv = _srv(tools=tools)

        enriched = await CapabilityRegistry.enrich_mcp([srv])

        assert not fetch.called
        assert enriched[0].tools == tools

    @pytest.mark.asyncio
    async def test_enrich_remote_refreshes_when_enabled(self, mocker):
        """MCP_TOOLS_REFRESH=true 且 remote 类型时才调用 list_tools"""
        from app.config import settings

        full_tools = [{"name": "fresh_tool", "input_schema": {}}]
        fetch = mocker.patch.object(
            CapabilityRegistry, "_fetch_mcp_tools", return_value=full_tools
        )
        mocker.patch.object(settings, "MCP_TOOLS_REFRESH", True)
        srv = _srv(transport="sse", url="http://mcp:9000")

        enriched = await CapabilityRegistry.enrich_mcp([srv])

        fetch.assert_called_once()
        assert enriched[0].tools == full_tools

    @pytest.mark.asyncio
    async def test_enrich_stdio_never_list_tools(self, mocker):
        """stdio 类型即使开启刷新也不调 list_tools，保留传入快照"""
        from app.config import settings

        fetch = mocker.patch.object(CapabilityRegistry, "_fetch_mcp_tools")
        mocker.patch.object(settings, "MCP_TOOLS_REFRESH", True)
        tools = [{"name": "local_tool", "input_schema": {"type": "object"}}]
        srv = _srv(transport="stdio", url="", tools=tools)

        enriched = await CapabilityRegistry.enrich_mcp([srv])

        assert not fetch.called
        assert enriched[0].tools == tools

    @pytest.mark.asyncio
    async def test_enrich_refresh_failure_uses_passed_tools(self, mocker):
        """刷新失败应降级使用传入的 tools"""
        from app.config import settings

        mocker.patch.object(
            CapabilityRegistry, "_fetch_mcp_tools", side_effect=Exception("boom")
        )
        mocker.patch.object(settings, "MCP_TOOLS_REFRESH", True)
        tools = [{"name": "fallback_tool"}]
        srv = _srv(tools=tools)

        enriched = await CapabilityRegistry.enrich_mcp([srv])

        assert enriched[0].tools == tools