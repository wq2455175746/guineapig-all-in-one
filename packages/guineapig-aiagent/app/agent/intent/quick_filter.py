"""
Phase 0: 快速筛选 — 纯规则，零 LLM 成本。

将用户消息分为三类:
- TRIVIAL: 问候/简单应答 → 直接放行到普通对话
- SIMPLE: 可能是单个能力 → 进入 Phase 1 关键词扫描
- COMPLEX: 明显多步协作 → 跳转 Phase 2 LLM 深度分析
"""

import re

from ..models import QuickFilterResult


class QuickFilter:
    """Phase 0 快速筛选器"""

    # ── 明显不需要拆解的问候/应答 ──
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

    # ── 明显需要多步拆解的复合信号 ──
    COMPLEX_PATTERNS = [
        # 顺序词 + 操作 → 多步
        r"(先|然后|再|接着|下一步|之后).*(搜索|查找|打开|运行|创建|保存|删除|总结|分析|写入)",
        # 多个操作组合（跨能力）
        r"(搜索|查找|读取|打开).{2,}(总结|归纳|分析|保存|写入|创建|发送)",
        # 涉及多种能力的关键词
        r"(搜索|查找).*(保存|写入|导出|发送)",
        r"(读取|打开).*(发送|通知|分享|上传)",
        # 明确的多步骤描述
        r"第[一二三四五六七八九十步]",
        r"步骤[1234567890]",
    ]

    # ── 简单的单能力信号（不一定是 complex） ──
    SIMPLE_INTENT_PATTERNS = [
        # 搜索类
        r"(搜索|查找|查一下|搜一[下个]|百度|google)",
        # 知识库
        r"(知识库|文档|资料|手册)",
        # 文件操作
        r"(打开文件|读取文件|保存|写入|创建文件|删除文件|列出目录|当前目录)",
        # 命令行
        r"(运行|执行|安装|启动|停止)",
        # Skill
        r"(skill|技能)",
        # 记忆
        r"(我记得|之前|上次|以前)",
        # 总结
        r"(总结|归纳|汇总)",
    ]

    @classmethod
    def classify(cls, message: str, conversation_history: list | None = None) -> QuickFilterResult:
        """
        快速分类用户消息。

        Args:
            message: 用户最新消息
            conversation_history: 可选对话历史

        Returns:
            QuickFilterResult: trivial | simple | complex
        """
        text = message.strip()

        # 1. 检查是否 trivial
        for pattern in cls.TRIVIAL_PATTERNS:
            if re.match(pattern, text, re.IGNORECASE):
                return QuickFilterResult.TRIVIAL

        # 2. 检查是否 complex（多步复合信号）
        for pattern in cls.COMPLEX_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return QuickFilterResult.COMPLEX

        # 3. 检查是否至少有一个简单意图信号
        #    没有信号 → 按 simple 处理（让 Phase 1 决定）
        #    但如果是纯符号或超短消息 → 标记为 trivial
        if len(text) <= 1 or all(c in ".,!?。，！？" for c in text):
            return QuickFilterResult.TRIVIAL

        return QuickFilterResult.SIMPLE
