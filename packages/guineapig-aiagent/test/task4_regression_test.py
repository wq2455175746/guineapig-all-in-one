"""
Task 4 (P1) 回归测试 — RAG 后台任务管理、下载错误传播、LLM/Milvus 客户端复用。
"""

import asyncio

import pytest
from botocore.exceptions import ClientError

from app.core.oss import OSS
from app.core.oss_wrapper_utils import download_file_from_s3
from app.routers.rag import (
    _pending_embedding_tasks,
    _track_embedding_task,
    cancel_pending_embedding_tasks,
)


class TestDownloadFailurePropagation:
    """下载失败应准确传播，而非静默吞掉误报成功"""

    def _oss(self, mocker):
        oss = object.__new__(OSS)
        oss.bucket_name = "test-bucket"
        oss.s3_client = mocker.MagicMock()
        return oss

    def test_download_single_propagates_client_error(self, mocker):
        """_download_single 在 ClientError 时应向上抛出"""
        oss = self._oss(mocker)
        oss.s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "not found"}}, "GetObject"
        )
        with pytest.raises(ClientError):
            oss._download_single("missing.txt", "/tmp/does-not-matter.bin")

    def test_download_file_from_s3_returns_false_on_client_error(self, mocker, tmp_path):
        """远端访问失败应返回 False"""
        oss = self._oss(mocker)
        oss.s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "403", "Message": "denied"}}, "GetObject"
        )
        mocker.patch("app.core.oss_wrapper_utils.get_oss_client", return_value=oss)
        assert download_file_from_s3("secret.txt", str(tmp_path / "out.bin")) is False

    def test_download_file_from_s3_returns_false_on_io_error(self, mocker, tmp_path):
        """本地写入失败应返回 False，而非此前误报成功"""
        oss = self._oss(mocker)
        oss.s3_client.get_object.return_value = {"ContentLength": 4, "Body": mocker.MagicMock()}
        mocker.patch("app.core.oss_wrapper_utils.get_oss_client", return_value=oss)
        target_dir = tmp_path / "out"
        target_dir.mkdir()
        # 目标路径是目录 → open(..., "wb") 抛 IsADirectoryError（OSError 子类）
        assert download_file_from_s3("key", str(target_dir)) is False

    def test_download_file_from_s3_success(self, mocker, tmp_path):
        """成功路径应返回 True 且文件内容正确"""
        oss = self._oss(mocker)

        class FakeBody:
            def iter_chunks(self, chunk_size):
                yield b"data"
                yield b"-more"

        oss.s3_client.get_object.return_value = {"ContentLength": 9, "Body": FakeBody()}
        mocker.patch("app.core.oss_wrapper_utils.get_oss_client", return_value=oss)
        target = tmp_path / "f.bin"
        assert download_file_from_s3("key", str(target)) is True
        assert target.read_bytes() == b"data-more"


class TestRagBackgroundTask:
    """rag.py 后台嵌入任务应被跟踪、记录异常、可取消"""

    @pytest.mark.asyncio
    async def test_task_tracked_and_cancelled_on_shutdown(self):
        async def long_running():
            await asyncio.sleep(30)

        task = _track_embedding_task(long_running())
        assert task in _pending_embedding_tasks

        cancel_pending_embedding_tasks()
        assert task not in _pending_embedding_tasks
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_task_exception_recorded_in_done_callback(self, mocker):
        """任务抛出的异常应被 done 回调消费并记录，而非泄漏"""
        spy = mocker.patch("app.routers.rag.logger.error")

        async def boom():
            raise RuntimeError("boom")

        task = _track_embedding_task(boom())
        try:
            await task
        except RuntimeError:
            pass

        assert task not in _pending_embedding_tasks
        assert any("嵌入后台任务异常" in str(c.args[0]) for c in spy.call_args_list)


class TestLlmClientReuse:
    """共享 LLM 客户端应按配置缓存复用"""

    def test_sync_and_async_clients_reused(self):
        from openai import AsyncOpenAI, OpenAI

        from app.core.llm_clients import (
            clear_llm_clients,
            get_async_llm_client,
            get_llm_client,
        )

        clear_llm_clients()
        try:
            c1 = get_llm_client("k", "https://u.example/v1", 120.0)
            c2 = get_llm_client("k", "https://u.example/v1", 120.0)
            assert c1 is c2
            assert isinstance(c1, OpenAI)

            a1 = get_async_llm_client("k", "https://u.example/v1", 120.0)
            a2 = get_async_llm_client("k", "https://u.example/v1", 120.0)
            assert a1 is a2
            assert isinstance(a1, AsyncOpenAI)

            # 不同 timeout 视为不同配置，应新建客户端
            assert get_llm_client("k", "https://u.example/v1", 60.0) is not c1
        finally:
            clear_llm_clients()


class TestMilvusClientReuse:
    """Milvus 客户端应按线程缓存复用"""

    def test_client_reused_per_thread(self, mocker):
        import pymilvus

        from app.core import milvus_clients

        mock_instance = mocker.MagicMock()
        mock_class = mocker.MagicMock(return_value=mock_instance)
        mocker.patch.object(pymilvus, "MilvusClient", mock_class)
        milvus_clients.clear_milvus_clients()

        c1 = milvus_clients.get_milvus_client("localhost", "19530", "db")
        c2 = milvus_clients.get_milvus_client("localhost", "19530", "db")
        assert c1 is c2
        assert mock_class.call_count == 1

        # 不同 db_name 视为不同客户端
        milvus_clients.get_milvus_client("localhost", "19530", "other")
        assert mock_class.call_count == 2


class TestRetrieveRagContextAsync:
    """retrieve_rag_context 异步化回归测试 — 直接 await，mock 底层向量化/检索/重排"""

    async def _call(self, **overrides):
        from app.services.rag_retrieval_service import retrieve_rag_context

        kwargs = dict(
            rag_names=["kb_a", "kb_b"],
            user_id=42,
            query="测试问题",
            embedding_api_url="https://llm.example/v1",
            embedding_api_key="k",
            embedding_model_name="emb-model",
            reranker_api_url="https://llm.example/v1",
            reranker_api_key="k",
            reranker_model_name="rerank-model",
            milvus_host="localhost",
            milvus_port="19530",
            top_k=20,
            rerank_top_k=3,
        )
        kwargs.update(overrides)
        return await retrieve_rag_context(**kwargs)

    @pytest.mark.asyncio
    async def test_searches_all_collections_and_formats_results(self, mocker):
        """应检索全部集合并返回包含重排结果的 Markdown"""
        mocker.patch(
            "app.services.rag_service.EmbeddingService.get_embedding",
            return_value=[0.1, 0.2, 0.3],
        )

        search_results = {
            "kb_a": [
                {"text_chunk": "片段来自知识库A", "score": 0.95, "collection": "kb_a"}
            ],
            "kb_b": [
                {"text_chunk": "片段来自知识库B", "score": 0.88, "collection": "kb_b"}
            ],
        }
        mock_search = mocker.patch(
            "app.services.rag_retrieval_service.MilvusSearcher.search_collection",
            side_effect=lambda collection_name, **kwargs: search_results[collection_name],
        )

        # 重排直接按传入顺序返回（不做实际排序）
        mocker.patch(
            "app.services.rag_retrieval_service.RerankerService.rerank",
            side_effect=lambda query, documents, top_k=3: [
                {"text": documents[0], "relevance_score": 1.0, "index": 0},
                {"text": documents[1], "relevance_score": 0.9, "index": 1},
            ],
        )

        result = await self._call()

        # 所有集合都被检索，且传入的向量与 top_k 正确
        assert mock_search.call_count == 2
        called_names = {c.kwargs["collection_name"] for c in mock_search.call_args_list}
        assert called_names == {"kb_a", "kb_b"}
        for call in mock_search.call_args_list:
            assert call.kwargs["query_embedding"] == [0.1, 0.2, 0.3]
            assert call.kwargs["top_k"] == 20

        # 返回结构：Markdown 片段包含重排后的文本块
        assert "## 知识库检索结果" in result
        assert "片段来自知识库A" in result
        assert "片段来自知识库B" in result
        assert "请参考以上知识库检索结果回答用户问题" in result

    @pytest.mark.asyncio
    async def test_no_search_results_returns_empty_string(self, mocker):
        """无检索结果时应返回空字符串"""
        mocker.patch(
            "app.services.rag_service.EmbeddingService.get_embedding",
            return_value=[0.1],
        )
        mocker.patch(
            "app.services.rag_retrieval_service.MilvusSearcher.search_collection",
            return_value=[],
        )

        result = await self._call(rag_names=["kb_a", "kb_b"])
        assert result == ""

    @pytest.mark.asyncio
    async def test_empty_rag_names_returns_empty_string(self, mocker):
        """rag_names 为空时不检索任何集合，直接返回空字符串"""
        mocker.patch(
            "app.services.rag_service.EmbeddingService.get_embedding",
            return_value=[0.1],
        )
        mock_search = mocker.patch(
            "app.services.rag_retrieval_service.MilvusSearcher.search_collection"
        )

        result = await self._call(rag_names=[])
        assert result == ""
        mock_search.assert_not_called()