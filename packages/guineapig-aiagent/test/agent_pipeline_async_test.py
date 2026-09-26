"""
Agent 意图管线简化回归测试 — 验证新的两段式流程。

新流程：
- Phase 0: QuickFilter 规则筛选 → 仅区分 trivial（简单对话）/ 非 trivial
- Phase 1: 一次 LLM 深度分析（DeepAnalyzer）→ 判断是否可行、是否需要 DAG
- Phase 2: feasible 且意图需要执行 → DAGGenerator 生成 DAG；否则直接对话

覆盖点：
- 同步 LLM 调用（DeepAnalyzer.analyze / DAGGenerator.generate）经 asyncio.to_thread 执行
- 关键词命中的消息也必须走 LLM 分析并生成 DAG（回归：修复「proceed 但 DAG 为空」）
- 不可行 / 纯聊天意图 → 不生成 DAG，走直接对话
"""

import pytest

from app.agent.models import (
    DAGDefinition,
    DAGStep,
    DeepAnalysisResult,
    ExecutionLocation,
)
from app.routers.agent import AgentChatRequest, _run_intent_pipeline


@pytest.mark.asyncio
async def test_run_intent_pipeline_offloads_llm_to_thread(mocker):
    """非 trivial 消息应触发 DeepAnalyzer + DAGGenerator（均经 to_thread），并返回其结果"""
    request = AgentChatRequest(message="先搜索一下天气，再总结成报告保存")

    deep_analysis = DeepAnalysisResult(
        intent_type="multi_step_complex",
        intent_summary="搜索天气并总结保存",
        confidence=0.9,
        feasible=True,
        complexity="multi_step",
    )
    dag = DAGDefinition(
        steps=[
            DAGStep(
                step_id="s1",
                capability="web_search",
                action="search",
                execution_location=ExecutionLocation.SERVER,
            ),
            DAGStep(
                step_id="s2",
                capability="llm_chat",
                action="summarize",
                depends_on=["s1"],
            ),
        ],
        original_intent="搜索天气并总结保存",
    )

    mock_analyze = mocker.patch(
        "app.routers.agent.DeepAnalyzer.analyze", return_value=deep_analysis
    )
    mock_generate = mocker.patch(
        "app.routers.agent.DAGGenerator.generate", return_value=dag
    )

    result = await _run_intent_pipeline(request)

    # 两个同步 LLM 调用都应被触发并返回结果
    assert result["deep_analysis"] is deep_analysis
    assert result["dag"] is dag
    mock_analyze.assert_called_once()
    mock_generate.assert_called_once()

    # 决策应衔接深层分析结果（proceed 且 DAG 可执行）
    assert result["action"] == "proceed"
    assert len(result["dag"].steps) == 2


@pytest.mark.asyncio
async def test_run_intent_pipeline_trivial_skips_llm(mocker):
    """TRIVIAL 消息不应触发任何 LLM 调用（提前返回）"""
    request = AgentChatRequest(message="你好")

    mock_analyze = mocker.patch("app.routers.agent.DeepAnalyzer.analyze")
    mock_generate = mocker.patch("app.routers.agent.DAGGenerator.generate")

    result = await _run_intent_pipeline(request)

    mock_analyze.assert_not_called()
    mock_generate.assert_not_called()
    assert result["action"] == "fallback_to_chat"
    assert result["deep_analysis"] is None
    assert result["dag"] is None


@pytest.mark.asyncio
async def test_keyword_message_runs_deep_analysis_and_generates_dag(mocker):
    """关键词命中的消息（如『帮我搜索今天星期几』）也必须走 LLM 分析并生成 DAG。

    回归：旧逻辑在关键词置信度 >= 0.5 时短路 LLM 分析，导致 proceed 但 DAG 为空。
    """
    request = AgentChatRequest(message="帮我搜索今天星期几")

    deep_analysis = DeepAnalysisResult(
        intent_type="web_search",
        intent_summary="搜索今天星期几",
        confidence=0.9,
        feasible=True,
        complexity="single_step",
    )
    dag = DAGDefinition(
        steps=[
            DAGStep(
                step_id="s1",
                capability="web_search",
                action="search",
                execution_location=ExecutionLocation.SERVER,
            )
        ],
        original_intent="搜索今天星期几",
    )

    mock_analyze = mocker.patch(
        "app.routers.agent.DeepAnalyzer.analyze", return_value=deep_analysis
    )
    mock_generate = mocker.patch(
        "app.routers.agent.DAGGenerator.generate", return_value=dag
    )

    result = await _run_intent_pipeline(request)

    # 关键词命中不再短路 LLM 分析
    mock_analyze.assert_called_once()
    assert result["deep_analysis"] is deep_analysis
    # 意图可行 → 生成 DAG 并 proceed
    mock_generate.assert_called_once()
    assert result["action"] == "proceed"
    assert result["dag"] is dag
    assert len(result["dag"].steps) == 1


@pytest.mark.asyncio
async def test_infeasible_message_routes_to_chat(mocker):
    """LLM 判定不可行 → 不生成 DAG，走直接对话"""
    request = AgentChatRequest(message="帮我搜索今天星期几")

    deep_analysis = DeepAnalysisResult(
        intent_type="web_search",
        intent_summary="搜索今天星期几",
        confidence=0.8,
        feasible=False,
        infeasible_reason="当前无可用搜索能力",
    )

    mock_analyze = mocker.patch(
        "app.routers.agent.DeepAnalyzer.analyze", return_value=deep_analysis
    )
    mock_generate = mocker.patch("app.routers.agent.DAGGenerator.generate")

    result = await _run_intent_pipeline(request)

    mock_analyze.assert_called_once()
    mock_generate.assert_not_called()
    assert result["action"] == "fallback_to_chat"
    assert result["dag"] is None


@pytest.mark.asyncio
async def test_chat_intent_message_routes_to_chat(mocker):
    """意图识别为 general_chat → 不需要 DAG，走直接对话"""
    request = AgentChatRequest(message="帮我看看这句话怎么理解")

    deep_analysis = DeepAnalysisResult(
        intent_type="general_chat",
        intent_summary="普通对话",
        confidence=0.9,
        feasible=True,
        complexity="single_step",
    )

    mock_analyze = mocker.patch(
        "app.routers.agent.DeepAnalyzer.analyze", return_value=deep_analysis
    )
    mock_generate = mocker.patch("app.routers.agent.DAGGenerator.generate")

    result = await _run_intent_pipeline(request)

    mock_analyze.assert_called_once()
    mock_generate.assert_not_called()
    assert result["action"] == "fallback_to_chat"
    assert result["dag"] is None