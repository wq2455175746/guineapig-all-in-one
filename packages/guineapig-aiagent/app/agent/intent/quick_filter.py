"""
Phase 0: 快速筛选 — 纯规则，零 LLM 成本。

只做一件事：判断用户消息是否是「简单对话」（问候/应答/身份询问等）。
- 是 → TRIVIAL，直接走普通 LLM 对话
- 否 → TASK，需要走一次 LLM 意图识别来决定是否生成 DAG
"""

import re

from ..models import QuickFilterResult


class QuickFilter:
    """Phase 0 快速筛选器"""

    # ── 明显不需要分析的简单对话 ──
    TRIVIAL_PATTERNS = [
        # 纯问候
        r"^(你好|您好|嗨|hi|hello|hey|早[上啊]?|晚上好|下午好|晚安)$",
        # 简单肯定/否定
        r"^(是[的嘛]?|对[的嘛]?|好[的吧]?|可以|行|ok|嗯|哦|好的|知道了|明白)$",
        r"^(不[是不是]?|[没别]有|算了|不用[了]?)$",
        # 简单致谢/告别
        r"^(谢谢|感谢|多谢|再见|拜拜|下次见)$",
        # 你是谁/你会什么 等身份询问
        r"^你(是|叫|会|能).{0,20}[吗嘛?？]?$",
        r"^你(好|叫什么名字|是谁)$",
        # 简单追问
        r"^(然后[呢呢]?|继续|还有[呢吗]?|然后呢)$",
    ]

    @classmethod
    def classify(
        cls, message: str, conversation_history: list | None = None
    ) -> QuickFilterResult:
        """
        快速分类用户消息。

        Args:
            message: 用户最新消息
            conversation_history: 可选对话历史（当前未使用，保留签名兼容）

        Returns:
            QuickFilterResult: trivial（简单对话） | task（需要分析）
        """
        text = message.strip()

        # 1. 检查是否简单对话
        for pattern in cls.TRIVIAL_PATTERNS:
            if re.match(pattern, text, re.IGNORECASE):
                return QuickFilterResult.TRIVIAL

        # 2. 纯符号或超短消息 → 视为简单对话
        if len(text) <= 1 or all(c in ".,!?。，！？" for c in text):
            return QuickFilterResult.TRIVIAL

        # 3. 其余全部视为需要 LLM 意图识别的任务
        return QuickFilterResult.TASK