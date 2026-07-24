"""
Phase 1: 关键词意图扫描 — 基于关键词映射表快速识别候选意图。

当 Phase 0 判定为 simple 时进入本阶段，通过关键词匹配返回候选意图列表。
"""

from ..models import ScanResult


class IntentScanner:
    """
    Phase 1 关键词扫描器。

    从用户消息中提取关键词，映射到候选意图类型。
    每个关键词附带基础置信度，最终结果按置信度降序排列。
    """

    # keyword → (intent_type, base_confidence)
    INTENT_KEYWORDS: list[tuple[str, str, float]] = [
        # ── 搜索类 ──
        ("搜索",   "web_search", 0.6),
        ("查一下", "web_search", 0.6),
        ("搜一下", "web_search", 0.6),
        ("查找",   "web_search", 0.5),
        ("搜搜",   "web_search", 0.5),
        ("google", "web_search", 0.7),

        # ── 知识库/RAG ──
        ("知识库", "rag_search", 0.7),
        ("文档",   "rag_search", 0.4),
        ("资料",   "rag_search", 0.4),

        # ── 文件操作 (MCP) ──
        ("打开文件", "mcp_file_operation", 0.7),
        ("读取",    "mcp_file_operation", 0.5),
        ("保存",    "mcp_file_operation", 0.6),
        ("写入",    "mcp_file_operation", 0.6),
        ("创建文件", "mcp_file_operation", 0.6),
        ("删除文件", "mcp_file_operation", 0.6),
        ("列出目录", "mcp_file_operation", 0.6),
        ("复制文件", "mcp_file_operation", 0.5),
        ("移动文件", "mcp_file_operation", 0.5),

        # ── 命令行 ──
        ("运行",  "cli_execute", 0.5),
        ("执行",  "cli_execute", 0.6),
        ("安装",  "cli_execute", 0.7),
        ("卸载",  "cli_execute", 0.7),
        ("启动",  "cli_execute", 0.5),
        ("停止",  "cli_execute", 0.5),

        # ── Skill ──
        ("skill", "skill_execute", 0.7),
        ("技能",  "skill_execute", 0.6),

        # ── 记忆 ──
        ("我记得", "memory_retrieve", 0.7),
        ("之前",   "memory_retrieve", 0.5),
        ("上次",   "memory_retrieve", 0.6),
        ("以前",   "memory_retrieve", 0.5),

        # ── 总结 ──
        ("总结", "memory_summarize", 0.6),
        ("归纳", "memory_summarize", 0.6),
        ("汇总", "memory_summarize", 0.5),

        # ── 通用 ──
        ("分析", "llm_analysis", 0.4),
        ("解释", "llm_analysis", 0.4),
        ("翻译", "llm_analysis", 0.5),
        ("对比", "llm_analysis", 0.4),

        # ── MCP GitHub ──
        ("issue",  "mcp_github", 0.6),
        ("pr",     "mcp_github", 0.6),
        ("github", "mcp_github", 0.5),
    ]

    @classmethod
    def scan(cls, message: str) -> list[ScanResult]:
        """
        扫描消息，返回按置信度降序排列的候选意图列表。

        Args:
            message: 用户消息

        Returns:
            候选意图列表，按置信度降序
        """
        text = message.lower()
        matched: dict[str, ScanResult] = {}

        for keyword, intent_type, confidence in cls.INTENT_KEYWORDS:
            if keyword in text:
                # 已匹配到同一 intent_type 时，取最高置信度
                existing = matched.get(intent_type)
                if existing is None or confidence > existing.confidence:
                    matched[intent_type] = ScanResult(
                        intent_type=intent_type,
                        confidence=confidence,
                        matched_keyword=keyword,
                        source="rule",
                    )

        results = list(matched.values())
        results.sort(key=lambda r: r.confidence, reverse=True)

        return results
