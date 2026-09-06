"""
DAG 执行引擎单元测试 — 拓扑排序、数据流、事件流、Timeline。

直接测试 DAGExecutionEngine 的 _topological_sort、_resolve_params、
_execute_step 等核心方法（无需 LLM 调用）。
"""

import pytest

from app.agent.models import (
    CapabilityInventory,
    DAGDefinition,
    DAGStep,
    ExecutionLocation,
    StreamEventType,
)
from app.agent.executor.engine import DAGExecutionEngine


class TestTopologicalSort:
    """拓扑排序测试"""

    def test_simple_linear(self):
        """线性依赖: s1 → s2 → s3"""
        dag = DAGDefinition(steps=[
            DAGStep(step_id="s1", capability="web_search", action="search", depends_on=[]),
            DAGStep(step_id="s2", capability="llm_chat", action="summarize", depends_on=["s1"]),
            DAGStep(step_id="s3", capability="llm_chat", action="output", depends_on=["s2"]),
        ])
        engine = DAGExecutionEngine(dag)
        result = engine._topological_sort()
        assert result is not None
        ids = [s.step_id for s in result]
        assert ids == ["s1", "s2", "s3"]

    def test_parallel_steps(self):
        """无依赖 → 任意顺序"""
        dag = DAGDefinition(steps=[
            DAGStep(step_id="a", capability="web_search", action="search"),
            DAGStep(step_id="b", capability="rag", action="retrieve"),
        ])
        engine = DAGExecutionEngine(dag)
        result = engine._topological_sort()
        assert result is not None
        ids = {s.step_id for s in result}
        assert ids == {"a", "b"}

    def test_cyclic_dag(self):
        """循环依赖 → 返回 None"""
        dag = DAGDefinition(steps=[
            DAGStep(step_id="s1", capability="a", action="x", depends_on=["s2"]),
            DAGStep(step_id="s2", capability="b", action="y", depends_on=["s1"]),
        ])
        engine = DAGExecutionEngine(dag)
        result = engine._topological_sort()
        assert result is None

    def test_fan_out(self):
        """扇出: s1 → s2, s1 → s3"""
        dag = DAGDefinition(steps=[
            DAGStep(step_id="s1", capability="web_search", action="search"),
            DAGStep(step_id="s2", capability="llm_chat", action="summarize", depends_on=["s1"]),
            DAGStep(step_id="s3", capability="memory", action="save", depends_on=["s1"]),
        ])
        engine = DAGExecutionEngine(dag)
        result = engine._topological_sort()
        assert result is not None
        ids = [s.step_id for s in result]
        assert ids[0] == "s1"
        assert set(ids[1:]) == {"s2", "s3"}


class TestResolveParams:
    """参数引用解析测试"""

    def test_basic_reference(self):
        """{{s1.result}} 应被替换为 s1 的执行结果"""
        dag = DAGDefinition(steps=[
            DAGStep(step_id="s1", capability="web_search", action="search",
                    params={"query": "AI news"}),
            DAGStep(step_id="s2", capability="llm_chat", action="summarize",
                    params={"text": "{{s1.result}}"}),
        ])
        engine = DAGExecutionEngine(dag)
        engine.step_results["s1"] = {"result": "AI news: ..."}
        resolved = engine._resolve_params(dag.steps[1].params)
        assert resolved["text"] == "AI news: ..."

    def test_multiple_references(self):
        """多个引用同时替换"""
        dag = DAGDefinition(steps=[
            DAGStep(step_id="s1", capability="web_search", action="search",
                    params={"query": "test"}),
        ])
        engine = DAGExecutionEngine(dag)
        engine.step_results["s1"] = {"result": "result1"}
        text = "前序结果: {{s1.result}}，长度: {{s1.char_count}}"
        resolved = engine._resolve_string(text)
        assert "{{s1.result}}" not in resolved
        assert "result1" in resolved

    def test_unresolved_reference(self):
        """不存在的引用应保持原样"""
        engine = DAGExecutionEngine.__new__(DAGExecutionEngine)
        engine.step_results = {}
        text = "{{nonexistent.key}}"
        resolved = engine._resolve_string(text)
        assert resolved == "{{nonexistent.key}}"

    def test_nested_params(self):
        """嵌套 dict 中的引用也应被解析"""
        dag = DAGDefinition(steps=[
            DAGStep(step_id="s1", capability="web_search", action="search",
                    params={"query": "data"}),
            DAGStep(step_id="s2", capability="llm_chat", action="analyze",
                    params={"nested": {"input": "{{s1.result}}"}}),
        ])
        engine = DAGExecutionEngine(dag)
        engine.step_results["s1"] = {"result": "nested_data"}
        resolved = engine._resolve_params(dag.steps[1].params)
        assert resolved["nested"]["input"] == "nested_data"


class TestDependenciesResolved:
    """前置依赖检查测试"""

    def test_all_resolved(self):
        """所有前置依赖已完成"""
        dag = DAGDefinition(steps=[
            DAGStep(step_id="s1", capability="a", action="x"),
            DAGStep(step_id="s2", capability="b", action="y", depends_on=["s1"]),
        ])
        engine = DAGExecutionEngine(dag)
        engine.step_results["s1"] = {"result": "done"}
        assert engine._dependencies_resolved(dag.steps[1]) is True

    def test_not_resolved(self):
        """前置依赖尚未完成"""
        dag = DAGDefinition(steps=[
            DAGStep(step_id="s1", capability="a", action="x"),
            DAGStep(step_id="s2", capability="b", action="y", depends_on=["s1"]),
        ])
        engine = DAGExecutionEngine(dag)
        assert engine._dependencies_resolved(dag.steps[1]) is False

    def test_with_error(self):
        """前置依赖执行失败"""
        dag = DAGDefinition(steps=[
            DAGStep(step_id="s1", capability="a", action="x"),
            DAGStep(step_id="s2", capability="b", action="y", depends_on=["s1"]),
        ])
        engine = DAGExecutionEngine(dag)
        engine.step_results["s1"] = {"error": "failed"}
        assert engine._dependencies_resolved(dag.steps[1]) is False


class TestStreamEvents:
    """SSE 事件结构测试"""

    @pytest.mark.asyncio
    async def test_empty_dag(self):
        """空 DAG → error + execution_complete 事件"""
        dag = DAGDefinition(steps=[], original_intent="empty")
        engine = DAGExecutionEngine(dag)
        events = []
        async for event in engine.execute():
            events.append(event)

        assert len(events) >= 1
        # 第一个事件应该是 error
        assert events[0].event == StreamEventType.ERROR.value

    @pytest.mark.asyncio
    async def test_cyclic_dag(self):
        """循环 DAG → error + execution_complete"""
        dag = DAGDefinition(steps=[
            DAGStep(step_id="s1", capability="a", action="x", depends_on=["s2"]),
            DAGStep(step_id="s2", capability="b", action="y", depends_on=["s1"]),
        ])
        engine = DAGExecutionEngine(dag)
        events = []
        async for event in engine.execute():
            events.append(event)

        assert len(events) >= 1

    @pytest.mark.asyncio
    async def test_client_step(self):
        """Client 端步骤 → awaiting_client 事件"""
        dag = DAGDefinition(steps=[
            DAGStep(
                step_id="s1", capability="cli", action="install python",
                execution_location=ExecutionLocation.CLIENT,
            ),
        ])
        engine = DAGExecutionEngine(dag)
        events = []
        async for event in engine.execute():
            events.append(event)

        # 应该包含 awaiting_client 事件
        event_types = [e.event for e in events]
        assert StreamEventType.STEP_AWAITING_CLIENT.value in event_types

    @pytest.mark.asyncio
    async def test_event_structure(self):
        """事件应包含正确的结构"""
        dag = DAGDefinition(steps=[
            DAGStep(
                step_id="s1", capability="cli", action="run test",
                execution_location=ExecutionLocation.CLIENT,
            ),
        ])
        engine = DAGExecutionEngine(dag)
        event = None
        async for e in engine.execute():
            event = e
            break

        assert event is not None
        assert hasattr(event, "event")
        assert hasattr(event, "data")
        assert hasattr(event, "timestamp")
        assert isinstance(event.data, dict)


class TestMatchMcpServer:
    """MCP server 前缀匹配 — LLM 可能把 capability 写成 mcp_{server} 或 mcp_{server}_{tool}"""

    def _make_engine(self):
        return DAGExecutionEngine(
            DAGDefinition(steps=[]),
            context={
                "mcp_servers": [
                    {
                        "server_name": "amap",
                        "transport_type": "streamable_http",
                        "mcp_url": "http://amap/mcp",
                        "headers": {},
                    },
                    {
                        "server_name": "github",
                        "transport_type": "streamable_http",
                        "mcp_url": "http://github/mcp",
                        "headers": {},
                    },
                ],
            },
        )

    def test_exact_server_name(self):
        engine = self._make_engine()
        srv = engine._match_mcp_server("mcp_amap")
        assert srv["server_name"] == "amap"

    def test_tool_suffix_matches_server(self):
        """回归：mcp_amap_maps_weather 应归到 amap，而不是匹配失败导致 MCP URL 未提供"""
        engine = self._make_engine()
        srv = engine._match_mcp_server("mcp_amap_maps_weather")
        assert srv is not None
        assert srv["server_name"] == "amap"
        assert srv["mcp_url"] == "http://amap/mcp"

    def test_other_server_tool_suffix(self):
        engine = self._make_engine()
        srv = engine._match_mcp_server("mcp_github_issue")
        assert srv["server_name"] == "github"

    def test_unmatched_capability(self):
        engine = self._make_engine()
        assert engine._match_mcp_server("mcp_unknown_server") is None
        assert engine._match_mcp_server("web_search") is None


class TestCapabilityNormalization:
    """DAG 能力名归一化 — LLM 臆造的能力名应归一到真实标识符"""

    def _make_inventory(self):
        from app.agent.models import (
            CapabilityInfo,
            CapabilityType,
            ExecutionLocation,
        )

        return CapabilityInventory(capabilities=[
            CapabilityInfo(
                type=CapabilityType.MCP,
                name="mcp_amap",
                description="MCP [amap](streamable_http)",
                execution_location=ExecutionLocation.SERVER,
                tools=[{"name": "maps_weather", "description": "天气"}],
            ),
            CapabilityInfo(
                type=CapabilityType.WEB_SEARCH,
                name="web_search",
                description="联网搜索",
                execution_location=ExecutionLocation.SERVER,
            ),
        ])

    def _normalized(self, guess):
        from app.agent.models import CapabilityInventory

        from app.agent.dag.validator import DAGValidator

        inventory = self._make_inventory()
        dag = DAGDefinition(steps=[DAGStep(step_id="s1", capability=guess, action="x")])
        ok, _ = DAGValidator.validate(dag, inventory)
        return ok, dag.steps[0].capability

    def test_reversed_name_amap_mcp(self):
        """回归：LLM 输出 amap_mcp 应归一到 mcp_amap 且 DAG 通过验证"""
        ok, cap = self._normalized("amap_mcp")
        assert ok
        assert cap == "mcp_amap"

    def test_tool_suffix_mcp_amap_maps_weather(self):
        """回归：mcp_amap_maps_weather 应归一到 mcp_amap"""
        ok, cap = self._normalized("mcp_amap_maps_weather")
        assert ok
        assert cap == "mcp_amap"

    def test_exact_names_unchanged(self):
        ok, cap = self._normalized("web_search")
        assert ok
        assert cap == "web_search"

    def test_unknown_capability_still_fails(self):
        from app.agent.models import CapabilityInventory

        from app.agent.dag.validator import DAGValidator

        inventory = self._make_inventory()
        dag = DAGDefinition(steps=[DAGStep(step_id="s1", capability="totally_unknown", action="x")])
        ok, errors = DAGValidator.validate(dag, inventory)
        assert not ok
        assert any("不在当前能力清单" in e for e in errors)
