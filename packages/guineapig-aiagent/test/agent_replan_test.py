"""DAG 自纠错 re-plan 单元测试。"""

import json

import pytest

from app.agent.executor.errors import StepFailure
from app.agent.executor.replanner import Replanner
from app.agent.models import (
    CapabilityInfo,
    CapabilityInventory,
    CapabilityType,
    DAGStep,
    ExecutionLocation,
)


def _inventory():
    return CapabilityInventory(
        capabilities=[
            CapabilityInfo(
                type=CapabilityType.LLM_CHAT,
                name="llm_chat",
                description="LLM",
                execution_location=ExecutionLocation.SERVER,
            ),
        ]
    )


def test_replan_returns_validated_server_steps(mocker):
    raw = json.dumps(
        [
            {
                "step_id": "r1",
                "capability": "llm_chat",
                "action": "用已有信息直接回答",
                "params": {"prompt": "回答用户"},
                "execution_location": "server",
            }
        ]
    )
    mocker.patch.object(Replanner, "_call_llm", return_value=raw)
    steps = Replanner.replan(
        original_intent="查天气",
        capability_inventory=_inventory(),
        capabilities_formatted="`llm_chat`",
        step_results={"s1": {"error": "超时"}},
        failed=StepFailure("s1", "web_search", "search", "超时", "timeout", "重试"),
    )
    assert [s.step_id for s in steps] == ["r1"]


def test_replan_filters_client_steps(mocker):
    raw = json.dumps(
        [
            {"step_id": "c1", "capability": "cli", "action": "x", "execution_location": "client"},
            {"step_id": "r1", "capability": "llm_chat", "action": "y", "execution_location": "server", "params": {"prompt": "p"}},
        ]
    )
    mocker.patch.object(Replanner, "_call_llm", return_value=raw)
    steps = Replanner.replan(
        original_intent="t",
        capability_inventory=_inventory(),
        capabilities_formatted="",
        step_results={},
        failed=StepFailure("s1", "cli", "x", "err"),
    )
    assert [s.step_id for s in steps] == ["r1"]


def test_replan_returns_empty_on_llm_failure(mocker):
    mocker.patch.object(Replanner, "_call_llm", side_effect=RuntimeError("no llm"))
    steps = Replanner.replan(
        original_intent="t",
        capability_inventory=_inventory(),
        capabilities_formatted="",
        step_results={},
        failed=StepFailure("s1", "web_search", "x", "err"),
    )
    assert steps == []


def test_replan_returns_empty_on_invalid_plan(mocker):
    raw = json.dumps([{"step_id": "r1", "capability": "nope", "action": "x", "execution_location": "server"}])
    mocker.patch.object(Replanner, "_call_llm", return_value=raw)
    steps = Replanner.replan(
        original_intent="t",
        capability_inventory=_inventory(),
        capabilities_formatted="",
        step_results={},
        failed=StepFailure("s1", "web_search", "x", "err"),
    )
    assert steps == []


def test_replan_event_types_exist():
    from app.agent.models import StreamEventType

    assert StreamEventType.REPLAN_STARTED.value == "replan_started"
    assert StreamEventType.REPLAN_GENERATED.value == "replan_generated"
    assert StreamEventType.REPLAN_FAILED.value == "replan_failed"


def test_replan_settings_defaults():
    from app.config import settings

    assert settings.AGENT_REPLAN_ENABLED is False
    assert settings.AGENT_REPLAN_MAX == 1


from app.agent.executor.engine import DAGExecutionEngine
from app.agent.executor import handlers as handlers_mod
from app.agent.executor.replanner import Replanner
from app.agent.executor import engine as engine_mod
from app.agent.models import DAGDefinition, DAGStep, StreamEventType
from app.config import settings


@pytest.mark.asyncio
async def test_engine_replans_after_failure(mocker):
    async def fake_execute(capability, params):
        if capability == "web_search":
            return {"error": "超时", "error_type": "timeout", "error_suggestion": "重试", "result": ""}
        return {"result": "修正后的答案", "char_count": 6}

    mocker.patch.object(handlers_mod.CapabilityHandlers, "execute", side_effect=fake_execute)
    mocker.patch.object(
        engine_mod.Replanner,
        "replan",
        return_value=[DAGStep(step_id="r1", capability="llm_chat", action="answer", params={"prompt": "p"})],
    )
    mocker.patch.object(settings, "AGENT_REPLAN_ENABLED", True)
    mocker.patch.object(settings, "AGENT_REPLAN_MAX", 1)

    dag = DAGDefinition(
        steps=[DAGStep(step_id="s1", capability="web_search", action="search", max_retries=0)],
        original_intent="查一下",
    )
    engine = DAGExecutionEngine(dag, context={"session_id": "conv_1", "capabilities_formatted": "`llm_chat`"})
    events = [e async for e in engine.execute(session_id="conv_1")]
    types = [e.event for e in events]

    assert StreamEventType.REPLAN_STARTED.value in types
    assert StreamEventType.REPLAN_GENERATED.value in types
    assert StreamEventType.STEP_COMPLETED.value in types
    complete = [e for e in events if e.event == StreamEventType.EXECUTION_COMPLETE.value][-1]
    assert complete.data["status"] == "completed"
    assert complete.data["replanned"] is True
    assert "r1" in engine.step_results


@pytest.mark.asyncio
async def test_engine_no_replan_without_session(mocker):
    async def fake_execute(capability, params):
        return {"error": "超时", "error_type": "timeout", "result": ""}

    mocker.patch.object(handlers_mod.CapabilityHandlers, "execute", side_effect=fake_execute)
    replan = mocker.patch.object(engine_mod.Replanner, "replan")
    mocker.patch.object(settings, "AGENT_REPLAN_ENABLED", True)

    dag = DAGDefinition(
        steps=[DAGStep(step_id="s1", capability="web_search", action="x", max_retries=0)],
        original_intent="t",
    )
    engine = DAGExecutionEngine(dag)
    _ = [e async for e in engine.execute()]
    replan.assert_not_called()
