"""
RAG 嵌入服务 — 文件下载、分块、向量化、写入 Milvus、进度回调
"""

import os
import uuid
import requests
from datetime import datetime

from app.config import settings
from app.core.log import logger
from app.core.oss_wrapper_utils import download_file_from_s3


class TextChunker:
    """文本分块工具"""

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split_text(self, text: str) -> list:
        if not text or not text.strip():
            return []
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0
        max_iterations = len(text) // max(1, self.chunk_size - self.overlap) + 10
        iteration = 0

        while start < len(text) and iteration < max_iterations:
            iteration += 1
            end = min(start + self.chunk_size, len(text))

            # 尝试在句子边界切割
            if end < len(text):
                found_sep = False
                for sep in ["。", "！", "？", "\n", ".", "!", "?", ";", "；"]:
                    last_sep = text.rfind(sep, start, end)
                    if last_sep != -1 and last_sep > start + self.chunk_size // 2:
                        end = last_sep + 1
                        found_sep = True
                        break
                if not found_sep and end <= start:
                    end = min(start + 1, len(text))

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(chunk_text)

            # 移动 start
            new_start = end - self.overlap
            if new_start <= start:
                new_start = start + 1
            start = new_start

            # 剩余文本太少时直接追加
            remaining = len(text) - start
            if 0 < remaining < self.chunk_size // 2:
                remaining = text[start:].strip()
                if remaining:
                    chunks.append(remaining)
                break

        return chunks


class EmbeddingService:
    """向量化服务 — 使用 OpenAI 兼容格式"""

    def __init__(self, api_url: str, model_name: str, timeout: int = 30):
        self.api_url = api_url.rstrip("/")
        # 确保 URL 指向 /v1/embeddings
        if not self.api_url.endswith("/embeddings"):
            if self.api_url.endswith("/v1"):
                self.api_url += "/embeddings"
            elif "/v1" not in self.api_url:
                self.api_url = self.api_url.rstrip("/") + "/v1/embeddings"
            else:
                self.api_url = self.api_url.rstrip("/") + "/embeddings"
        self.model_name = model_name
        self.timeout = timeout

    def get_embedding(self, text: str) -> list | None:
        if not text or not text.strip():
            return None
        try:
            resp = requests.post(
                self.api_url,
                json={"model": self.model_name, "input": text},
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                embeddings = data.get("data", [])
                if embeddings:
                    return embeddings[0].get("embedding")
            return None
        except Exception as e:
            logger.error(f"向量化失败: {e}")
            return None


class MilvusWriter:
    """Milvus 写入服务（基于 MilvusClient）"""

    def __init__(
        self,
        host: str = "localhost",
        port: str = "19530",
        db_name: str = "guineapig_user_rag",
    ):
        self.host = host
        self.port = port
        self.db_name = db_name

    def _make_client(self, db_name: str | None = None):
        """创建 MilvusClient 实例"""
        from pymilvus import MilvusClient

        return MilvusClient(
            uri=f"http://{self.host}:{self.port}",
            db_name=db_name or self.db_name,
        )

    def ensure_collection(self, collection_name: str, dimension: int):
        """确保数据库和集合存在，返回指向目标数据库的 MilvusClient"""
        from pymilvus import MilvusClient, DataType

        # 1) 确保数据库存在（用 default DB 连接来管理数据库）
        admin_client = self._make_client(db_name="default")
        databases = admin_client.list_databases()
        if self.db_name not in databases:
            admin_client.create_database(self.db_name)
            logger.info(f"创建 Milvus 数据库: {self.db_name}")
        else:
            logger.info(f"Milvus 数据库已存在: {self.db_name}")

        # 2) 使用指向目标数据库的 client
        client = self._make_client()

        # 3) 创建/获取集合
        if client.has_collection(collection_name):
            logger.info(f"集合已存在: {collection_name}")
            return client

        schema = MilvusClient.create_schema(
            auto_id=False,
            enable_dynamic_field=False,
        )
        schema.add_field(
            field_name="id", datatype=DataType.VARCHAR, max_length=36, is_primary=True
        )
        schema.add_field(
            field_name="user_id",
            datatype=DataType.VARCHAR,
            max_length=64,
            is_partition_key=True,
        )
        schema.add_field(
            field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=dimension
        )
        schema.add_field(
            field_name="text_chunk", datatype=DataType.VARCHAR, max_length=65535
        )
        schema.add_field(
            field_name="file_id", datatype=DataType.VARCHAR, max_length=36
        )

        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            metric_type="IP",
            index_type="IVF_FLAT",
            params={"nlist": 128},
        )

        client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params,
        )
        logger.info(f"创建 Milvus 集合: {collection_name}, 维度: {dimension}")
        return client

    def delete_by_file_id(self, collection_name: str, file_id: int):
        """根据 file_id 删除 Milvus 集合中的记录"""
        from pymilvus import MilvusClient

        client = self._make_client()
        if not client.has_collection(collection_name):
            logger.warning(f"集合不存在，跳过删除: {collection_name}")
            return True

        file_id_str = str(file_id)
        try:
            result = client.delete(
                collection_name=collection_name,
                filter=f'file_id == "{file_id_str}"',
            )
            logger.info(
                f"从 Milvus 集合 {collection_name} 删除 file_id={file_id_str} 的记录: {result}"
            )
            return True
        except Exception as e:
            logger.error(f"Milvus 删除失败: {e}")
            return False

    def insert_batch(
        self,
        client,
        collection_name: str,
        file_id: int,
        ids: list,
        user_ids: list,
        embeddings: list,
        text_chunks: list,
    ):
        """批量插入数据（行式 dict 格式）"""
        client.load_collection(collection_name)
        file_id_str = str(file_id)
        data = [
            {
                "id": ids[i],
                "user_id": user_ids[i],
                "embedding": embeddings[i],
                "text_chunk": text_chunks[i],
                "file_id": file_id_str,
            }
            for i in range(len(ids))
        ]
        try:
            client.insert(collection_name=collection_name, data=data)
            client.flush(collection_name=collection_name)
            logger.info(f"插入 {len(ids)} 条数据到 Milvus")
            return True
        except Exception as e:
            logger.error(f"插入 Milvus 失败: {e}")
            return False


def report_progress(backend_url: str, file_id: int, task_id: str, progress: int):
    """回调后端进度接口"""
    try:
        resp = requests.post(
            f"{backend_url}/inner/api/v1/file/embed-progress",
            json={
                "file_id": file_id,
                "task_id": task_id,
                "progress": progress,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info(
                f"报告进度 {progress}% 成功: file_id={file_id}, task_id={task_id}"
            )
        else:
            logger.warning(f"报告进度失败: {resp.status_code}")
    except Exception as e:
        logger.warning(f"报告进度异常: {e}")


def report_error(backend_url: str, file_id: int, task_id: str, error_msg: str):
    """回调后端报告嵌入失败"""
    try:
        resp = requests.post(
            f"{backend_url}/inner/api/v1/file/embed-progress",
            json={
                "file_id": file_id,
                "task_id": task_id,
                "progress": 0,
                "error": error_msg,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info(f"报告错误成功: file_id={file_id}, task_id={task_id}")
        else:
            logger.warning(f"报告错误失败: {resp.status_code}")
    except Exception as e:
        logger.warning(f"报告错误异常: {e}")


def process_file_embedding(params: dict):
    """
    处理文件嵌入的主逻辑（异步后台任务）

    Args:
        params: 包含 file_id, res_rag_id, task_id, rag_name, chunk_size,
                overlap_size, dimension_size, embedding_model_url,
                embedding_model_name, s3_key, user_id
    """
    file_id = params["file_id"]
    task_id = params["task_id"]
    rag_name = params["rag_name"]
    user_id = params["user_id"]
    s3_key = params["s3_key"]

    logger.info(
        f"[RAG Embed] 开始处理: file_id={file_id}, task_id={task_id}, rag={rag_name}"
    )
    local_path = None

    try:
        # 1. 下载文件
        today = datetime.now().strftime("%Y%m%d")
        local_dir = os.path.join(settings.DATA_DIR, "res", str(user_id), today)
        os.makedirs(local_dir, exist_ok=True)
        local_filename = os.path.basename(s3_key)
        if not local_filename:
            local_filename = f"file_{file_id}"
        local_path = os.path.join(local_dir, local_filename)

        logger.info(f"[RAG Embed] 下载 S3 文件: {s3_key} -> {local_path}")
        success = download_file_from_s3(s3_key, local_path)
        if not success:
            logger.error(f"[RAG Embed] S3 下载失败: {s3_key}")
            return
        logger.info(f"[RAG Embed] 文件下载完成: {local_path}")

        # 2. 读取文件
        text = ""
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError:
            try:
                with open(local_path, "r", encoding="gbk") as f:
                    text = f.read()
            except Exception as e:
                logger.error(f"[RAG Embed] 读取文件失败: {e}")
                return

        if not text.strip():
            logger.warning(f"[RAG Embed] 文件内容为空: {local_path}")
            return

        logger.info(f"[RAG Embed] 文件大小: {len(text)} 字符")

        # 3. 文本分块
        chunker = TextChunker(
            chunk_size=params.get("chunk_size", 500),
            overlap=params.get("overlap_size", 50),
        )
        chunks = chunker.split_text(text)
        if not chunks:
            logger.warning("[RAG Embed] 没有生成文本块")
            return
        logger.info(f"[RAG Embed] 分块完成: {len(chunks)} 块")

        # 4. 向量化
        embedder = EmbeddingService(
            api_url=params["embedding_model_url"],
            model_name=params["embedding_model_name"],
        )
        embeddings = []
        total_chunks = len(chunks)
        for i, chunk in enumerate(chunks):
            embedding = embedder.get_embedding(chunk)
            if embedding:
                embeddings.append(embedding)
            else:
                logger.warning(
                    f"[RAG Embed] 第 {i+1}/{total_chunks} 块向量化失败，跳过"
                )

            # 每处理 5 块或最后一块时报告进度
            # 注意：分块+向量化阶段最多只到 50%，写入 Milvus 成功后才报告 100%
            if (i + 1) % 5 == 0 or i == total_chunks - 1:
                progress = int((i + 1) / total_chunks * 50)
                report_progress(settings.BACKEND_BASE_URL, file_id, task_id, progress)

        if not embeddings:
            logger.error("[RAG Embed] 所有文本块向量化失败")
            return

        logger.info(f"[RAG Embed] 向量化完成: {len(embeddings)}/{total_chunks}")

        # 5. 写入 Milvus
        writer = MilvusWriter(host=settings.MILVUS_HOST, port=settings.MILVUS_PORT)
        client = writer.ensure_collection(
            collection_name=rag_name,
            dimension=params.get("dimension_size", 1024),
        )

        ids = [str(uuid.uuid4()) for _ in range(len(embeddings))]
        user_ids = [str(user_id)] * len(embeddings)
        text_chunks = chunks[: len(embeddings)]

        writer.insert_batch(client, rag_name, file_id, ids, user_ids, embeddings, text_chunks)

        # 6. 报告 100% 完成
        report_progress(settings.BACKEND_BASE_URL, file_id, task_id, 100)
        logger.info(f"[RAG Embed] 嵌入完成: file_id={file_id}, task_id={task_id}")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[RAG Embed] 处理异常: {error_msg}")
        # 报告失败给后端
        try:
            report_error(settings.BACKEND_BASE_URL, file_id, task_id, error_msg)
        except Exception as report_err:
            logger.error(f"[RAG Embed] 报告错误失败: {report_err}")

    finally:
        # 清理临时文件
        if local_path:
            try:
                os.remove(local_path)
                logger.debug(f"[RAG Embed] 临时文件已删除: {local_path}")
            except FileNotFoundError:
                pass
