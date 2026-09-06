"""
Phase 2: LLM 深度意图分析 — 一次非流式 LLM 调用，输出结构化意图。

适用场景：
- Phase 0 判定为 complex（多步复合）
- Phase 1 无匹配或置信度不足

使用与 handle_llmservice 相同的 OpenAI 兼容客户端（settings 配置）。
集成 Langfuse 可观测性：自动追踪 LLM 调用链。
"""

import json

from openai import OpenAI

from app.config import settings
from app.core.log import logger
from app.core.llm_clients import get_llm_client
from app.services.langfuse_client import get_langfuse, is_langfuse_enabled

from ..models import DeepAnalysisResult, CapabilityInventory
from .prompts import DEEP_ANALYZER_SYSTEM, DEEP_ANALYZER_HUMAN_TEMPLATE


class DeepAnalyzer:
    """Phase 2 LLM 深度意图分析器"""

    @classmethod
    def _get_llm_client(cls) -> tuple[OpenAI, str]:
        """获取 LLM 客户端（惰性初始化，复用 settings 配置）"""
        if not settings.LLM_API_KEY:
            raise ValueError("LLM_API_KEY not set in .env — 无法进行深度意图分析")
        client = get_llm_client(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            timeout=120.0,
        )
        return client, settings.LLM_MODEL_NAME

    @classmethod
    def analyze(
        cls,
        user_message: str,
        capability_inventory: CapabilityInventory | None = None,
        conversation_history: list[dict] | None = None,
        capabilities_formatted: str = "",
        trace_id: str | None = None,
    ) -> DeepAnalysisResult:
        """
        执行一次非流式 LLM 调用，返回结构化意图分析结果。

        Args:
            user_message: 用户消息
            capability_inventory: 当前能力清单（可选，用于格式化）
            conversation_history: 对话历史（可选）
            capabilities_formatted: 已格式化的能力文本（优先使用）

        Returns:
            DeepAnalysisResult 结构化意图分析
        """
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

            # 格式化对话上下文
            context_parts = []
            if conversation_history:
                # 取最近 4 轮对话（避免 token 过长）
                recent = (
                    conversation_history[-8:]
                    if len(conversation_history) > 8
                    else conversation_history
                )
                for msg in recent:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    context_parts.append(f"[{role}]: {content}")
            conversation_context = "\n".join(context_parts) if context_parts else "(无)"
            if len(conversation_context) > 2000:
                conversation_context = conversation_context[-2000:] + "..."

            # 构建 human 消息
            human_message = DEEP_ANALYZER_HUMAN_TEMPLATE.format(
                capabilities=capabilities_formatted,
                conversation_context=conversation_context,
                user_message=user_message,
            )

            logger.info(
                f"[DeepAnalyzer] 请求 LLM 分析: model={model_name}, "
                f"msg='{user_message[:60]}...'"
            )

            # ── Langfuse Generation Span (SDK v4) ──
            langfuse_gen = None
            if is_langfuse_enabled():
                langfuse = get_langfuse()
                langfuse_gen = langfuse.start_observation(
                    name="deep-analyzer-llm",
                    as_type="generation",
                    trace_context={"trace_id": trace_id} if trace_id else None,
                    model=model_name,
                    input={
                        "system": DEEP_ANALYZER_SYSTEM[:200],
                        "user": human_message[:500],
                    },
                    metadata={"intent_phase": "phase2_deep_analyzer"},
                )

            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": DEEP_ANALYZER_SYSTEM},
                    {"role": "user", "content": human_message},
                ],
                temperature=0.1,  # 低温度确保结构化输出稳定
                max_tokens=1024,
                response_format={"type": "json_object"},
            )

            # ── 结束 Langfuse Generation Span (SDK v4) ──
            if langfuse_gen:
                usage = completion.usage
                update_kwargs = {"output": completion.choices[0].message.content}
                if usage:
                    update_kwargs["usage_details"] = {
                        "input": usage.prompt_tokens,
                        "output": usage.completion_tokens,
                    }
                langfuse_gen.update(**update_kwargs)
                langfuse_gen.end()

            raw = completion.choices[0].message.content
            logger.debug(f"[DeepAnalyzer] LLM 原始回复: {raw[:1000]}...")

            return cls._parse_response(raw)

        except Exception as e:
            logger.error(f"[DeepAnalyzer] LLM 调用失败: {e}")
            return DeepAnalysisResult(
                intent_type="general_chat",
                intent_summary=f"意图分析失败: {e}",
                confidence=0.0,
                feasible=False,
                infeasible_reason=f"LLM 分析异常: {str(e)}",
                source="llm_fallback",
            )

    @classmethod
    def _parse_response(cls, raw: str | None) -> DeepAnalysisResult:
        """解析 LLM JSON 响应，返回结构化结果"""
        if not raw:
            return DeepAnalysisResult(
                intent_type="general_chat",
                intent_summary="LLM 返回空响应",
                confidence=0.0,
                feasible=False,
                infeasible_reason="LLM 返回空响应",
                source="llm_fallback",
            )

        try:
            data = json.loads(raw)
            # 清理可能的 markdown 代码块包装
            if isinstance(data, dict) and "intent_type" in data:
                return DeepAnalysisResult(
                    intent_type=str(data.get("intent_type", "general_chat")),
                    intent_summary=str(data.get("intent_summary", "")),
                    confidence=min(max(float(data.get("confidence", 0.0)), 0.0), 1.0),
                    entities=data.get("entities", {}),
                    required_capabilities=data.get("required_capabilities", []),
                    feasible=bool(data.get("feasible", True)),
                    infeasible_reason=str(data.get("infeasible_reason", "")),
                    complexity=str(data.get("complexity", "single_step")),
                    estimated_steps=max(int(data.get("estimated_steps", 1)), 1),
                    source="llm",
                )
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"[DeepAnalyzer] JSON 解析失败: {e}, raw={raw[:100]}")

        return DeepAnalysisResult(
            intent_type="general_chat",
            intent_summary="无法解析 LLM 响应",
            confidence=0.2,
            feasible=False,
            infeasible_reason="LLM 响应格式异常",
            source="llm_fallback",
        )
