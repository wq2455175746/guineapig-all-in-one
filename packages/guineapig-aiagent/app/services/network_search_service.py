"""
Network Search Service — 调用 SearXNG 获取联网搜索结果并格式化为 LLM 上下文。
"""

import httpx

from app.config import settings
from app.core.log import logger


async def search_web(query: str, max_results: int = 5) -> str:
    """
    调用 SearXNG 搜索，返回 Markdown 格式的结果字符串。
    搜索失败或结果为空时返回空字符串，不中断调用方流程。
    """
    if not settings.SEARXNG_URL:
        logger.warning("[NetworkSearch] SEARXNG_URL 未配置")
        return ""

    search_url = f"{settings.SEARXNG_URL}/search?q={query}&format=json&language=zh"
    logger.info(f"[NetworkSearch] 搜索: {query[:80]}...")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(search_url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"[NetworkSearch] 请求失败: {e}")
        return ""

    results = data.get("results", [])
    if not results:
        logger.info("[NetworkSearch] 无搜索结果")
        return ""

    lines = []
    for i, r in enumerate(results[:max_results], 1):
        title = r.get("title", "无标题")
        url = r.get("url", "")
        snippet = r.get("content", r.get("snippet", "")).strip()
        lines.append(f"{i}. [{title}]({url})")
        if snippet:
            lines.append(f"   {snippet[:500]}")
        lines.append("")

    formatted = "\n".join(lines)
    logger.info(f"[NetworkSearch] 获取到 {len(results)} 条结果，注入 {min(len(results), max_results)} 条")
    return formatted
