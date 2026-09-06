"""RAG 嵌入路由"""

import asyncio
from fastapi import APIRouter

from app.core.log import logger
from app.schemas.base_models import success_response, error_response
from app.schemas.rag_models import RagEmbedRequest, RagDeleteEmbeddingsRequest
from app.services.rag_service import process_file_embedding, MilvusWriter

router = APIRouter(prefix="/guineapig-aiagent/rag", tags=["rag"])

# 后台嵌入任务集合：保留强引用避免被 GC，done 回调统一记录异常，关闭时统一取消
_pending_embedding_tasks: set[asyncio.Task] = set()


def _track_embedding_task(coro) -> asyncio.Task:
    """创建并跟踪后台嵌入任务，异常统一记录，避免 fire-and-forget 泄漏。"""
    task = asyncio.create_task(coro)
    _pending_embedding_tasks.add(task)
    task.add_done_callback(_on_embedding_task_done)
    return task


def _on_embedding_task_done(task: asyncio.Task):
    _pending_embedding_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(f"[RAG] 嵌入后台任务异常: {exc!r}")


def cancel_pending_embedding_tasks() -> None:
    """服务关闭时取消所有未完成的后台嵌入任务。"""
    tasks = list(_pending_embedding_tasks)
    for task in tasks:
        task.cancel()
    _pending_embedding_tasks.clear()


@router.post("/embed")
async def embed_file(request: RagEmbedRequest):
    """
    接收文件嵌入任务。

    立即返回 task_id，后台异步处理文件下载、分块、向量化和 Milvus 写入。
    """
    logger.info(f"[RAG] 收到嵌入请求: file_id={request.file_id}, "
                f"rag={request.rag_name}, task_id={request.task_id}")

    try:
        # 启动后台异步任务
        params = request.model_dump()
        _track_embedding_task(_run_embedding_async(params))

        return success_response(data={"task_id": request.task_id, "message": "embedding started"})
    except Exception as e:
        logger.error(f"[RAG] 启动嵌入任务失败: {e}")
        return error_response(message=f"启动失败: {str(e)}", code=500)


@router.post("/delete-embeddings")
async def delete_embeddings(request: RagDeleteEmbeddingsRequest):
    """
    删除指定 file_id 在知识库中的所有嵌入向量。
    同步执行（操作轻量，不应阻塞）。
    """
    logger.info(f"[RAG] 收到删除嵌入请求: file_id={request.file_id}, rag_name={request.rag_name}")

    try:
        from app.config import settings

        writer = MilvusWriter(host=settings.MILVUS_HOST, port=settings.MILVUS_PORT)
        ok = writer.delete_by_file_id(
            collection_name=request.rag_name,
            file_id=request.file_id,
        )
        if ok:
            return success_response(data={"message": "embeddings deleted"})
        else:
            return error_response(message="删除嵌入失败", code=500)
    except Exception as e:
        logger.error(f"[RAG] 删除嵌入异常: {e}")
        return error_response(message=str(e), code=500)


async def _run_embedding_async(params: dict):
    """在后台线程中运行嵌入处理（避免阻塞事件循环）"""
    await asyncio.to_thread(process_file_embedding, params)
