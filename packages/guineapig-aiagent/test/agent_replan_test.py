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
