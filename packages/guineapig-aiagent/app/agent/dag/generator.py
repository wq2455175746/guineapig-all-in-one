"""
DAG 生成器 — 根据 LLM 意图分析结果 + 能力清单，生成可执行的 DAG。

通过一次非流式 LLM 调用生成步骤计划，然后由 validator 验证。
集成 Langfuse 可观测性：自动追踪 DAG 生成 LLM 调用。
"""

import json

from openai import OpenAI

from app.config import settings
from app.core.log import logger
from app.services.langfuse_client import get_langfuse, is_langfuse_enabled

from ..models import (
    CapabilityInventory,
    DAGDefinition,
    DAGStep,
    DeepAnalysisResult,
    ExecutionLocation,
)
from ..intent.prompts import DAG_GENERATOR_SYSTEM, DAG_GENERATOR_HUMAN_TEMPLATE
from .validator import DAGValidator


class DAGGenerator:
    """DAG 生成器 — 将意图转化为可执行步骤计划"""

    # 无法生成 DAG 的意图类型（直接走 LLM 对话即可）
    NON_DAG_INTENTS = {"general_chat", "llm_analysis"}

    @classmethod
    def _get_llm_client(cls) -> tuple[OpenAI, str]:
        """获取 LLM 客户端"""
        if not settings.LLM_API_KEY:
            raise ValueError("LLM_API_KEY not set in .env — 无法生成 DAG")
        client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            timeout=120.0,
        )
        return client, settings.LLM_MODEL_NAME

    @classmethod
    def generate(
        cls,
        deep_analysis: DeepAnalysisResult,
        capability_inventory: CapabilityInventory | None = None,
        capabilities_formatted: str = "",
        trace_id: str | None = None,
    ) -> DAGDefinition:
        """
        根据意图分析结果生成 DAG。

        Args:
            deep_analysis: Phase 2 深度意图分析结果
            capability_inventory: 当前能力清单（可选，用于格式化）
            capabilities_formatted: 已格式化的能力文本（优先使用）

        Returns:
            DAGDefinition 可执行的步骤计划
        """
        # ── 前置检查: 不需要 DAG 的意图类型 ──
        if deep_analysis.intent_type in cls.NON_DAG_INTENTS:
            return DAGDefinition(
                steps=[],
                original_intent=deep_analysis.intent_summary,
                estimated_total_steps=0,
            )

        # ── 不可行的任务不生成 DAG ──
        if not deep_analysis.feasible:
            return DAGDefinition(
                steps=[],
                original_intent=deep_analysis.intent_summary,
                estimated_total_steps=0,
            )

        try:
            client, model_name = cls._get_llm_client()

            # 格式化能力清单
            if not capabilities_formatted and capability_inventory:
                from ..capability_registry import CapabilityRegistry

                capabilities_formatted = CapabilityRegistry.format_for_llm(
                    capability_inventory
                )
            if not capabilities_formatted:
                capabilities_formatted = "(当前无可用能力)"

            # 格式化意图分析
            intent_analysis = json.dumps(
                deep_analysis.model_dump(), ensure_ascii=False, indent=2
            )

            human_message = DAG_GENERATOR_HUMAN_TEMPLATE.format(
                capabilities=capabilities_formatted,
                intent_analysis=intent_analysis,
            )

            logger.info(
                f"[DAGGenerator] 请求 LLM 生成 DAG: model={model_name}, "
                f"intent={deep_analysis.intent_type}, "
                f"human_message={human_message}"
            )

            # ── Langfuse Generation Span (SDK v4) ──
            langfuse_gen = None
            if is_langfuse_enabled():
                langfuse = get_langfuse()
                langfuse_gen = langfuse.start_observation(
                    name="dag-generator-llm",
                    as_type="generation",
                    trace_context={"trace_id": trace_id} if trace_id else None,
                    model=model_name,
                    input={
                        "system": DAG_GENERATOR_SYSTEM[:200],
                        "user": human_message[:500],
                    },
                    metadata={
                        "intent_type": deep_analysis.intent_type,
                        "intent_phase": "dag_generation",
                    },
                )

            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": DAG_GENERATOR_SYSTEM},
                    {"role": "user", "content": human_message},
                ],
                temperature=0.1,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )

            raw = completion.choices[0].message.content

            # ── 结束 Langfuse Generation Span (SDK v4) ──
            if langfuse_gen:
                usage = completion.usage
                update_kwargs = {"output": raw}
                if usage:
                    update_kwargs["usage_details"] = {
                        "input": usage.prompt_tokens,
                        "output": usage.completion_tokens,
                    }
                langfuse_gen.update(**update_kwargs)
                langfuse_gen.end()

            logger.info(f"[DAGGenerator] LLM 原始回复: {raw[:1000]}...")

            steps = cls._parse_steps(raw)

            dag = DAGDefinition(
                steps=steps,
                original_intent=deep_analysis.intent_summary,
                estimated_total_steps=len(steps),
            )

            # ── 验证 DAG ──
            valid, errors = DAGValidator.validate(dag, capability_inventory)
            if not valid:
                logger.warning(f"[DAGGenerator] DAG 验证失败: {errors}; " f"返回空 DAG")
                return DAGDefinition(
                    steps=[],
                    original_intent=deep_analysis.intent_summary,
                    estimated_total_steps=0,
                )

            logger.info(f"[DAGGenerator] DAG 生成成功: {len(steps)} 个步骤")
            return dag

        except Exception as e:
            logger.error(f"[DAGGenerator] DAG 生成失败: {e}")
            return DAGDefinition(
                steps=[],
                original_intent=deep_analysis.intent_summary,
                estimated_total_steps=0,
            )

    @classmethod
    def _parse_steps(cls, raw: str | None) -> list[DAGStep]:
        """解析 LLM JSON 响应，返回 DAGStep 列表"""
        if not raw:
            return []

        try:
            data = json.loads(raw)

            # 支持顶层是数组或包含 steps 键的对象
            if isinstance(data, dict):
                steps_data = data.get("steps", data.get("plan", []))
                if isinstance(steps_data, list):
                    data = steps_data
                elif isinstance(steps_data, dict):
                    data = [steps_data]
                else:
                    data = []

            if not isinstance(data, list):
                logger.warning(f"[DAGGenerator] LLM 响应不是数组: {type(data)}")
                return []

            steps = []
            for i, item in enumerate(data):
                if not isinstance(item, dict):
                    continue
                loc_str = str(item.get("execution_location", "server"))
                loc = (
                    ExecutionLocation.CLIENT
                    if loc_str == "client"
                    else ExecutionLocation.SERVER
                )
                step = DAGStep(
                    step_id=str(item.get("step_id", f"s{i+1}")),
                    capability=str(item.get("capability", "unknown")),
                    action=str(item.get("action", "")),
                    params=item.get("params", {}),
                    output_key=str(item.get("output_key", "")),
                    depends_on=item.get("depends_on", []),
                    execution_location=loc,
                    requires_confirmation=bool(
                        item.get("requires_confirmation", False)
                    ),
                    max_retries=int(item.get("max_retries", 2)),
                    timeout_seconds=int(item.get("timeout_seconds", 60)),
                    fallback_action=str(item.get("fallback_action") or ""),
                )
                steps.append(step)

            return steps

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"[DAGGenerator] JSON 解析失败: {e}")
            return []
