"""
RAG 检索服务 — Milvus 向量搜索 + Reranker 重排序 + 结果格式化
用于 LLM Pipeline 中的 RAGRetrievalProcessor。
"""

import asyncio
import json
from typing import Optional

import requests

from app.config import settings
from app.core.log import logger
from app.core.milvus_clients import get_milvus_client
from app.services.prompt_context import wrap_context


def _estimate_tokens(text: str) -> int:
    """估算文本的 token 数（中文字符 ~1 token / 1.5 字符，英文 ~1 token / 4 字符）。"""
    if not text:
        return 0
    chinese = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other = len(text) - chinese
    return max(1, int(chinese / 1.5 + other / 4))


class MilvusSearcher:
    """Milvus 向量检索服务（基于 MilvusClient）"""

    def __init__(
        self,
        host: str = "localhost",
        port: str = "19530",
        db_name: str = "guineapig_user_rag",
    ):
        self.host = host
        self.port = port
        self.db_name = db_name

    def _create_client(self):
        """获取 MilvusClient 实例（按线程缓存复用，避免每次新建连接）"""
        return get_milvus_client(self.host, self.port, self.db_name)

    def search_collection(
        self,
        collection_name: str,
        query_embedding: list[float],
        user_id: int,
        top_k: int = 20,
    ) -> list[dict]:
        """
        在指定集合中搜索 top_k 个结果。

        Returns:
            [{"text_chunk": "...", "score": 0.95, "collection": "..."}, ...]
        """
        try:
            client = self._create_client()

            # 检查集合是否存在
            if not client.has_collection(collection_name):
                logger.warning(
                    f"[RAG] Milvus 集合不存在: {collection_name}"
                )
                return []

            # 加载集合到内存（幂等操作，重复加载无害）
            client.load_collection(collection_name)

            # 搜索参数
            search_params = {
                "metric_type": "IP",
                "params": {"nprobe": 10},
            }

            # 按 user_id 分区过滤表达式
            expr = f'user_id == "{user_id}"'

            results = client.search(
                collection_name=collection_name,
                data=[query_embedding],
                anns_field="embedding",
                search_params=search_params,
                limit=top_k,
                filter=expr,
                output_fields=["text_chunk"],
            )

            hits = []
            for hits_group in results:
                for hit in hits_group:
                    hits.append({
                        "text_chunk": hit.get("entity", {}).get("text_chunk", ""),
                        "score": hit.get("distance", 0),
                        "collection": collection_name,
                    })

            return hits

        except Exception as e:
            logger.error(f"[RAG] Milvus 搜索失败: collection={collection_name}, err={e}")
            return []

    @staticmethod
    def load_all_collections(
        host: str = "localhost",
        port: str = "19530",
        db_name: str = "guineapig_user_rag",
    ) -> None:
        """
        启动时加载 Milvus 数据库中所有集合到内存。
        避免后续搜索时因集合未加载而查询不到数据。
        """
        try:
            client = get_milvus_client(host, port, db_name)
            collections = client.list_collections()
            if not collections:
                logger.info(f"[RAG] Milvus 数据库 '{db_name}' 中没有集合需要加载")
                return

            logger.info(f"[RAG] 开始加载 {len(collections)} 个 Milvus 集合到内存...")
            for name in collections:
                try:
                    client.load_collection(name)
                    logger.info(f"[RAG]   ✓ 集合已加载: {name}")
                except Exception as e:
                    logger.warning(f"[RAG]   ✗ 集合加载失败: {name}, err={e}")

            logger.info(f"[RAG] Milvus 集合加载完成")
        except Exception as e:
            logger.error(f"[RAG] 连接 Milvus 失败: {e}")


class RerankerService:
    """重排序服务 — 使用 OpenAI 兼容格式调用 Reranker API"""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        model_name: str,
        timeout: int = 30,
    ):
        self.api_url = api_url.rstrip("/")
        # 兼容多种 URL 格式
        if not self.api_url.endswith("/rerank"):
            if self.api_url.endswith("/v1"):
                self.api_url += "/rerank"
            elif "/v1" in self.api_url and not self.api_url.endswith("/rerank"):
                self.api_url = self.api_url.rstrip("/") + "/rerank"
            else:
                self.api_url = self.api_url.rstrip("/") + "/v1/rerank"
        self.api_key = api_key
        self.model_name = model_name
        self.timeout = timeout

    def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int = 3,
    ) -> list[dict]:
        """
        调用重排序 API，返回按相关性得分排序的前 top_k 个文档。

        API 格式参考 Cohere Rerank:
            POST /v1/rerank
            {"model": "...", "query": "...", "documents": [...], "top_n": N}

        Returns:
            [{"text": "...", "relevance_score": 0.95, "index": 0}, ...]
        """
        if not documents:
            return []

        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
            payload = {
                "model": self.model_name,
                "query": query,
                "documents": documents,
                "top_n": top_k,
            }

            resp = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )

            if resp.status_code != 200:
                logger.warning(
                    f"[RAG] Reranker API 返回非 200: {resp.status_code}, body={resp.text[:200]}"
                )
                # 回退：取原始 documents 的前 top_k 条
                return self._fallback_rank(documents, top_k)

            data = resp.json()

            # 兼容两种返回格式：
            # 1. Cohere 格式: {"results": [{"index": 0, "relevance_score": 0.95, "document": {...}}, ...]}
            # 2. 简化格式: [{"index": 0, "relevance_score": 0.95}, ...]
            results = data.get("results", [])
            if not results and isinstance(data, list):
                results = data

            ranked = []
            for item in results:
                idx = item.get("index", 0)
                score = item.get("relevance_score", 0)
                doc_text = documents[idx] if idx < len(documents) else ""
                # 部分 API 在 document 字段中返回原始文本
                doc = item.get("document") or {}
                if isinstance(doc, dict):
                    doc_text = doc.get("text", doc_text)
                ranked.append({
                    "text": doc_text,
                    "relevance_score": score,
                    "index": idx,
                })

            # 按得分降序排列
            ranked.sort(key=lambda x: x["relevance_score"], reverse=True)
            return ranked[:top_k]

        except Exception as e:
            logger.warning(f"[RAG] Reranker 调用失败: {e}，回退到原始排序")
            return self._fallback_rank(documents, top_k)

    def _fallback_rank(self, documents: list[str], top_k: int) -> list[dict]:
        """当 Reranker 不可用时的回退：直接取前 top_k 条"""
        return [
            {"text": documents[i], "relevance_score": 0.0, "index": i}
            for i in range(min(top_k, len(documents)))
        ]


async def retrieve_rag_context(
    rag_names: list[str],
    user_id: int,
    query: str,
    embedding_api_url: str,
    embedding_api_key: str,
    embedding_model_name: str,
    reranker_api_url: str,
    reranker_api_key: str,
    reranker_model_name: str,
    milvus_host: str,
    milvus_port: str,
    top_k: int = 20,
    rerank_top_k: int = 3,
) -> str:
    """
    RAG 检索完整流程：
    1. 对用户查询进行向量化
    2. 对每个 rag_name 在 Milvus 中搜索（按 user_id 分区过滤）
    3. 合并所有结果
    4. 使用 Reranker 重排序
    5. 格式化为 Markdown 字符串

    Returns:
        格式化后的 Markdown 字符串，或空字符串（无结果时）
    """
    # 步骤 1: 向量化用户查询
    from app.services.rag_service import EmbeddingService

    embedder = EmbeddingService(
        api_url=embedding_api_url,
        model_name=embedding_model_name,
    )
    query_vector = await asyncio.to_thread(embedder.get_embedding, query)
    if not query_vector:
        logger.warning("[RAG] 查询向量化失败，跳过 RAG 检索")
        return ""

    # 步骤 2: 并发搜索各集合（每个集合一个线程，MilvusClient 按线程缓存复用）
    searcher = MilvusSearcher(host=milvus_host, port=milvus_port)
    all_results = []
    if rag_names:
        per_collection = await asyncio.gather(
            *(
                asyncio.to_thread(
                    searcher.search_collection,
                    collection_name=name,
                    query_embedding=query_vector,
                    user_id=user_id,
                    top_k=top_k,
                )
                for name in rag_names
            )
        )
        for results in per_collection:
            all_results.extend(results)

    if not all_results:
        logger.info("[RAG] Milvus 无搜索结果")
        return ""

    logger.info(f"[RAG] Milvus 搜索完成: 共 {len(all_results)} 条结果")

    # 步骤 3: 重排序
    documents = [r["text_chunk"] for r in all_results]
    reranker = RerankerService(
        api_url=reranker_api_url,
        api_key=reranker_api_key,
        model_name=reranker_model_name,
    )
    reranked = await asyncio.to_thread(reranker.rerank, query, documents, rerank_top_k)

    logger.info(f"[RAG] 重排序完成: 返回 {len(reranked)} 条")

    # 步骤 4: 格式化为 Markdown，并在总 token 预算内裁剪/截断
    formatted = _format_rag_markdown(reranked)
    formatted = _apply_token_budget(formatted, reranked)
    return wrap_context(formatted)


def _format_rag_markdown(reranked: list[dict], chunk_cap: int = 2000) -> str:
    """将重排结果格式化为 Markdown 字符串。"""
    lines = ["\n\n## 知识库检索结果"]
    for item in reranked:
        text = item["text"]
        score = item["relevance_score"]
        # 截断单个文本块，防止 system prompt 过大
        if len(text) > chunk_cap:
            text = text[:chunk_cap] + "..."
        lines.append(f"\n### 相关片段（相关性: {score:.2f}）")
        lines.append(text)

    lines.append(
        "\n\n请参考以上知识库检索结果回答用户问题。"
        "优先采用相关性高的信息。"
    )

    return "\n".join(lines)


def _apply_token_budget(markdown: str, reranked: list[dict]) -> str:
    """
    RAG 注入上下文 token 预算守卫。

    超过 settings.RAG_CONTEXT_TOKEN_BUDGET 时：
    1. 优先压缩每个片段的长度（chunk_cap 逐档减半，下限 200 字符）；
    2. 仍超预算则丢弃相关性最低的片段（reranked 已按得分降序），并重置长度上限。
    """
    budget = max(1, settings.RAG_CONTEXT_TOKEN_BUDGET)
    if _estimate_tokens(markdown) <= budget:
        return markdown

    chunks = list(reranked)  # 已按相关性得分降序
    cap = 2000
    min_cap = 200
    while chunks:
        cap = max(cap, min_cap)
        result = _format_rag_markdown(chunks, chunk_cap=cap)
        if _estimate_tokens(result) <= budget:
            return result
        if cap > min_cap:
            cap //= 2
            continue
        if len(chunks) > 1:
            # 压缩到下限仍超预算 → 丢弃最低分片段并重置长度上限
            chunks = chunks[:-1]
            cap = 2000
            continue
        return result  # 仅剩最高分片段且已达最小截断，尽力而为
    return _format_rag_markdown(reranked[:1], chunk_cap=min_cap)
