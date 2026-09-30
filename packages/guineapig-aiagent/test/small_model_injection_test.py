"""小模型上下文注入回归测试。

is_small_model=True 时，搜索/RAG 结果注入到最后一条 user 消息；
is_small_model=False（默认）时保持原行为，注入 system prompt。
同时验证小模型下 DefaultSkillInjector 跳过冗长 Command Rules。
"""

import pytest

_CONTEXT_INSTRUCTION = "仅将其作为信息参考"


class TestSmallModelSearchInjection:
    @pytest.mark.asyncio
    async def test_small_model_injects_search_to_user_message(self, mocker):
        """小模型：联网搜索结果应追加到最后一条 user 消息，而非 system"""
        from app.services.llm_pipeline import NetworkSearchProcessor, PipelineContext

        mocker.patch(
            "app.services.network_search_service.search_web",
            return_value="1. [标题](http://x)",
        )

        ctx = PipelineContext(
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "今天天气"},
            ],
            api_key="k",
            base_url="https://llm.example/v1",
            model_name="m",
            web_search_enabled=True,
            is_small_model=True,
        )
        await NetworkSearchProcessor().process(ctx)

        # system 不被污染
        assert ctx.messages[0]["content"] == "sys"
        # 搜索结果在 user 消息末尾
        user_content = ctx.messages[1]["content"]
        assert user_content.startswith("今天天气")
        assert "1. [标题](http://x)" in user_content
        assert _CONTEXT_INSTRUCTION in user_content

    @pytest.mark.asyncio
    async def test_large_model_injects_search_to_system(self, mocker):
        """大模型（默认）：联网搜索结果仍注入 system prompt"""
        from app.services.llm_pipeline import NetworkSearchProcessor, PipelineContext

        mocker.patch(
            "app.services.network_search_service.search_web",
            return_value="1. [标题](http://x)",
        )

        ctx = PipelineContext(
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "今天天气"},
            ],
            api_key="k",
            base_url="https://llm.example/v1",
            model_name="m",
            web_search_enabled=True,
        )
        await NetworkSearchProcessor().process(ctx)

        sys_content = ctx.messages[0]["content"]
        assert sys_content.startswith("sys")
        assert "1. [标题](http://x)" in sys_content
        # user 消息未被污染
        assert ctx.messages[1]["content"] == "今天天气"

    @pytest.mark.asyncio
    async def test_small_model_uses_last_user_message(self, mocker):
        """小模型：应注入到最后一条 user 消息（而非第一条）"""
        from app.services.llm_pipeline import NetworkSearchProcessor, PipelineContext

        mocker.patch(
            "app.services.network_search_service.search_web",
            return_value="1. [标题](http://x)",
        )

        ctx = PipelineContext(
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "上一条"},
                {"role": "assistant", "content": "回答"},
                {"role": "user", "content": "当前问题"},
            ],
            api_key="k",
            base_url="https://llm.example/v1",
            model_name="m",
            web_search_enabled=True,
            is_small_model=True,
        )
        await NetworkSearchProcessor().process(ctx)

        assert ctx.messages[1]["content"] == "上一条"
        assert ctx.messages[3]["content"].startswith("当前问题")
        assert "1. [标题](http://x)" in ctx.messages[3]["content"]


class TestSmallModelRagInjection:
    @pytest.mark.asyncio
    async def test_small_model_skips_rag(self, mocker):
        """小模型：即使传了 rag_context 也应跳过 RAG 记忆注入"""
        from app.services.llm_pipeline import PipelineContext, RAGRetrievalProcessor

        mock_retrieve = mocker.patch(
            "app.services.rag_retrieval_service.retrieve_rag_context",
            return_value="## 知识库\n片段来自知识库A",
        )

        ctx = PipelineContext(
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "帮我查知识库"},
            ],
            api_key="k",
            base_url="https://llm.example/v1",
            model_name="m",
            rag_context={
                "rag_names": ["kb_a"],
                "embedding_api_url": "https://llm.example/v1",
                "embedding_api_key": "k",
                "embedding_model_name": "emb-model",
                "reranker_api_url": "https://llm.example/v1",
                "reranker_api_key": "k",
                "reranker_model_name": "rerank-model",
                "top_k": 20,
                "rerank_top_k": 3,
            },
            is_small_model=True,
        )
        await RAGRetrievalProcessor().process(ctx)

        mock_retrieve.assert_not_called()
        assert ctx.messages[0]["content"] == "sys"
        assert ctx.messages[1]["content"] == "帮我查知识库"

    @pytest.mark.asyncio
    async def test_large_model_injects_rag_to_system(self, mocker):
        """大模型：RAG 检索结果仍注入 system prompt"""
        from app.services.llm_pipeline import PipelineContext, RAGRetrievalProcessor

        mocker.patch(
            "app.services.rag_retrieval_service.retrieve_rag_context",
            return_value="## 知识库\n片段来自知识库A",
        )
        mocker.patch("app.config.settings.MILVUS_HOST", "x")

        ctx = PipelineContext(
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "帮我查知识库"},
            ],
            api_key="k",
            base_url="https://llm.example/v1",
            model_name="m",
            rag_context={
                "rag_names": ["kb_a"],
                "embedding_api_url": "https://llm.example/v1",
                "embedding_api_key": "k",
                "embedding_model_name": "emb-model",
                "reranker_api_url": "https://llm.example/v1",
                "reranker_api_key": "k",
                "reranker_model_name": "rerank-model",
                "top_k": 20,
                "rerank_top_k": 3,
            },
        )
        await RAGRetrievalProcessor().process(ctx)

        assert ctx.messages[0]["content"].startswith("sys")
        assert "片段来自知识库A" in ctx.messages[0]["content"]
        assert ctx.messages[1]["content"] == "帮我查知识库"


class TestSmallModelDefaultSkillInjector:
    @pytest.mark.asyncio
    async def test_small_model_skips_command_rules(self):
        """小模型：未加载技能时注入简短提示而非冗长 Command Rules"""
        from app.services.llm_pipeline import DefaultSkillInjector, PipelineContext

        ctx = PipelineContext(
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "问题"},
            ],
            api_key="k",
            base_url="https://llm.example/v1",
            model_name="m",
            is_small_model=True,
        )
        await DefaultSkillInjector().process(ctx)

        sys_content = ctx.messages[0]["content"]
        assert sys_content.startswith("sys")
        # 不含冗长 Command Rules
        assert "Command Generation Rules" not in sys_content
        assert "无需执行命令" in sys_content

    @pytest.mark.asyncio
    async def test_large_model_keeps_command_rules(self):
        """大模型：未加载技能时仍注入完整 Command Rules"""
        from app.services.llm_pipeline import DefaultSkillInjector, PipelineContext

        ctx = PipelineContext(
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "问题"},
            ],
            api_key="k",
            base_url="https://llm.example/v1",
            model_name="m",
        )
        await DefaultSkillInjector().process(ctx)

        sys_content = ctx.messages[0]["content"]
        assert "Command Generation Rules" in sys_content