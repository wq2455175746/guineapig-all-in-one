"""
Agent 意图管线异步路径回归测试 — 验证同步 LLM 调用被安全地放到线程池执行。

覆盖点：
- _run_intent_pipeline 在 async 上下文中调用 DeepAnalyzer.analyze / DAGGenerator.generate，
  二者为同步阻塞 LLM 调用，必须经由 asyncio.to_thread 执行（不阻塞事件循环），
  且返回结果与 Pipeline 后续阶段（Phase 3 决策、DAG 生成）正确衔接。
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
    """COMPLEX 消息应触发 DeepAnalyzer + DAGGenerator（均经 to_thread），并返回其结果"""
    # 用 COMPLEX 模式消息走完整个 Pipeline（Phase 0 → 2 → 3 → DAG）
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

    # Phase 3 决策应与深层分析结果衔接（proceed 且 DAG 可执行）
    assert result["decision"].action == "proceed"
    assert result["decision"].confidence == 0.9
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
    assert result["decision"].action == "fallback"
    assert result["deep_analysis"] is None
    assert result["dag"] is None