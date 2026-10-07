"""DAG 自纠错 Replanner — 根据失败信息生成并校验修正步骤（仅 server 端）。"""

from __future__ import annotations

from app.core.log import logger
from app.core.llm_clients import call_with_retry
from app.agent.models import (
    CapabilityInventory,
    DAGDefinition,
    DAGStep,
    ExecutionLocation,
)

from .errors import StepFailure


class Replanner:
    """把一次终态失败回喂给 LLM，产出一份受约束的修正计划。"""

    @classmethod
    def _call_llm(cls, system: str, human: str, trace_id: str | None = None) -> str:
        from app.agent.dag.generator import DAGGenerator

        client, model_name = DAGGenerator._get_llm_client()
        completion = call_with_retry(
            client.chat.completions.create,
            model=model_name,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": human},
            ],
            temperature=0.1,
            max_tokens=2048,
            response_format={"type": "json_object"},
        )
        return completion.choices[0].message.content or ""

    @classmethod
    def replan(
        cls,
        *,
        original_intent: str,
        capability_inventory: CapabilityInventory | None,
        capabilities_formatted: str,
        step_results: dict,
        failed: StepFailure,
        trace_id: str | None = None,
    ) -> list[DAGStep]:
        from app.agent.dag.generator import DAGGenerator
        from app.agent.dag.validator import DAGValidator
        from app.agent.intent.prompts import REPLAN_SYSTEM, REPLAN_HUMAN_TEMPLATE

        executed_summary = (
            "\n".join(f"- {sid}: {str(res)[:300]}" for sid, res in step_results.items())
            or "(无)"
        )
        human = REPLAN_HUMAN_TEMPLATE.format(
            capabilities=capabilities_formatted or "(无)",
            original_intent=original_intent or "",
            executed_summary=executed_summary,
            failed_step_id=failed.step_id,
            failed_capability=failed.capability,
            failed_action=failed.action,
            error=failed.error,
            suggestion=failed.suggestion or "(无)",
        )

        logger.warning(
            f"[Replanner] 触发自纠错: failed={failed.step_id}/{failed.capability}, "
            f"error={failed.error[:120]}"
        )
        try:
            raw = cls._call_llm(REPLAN_SYSTEM, human, trace_id=trace_id)
        except Exception as e:
            logger.opt(exception=e).error(f"[Replanner] re-plan LLM 调用失败，放弃自纠错: {e}")
            return []

        steps = DAGGenerator._parse_steps(raw)
        server_steps = [
            s for s in steps if s.execution_location == ExecutionLocation.SERVER
        ]
        if len(server_steps) != len(steps):
            logger.warning(
                f"[Replanner] 过滤 {len(steps) - len(server_steps)} 个 client 端修正步骤"
            )
        if not server_steps:
            logger.warning("[Replanner] 修正计划为空，放弃自纠错")
            return []

        dag = DAGDefinition(
            steps=server_steps,
            original_intent=original_intent,
            estimated_total_steps=len(server_steps),
        )
        valid, errors = DAGValidator.validate(dag, capability_inventory)
        if not valid:
            logger.warning(f"[Replanner] 修正计划验证失败: {errors}")
            return []

        logger.info(
            f"[Replanner] 修正计划通过: {len(server_steps)} 步: "
            f"{[f'{s.step_id}:{s.capability}' for s in server_steps]}"
        )
        return server_steps
