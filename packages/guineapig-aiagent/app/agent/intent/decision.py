"""
Phase 3: 置信度综合判定 — 结合 Phase 0 + 1 + 2 结果，输出最终决策。

决策逻辑：
┌─────────────────────────────────────────────────────────┐
│ Phase 0 结果 → trivial? → fallback_to_chat              │
│ Phase 0 结果 → simple? → Phase 1 → 置信度≥0.7? → proceed │
│                          Phase 1 → 置信度<0.7? → analyze, then decide  │
│ Phase 0 结果 → complex? → skip Phase 1 → Phase 2 analyze │
│    → 置信度≥0.7 + feasible → proceed                    │
│    → 置信度≥0.7 + !feasible → reject                    │
│    → 置信度<0.4 → fallback                              │
│    → 0.4≤置信度<0.7 → clarify                           │
└─────────────────────────────────────────────────────────┘
"""

from ..models import (
    DeepAnalysisResult,
    IntentDecisionResult,
    QuickFilterResult,
    ScanResult,
)

# ── 置信度阈值 ──
CONFIDENCE_HIGH = 0.7  # ≥0.7: 足够自信，直接 proceed / reject
CONFIDENCE_MEDIUM = 0.4  # 0.4~0.7: 需要澄清
# <0.4: 置信度过低，fallback 到普通对话


class IntentDecision:
    """Phase 3 综合判定器"""

    @classmethod
    def decide(
        cls,
        quick_result: QuickFilterResult,
        candidates: list[ScanResult],
        deep_analysis: DeepAnalysisResult | None = None,
    ) -> IntentDecisionResult:
        """
        综合 Phase 0 + 1 + 2 结果，输出最终决策。

        Args:
            quick_result: Phase 0 快速筛选结果
            candidates: Phase 1 关键词扫描候选意图列表
            deep_analysis: Phase 2 LLM 深度分析结果（可选）

        Returns:
            IntentDecisionResult 最终决策
        """
        # ── Case 1: Trivial — 直接放行 ──
        if quick_result == QuickFilterResult.TRIVIAL:
            return IntentDecisionResult(
                action="fallback",
                primary_intent=None,
                candidates=candidates,
                confidence=1.0,
                reason="问候或简单应答，走普通对话",
            )

        # ── Case 2: Complex — 必须有 deep_analysis ──
        if quick_result == QuickFilterResult.COMPLEX:
            return cls._decide_with_deep_analysis(deep_analysis, candidates)

        # ── Case 3: Simple — 检查 Phase 1 结果 ──
        if quick_result == QuickFilterResult.SIMPLE:
            return cls._decide_simple(candidates, deep_analysis)

        # ── 兜底 ──
        return IntentDecisionResult(
            action="fallback",
            primary_intent=deep_analysis,
            candidates=candidates,
            confidence=0.0,
            reason="无法确定意图分类",
        )

    @classmethod
    def _decide_simple(
        cls,
        candidates: list[ScanResult],
        deep_analysis: DeepAnalysisResult | None = None,
    ) -> IntentDecisionResult:
        """处理 Phase 0 = simple 的情况"""
        if not candidates:
            # Phase 1 无匹配 → 如有 deep_analysis 则用它判断
            if deep_analysis:
                return cls._decide_with_deep_analysis(deep_analysis, candidates)
            return IntentDecisionResult(
                action="fallback",
                candidates=candidates,
                confidence=0.0,
                reason="无关键词匹配且无深度分析，走普通对话",
            )

        # Phase 1 有匹配 → 取最高置信度
        top = candidates[0]

        # Phase 1 关键词匹配是强信号，置信度 >= 0.5 即可 proceed
        # 关键词扫描是精确匹配而非 LLM 推测，可靠性更高
        if top.confidence >= 0.5:
            return IntentDecisionResult(
                action="proceed",
                primary_intent=deep_analysis,
                candidates=candidates,
                confidence=top.confidence,
                reason=f"关键词匹配 '{top.matched_keyword}' → {top.intent_type} (置信度 {top.confidence})",
            )

        # 置信度很低（< 0.5）→ 如果有 deep_analysis 则用它细化
        if deep_analysis and deep_analysis.confidence > top.confidence:
            return cls._decide_with_deep_analysis(deep_analysis, candidates)

        return IntentDecisionResult(
            action="clarify",
            primary_intent=deep_analysis,
            candidates=candidates,
            confidence=top.confidence,
            reason=f"置信度不足 ({top.confidence})，需要用户澄清",
        )

    @classmethod
    def _decide_with_deep_analysis(
        cls,
        deep_analysis: DeepAnalysisResult | None,
        candidates: list[ScanResult],
    ) -> IntentDecisionResult:
        """基于 LLM 深度分析结果做决策"""
        if deep_analysis is None:
            return IntentDecisionResult(
                action="fallback",
                candidates=candidates,
                confidence=0.0,
                reason="需要 LLM 深度分析但结果为空",
            )

        conf = deep_analysis.confidence

        if conf >= CONFIDENCE_HIGH:
            if deep_analysis.feasible:
                return IntentDecisionResult(
                    action="proceed",
                    primary_intent=deep_analysis,
                    candidates=candidates,
                    confidence=conf,
                    reason=(
                        f"LLM 分析: {deep_analysis.intent_type} "
                        f"(置信度 {conf}, {deep_analysis.complexity})"
                    ),
                )
            else:
                return IntentDecisionResult(
                    action="reject",
                    primary_intent=deep_analysis,
                    candidates=candidates,
                    confidence=conf,
                    reason=f"任务不可行: {deep_analysis.infeasible_reason}",
                )

        if conf < CONFIDENCE_MEDIUM:
            return IntentDecisionResult(
                action="fallback",
                primary_intent=deep_analysis,
                candidates=candidates,
                confidence=conf,
                reason=f"LLM 置信度过低 ({conf})，走普通对话",
            )

        # 中等置信度
        return IntentDecisionResult(
            action="clarify",
            primary_intent=deep_analysis,
            candidates=candidates,
            confidence=conf,
            reason=f"LLM 置信度中等 ({conf})，需要用户澄清",
        )
