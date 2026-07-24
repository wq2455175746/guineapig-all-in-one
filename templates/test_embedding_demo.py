import os
import uuid
import glob
import logging
import traceback
import time
from typing import List, Dict, Optional
import requests
import numpy as np
from pymilvus import (
    connections,
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
    utility,
)

# ==================== 日志配置 ====================
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# 同时输出到控制台和文件
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

file_handler = logging.FileHandler("debug.log")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)
logger.addHandler(file_handler)

# ==================== 配置信息 ====================
MILVUS_HOST = "localhost"
MILVUS_PORT = "19530"
COLLECTION_NAME = "rag_user_resdata_test"
VECTOR_DIM = 1024
USER_ID = "1000"

OLLAMA_URL = "http://8.130.65.55:11434/api/embeddings"
EMBEDDING_MODEL = "qwen3-embedding:0.6b"

FILE_PATH = "./documents"  # 修改为你的文件路径
SUPPORTED_EXTENSIONS = [".txt", ".md"]


# ==================== 1. 文本分块工具（修复版） ====================
class TextChunker:
    """简单的文本分块工具 - 修复死循环问题"""

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap
        logger.info(f"初始化TextChunker: chunk_size={chunk_size}, overlap={overlap}")

    def split_text(self, text: str) -> List[str]:
        """将长文本切分成多个块 - 安全版本"""
        logger.info(f"开始分块，文本长度: {len(text)}")

        if not text or len(text.strip()) == 0:
            logger.warning("文本为空，跳过分块")
            return []

        if len(text) <= self.chunk_size:
            logger.info(f"文本长度 {len(text)} <= 块大小 {self.chunk_size}，不进行分块")
            return [text]

        chunks = []
        start = 0
        chunk_count = 0
        max_iterations = len(text) // max(1, self.chunk_size - self.overlap) + 10
        iteration = 0

        logger.debug(f"最大迭代次数: {max_iterations}")

        while start < len(text) and iteration < max_iterations:
            iteration += 1

            # 计算结束位置
            end = min(start + self.chunk_size, len(text))

            # 尝试在句子边界处切割
            if end < len(text):
                found_sep = False
                # 查找分隔符
                for sep in ["。", "！", "？", "\n", ".", "!", "?", ";", "；"]:
                    last_sep = text.rfind(sep, start, end)
                    if last_sep != -1 and last_sep > start + self.chunk_size // 2:
                        end = last_sep + 1
                        found_sep = True
                        break

                # 如果没有找到合适的分隔符，强制在chunk_size处切割
                if not found_sep:
                    # 确保end > start
                    if end <= start:
                        end = min(start + self.chunk_size, len(text))
                    if end <= start:
                        end = start + 1

            # 确保end大于start
            if end <= start:
                end = min(start + 1, len(text))
                logger.warning(f"  调整end: start={start}, end={end}")

            # 提取文本块
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(chunk_text)
                chunk_count += 1
                logger.debug(
                    f"  生成块 {chunk_count}: 位置 {start}-{end}, 长度={len(chunk_text)}"
                )
            else:
                logger.warning(f"  块 {chunk_count+1} 为空，跳过")

            # 更新start位置
            new_start = end - self.overlap

            # 确保start在前进，避免死循环
            if new_start <= start:
                new_start = start + 1
                logger.warning(f"  检测到start未前进，强制前进到 {new_start}")

            start = new_start

            # 如果剩余文本太少，直接添加到最后一个块
            if len(text) - start < self.chunk_size // 2 and len(text) - start > 0:
                remaining = text[start:].strip()
                if remaining:
                    chunks.append(remaining)
                    chunk_count += 1
                    logger.debug(
                        f"  生成最后块 {chunk_count}: 位置 {start}-{len(text)}, 长度={len(remaining)}"
                    )
                break

            # 进度日志
            if iteration % 100 == 0:
                logger.debug(
                    f"  分块进度: {start}/{len(text)} ({start/len(text)*100:.1f}%)"
                )

        if iteration >= max_iterations:
            logger.error(f"达到最大迭代次数 {max_iterations}，强制结束")

        logger.info(f"分块完成，共生成 {chunk_count} 个块")
        return chunks


# ==================== 2. 文件读取器 ====================
class FileReader:
    """读取各种格式的文件"""

    @staticmethod
    def read_text_file(file_path: str) -> str:
        """读取文本文件"""
        logger.info(f"读取文本文件: {file_path}")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                logger.info(f"成功读取文件，长度: {len(content)} 字符")
                return content
        except UnicodeDecodeError as e:
            logger.warning(f"UTF-8解码失败，尝试GBK编码: {e}")
            try:
                with open(file_path, "r", encoding="gbk") as f:
                    content = f.read()
                    logger.info(f"成功读取文件(GBK)，长度: {len(content)} 字符")
                    return content
            except Exception as e2:
                logger.error(f"GBK编码也失败: {e2}")
                raise
        except Exception as e:
            logger.error(f"读取文件失败: {e}")
            logger.debug(traceback.format_exc())
            raise

    @staticmethod
    def read_file(file_path: str) -> str:
        """根据文件扩展名读取文件"""
        ext = os.path.splitext(file_path)[1].lower()
        logger.info(f"读取文件: {os.path.basename(file_path)} (扩展名: {ext})")

        try:
            if ext in [".txt", ".md", ".py", ".json"]:
                return FileReader.read_text_file(file_path)
            else:
                logger.warning(f"未知文件类型 {ext}，尝试作为文本文件处理")
                return FileReader.read_text_file(file_path)
        except Exception as e:
            logger.error(f"读取文件失败: {e}")
            logger.debug(traceback.format_exc())
            raise


# ==================== 3. 向量化服务 ====================
class EmbeddingService:
    """调用Ollama获取文本向量"""

    def __init__(self, ollama_url: str, model: str):
        self.ollama_url = ollama_url
        self.model = model
        self.timeout = 30
        logger.info(f"初始化EmbeddingService: {ollama_url}, model={model}")

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """获取单个文本的向量"""
        if not text or len(text.strip()) == 0:
            logger.warning("文本为空，跳过向量化")
            return None

        try:
            logger.debug(f"向量化文本，长度: {len(text)}")
            response = requests.post(
                self.ollama_url,
                json={"model": self.model, "prompt": text},
                timeout=self.timeout,
            )

            if response.status_code == 200:
                result = response.json()
                embedding = result.get("embedding")
                if embedding:
                    logger.debug(f"向量化成功，维度: {len(embedding)}")
                    return embedding
                else:
                    logger.error("响应中没有embedding字段")
                    return None
            else:
                logger.error(f"请求失败: {response.status_code}")
                logger.error(f"响应: {response.text[:200]}")
                return None

        except Exception as e:
            logger.error(f"向量化失败: {e}")
            logger.debug(traceback.format_exc())
            return None

    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """批量获取多个文本的向量"""
        if not texts:
            logger.warning("没有文本需要向量化")
            return []

        logger.info(f"开始批量向量化，共 {len(texts)} 个文本块")

        embeddings = []
        failed_count = 0

        for i, text in enumerate(texts):
            logger.info(f"  向量化进度: {i+1}/{len(texts)}")

            embedding = self.get_embedding(text)
            if embedding is not None:
                embeddings.append(embedding)
            else:
                failed_count += 1
                logger.warning(f"  第 {i+1} 个文本向量化失败，使用随机向量")
                embeddings.append(np.random.rand(VECTOR_DIM).tolist())

        logger.info(f"批量向量化完成: 成功 {len(embeddings)-failed_count}/{len(texts)}")
        return embeddings


# ==================== 4. Milvus操作 ====================
class MilvusManager:
    """管理Milvus集合的创建和数据插入"""

    def __init__(self, host: str, port: str):
        self.host = host
        self.port = port
        self.collection = None
        logger.info(f"初始化MilvusManager: {host}:{port}")

    def connect(self):
        """连接到Milvus"""
        try:
            connections.connect(alias="default", host=self.host, port=self.port)
            logger.info(f"✅ 已连接到Milvus: {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"❌ 连接Milvus失败: {e}")
            logger.debug(traceback.format_exc())
            raise

    def create_collection(self, collection_name: str, vector_dim: int):
        """创建集合（如果不存在）"""
        logger.info(f"检查集合 {collection_name} 是否存在...")

        if utility.has_collection(collection_name):
            logger.info(f"⚠️  集合 {collection_name} 已存在，将使用现有集合")
            self.collection = Collection(collection_name)
            return

        logger.info(f"创建新集合: {collection_name}")

        fields = [
            FieldSchema(
                name="id", dtype=DataType.VARCHAR, max_length=36, is_primary=True
            ),
            FieldSchema(
                name="user_id",
                dtype=DataType.VARCHAR,
                max_length=64,
                is_partition_key=True,
            ),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=vector_dim),
            FieldSchema(name="text_chunk", dtype=DataType.VARCHAR, max_length=65535),
        ]

        schema = CollectionSchema(fields=fields, description="用户RAG文档集合")
        self.collection = Collection(name=collection_name, schema=schema)

        index_params = {
            "metric_type": "IP",
            "index_type": "IVF_FLAT",
            "params": {"nlist": 128},
        }
        self.collection.create_index(field_name="embedding", index_params=index_params)

        logger.info(f"✅ 集合 {collection_name} 创建成功")

    def insert_data(self, data: Dict):
        """插入数据到Milvus"""
        if not self.collection:
            raise Exception("集合未初始化")

        logger.info(f"准备插入数据，共 {len(data['ids'])} 条")
        self.collection.load()

        insert_data = [
            data["ids"],
            data["user_ids"],
            data["embeddings"],
            data["text_chunks"],
        ]

        try:
            result = self.collection.insert(insert_data)
            self.collection.flush()
            logger.info(f"✅ 成功插入 {len(data['ids'])} 条数据")
            return result
        except Exception as e:
            logger.error(f"❌ 插入数据失败: {e}")
            logger.debug(traceback.format_exc())
            raise


# ==================== 5. 主流程 ====================
def process_files(
    file_path: str, chunker: TextChunker, embedding_service: EmbeddingService
):
    """处理文件并生成向量数据"""
    logger.info("=" * 60)
    logger.info("开始处理文件...")
    logger.info("=" * 60)

    all_chunks = []
    file_count = 0

    # 判断是文件还是目录
    if os.path.isfile(file_path):
        logger.info(f"处理单个文件: {file_path}")
        files = [file_path]
    elif os.path.isdir(file_path):
        logger.info(f"处理目录: {file_path}")
        files = []
        for ext in SUPPORTED_EXTENSIONS:
            pattern = os.path.join(file_path, f"**/*{ext}")
            found = glob.glob(pattern, recursive=True)
            if found:
                logger.info(f"找到 {len(found)} 个 {ext} 文件")
                files.extend(found)
    else:
        raise ValueError(f"路径不存在: {file_path}")

    if not files:
        logger.warning(f"⚠️  未找到任何支持的文件")
        return None

    logger.info(f"📁 找到 {len(files)} 个文件")

    # 读取并分块
    for i, file in enumerate(files):
        try:
            logger.info(f"\n📄 [{i+1}/{len(files)}] 正在处理: {os.path.basename(file)}")

            text = FileReader.read_file(file)

            if not text or not text.strip():
                logger.warning(f"   ⚠️  文件为空，跳过")
                continue

            logger.info(f"   📝 文件大小: {len(text)} 字符")

            chunks = chunker.split_text(text)
            if chunks:
                all_chunks.extend(chunks)
                file_count += 1
                logger.info(f"   ✅ 分成 {len(chunks)} 个文本块")
            else:
                logger.warning(f"   ⚠️  没有生成任何文本块")

        except Exception as e:
            logger.error(f"   ❌ 处理文件失败: {e}")
            logger.debug(traceback.format_exc())
            continue

    if not all_chunks:
        logger.error("❌ 没有提取到任何文本内容")
        return None

    logger.info(f"\n📊 文件处理统计:")
    logger.info(f"   - 总文件数: {len(files)}")
    logger.info(f"   - 成功处理: {file_count}")
    logger.info(f"   - 文本块总数: {len(all_chunks)}")

    # 向量化
    logger.info(f"\n🔄 开始向量化 {len(all_chunks)} 个文本块...")
    embeddings = embedding_service.get_embeddings_batch(all_chunks)

    if not embeddings:
        logger.error("❌ 向量化失败，没有生成任何向量")
        return None

    # 准备Milvus数据
    ids = [str(uuid.uuid4()) for _ in range(len(embeddings))]
    user_ids = [USER_ID] * len(embeddings)

    data = {
        "ids": ids,
        "user_ids": user_ids,
        "embeddings": embeddings,
        "text_chunks": all_chunks[: len(embeddings)],
    }

    logger.info(f"\n✅ 数据准备完成:")
    logger.info(f"   - 成功处理文件数: {file_count}")
    logger.info(f"   - 文本块数: {len(embeddings)}")
    logger.info(f"   - 用户ID: {USER_ID}")
    logger.info(f"   - 向量维度: {len(embeddings[0]) if embeddings else 0}")

    return data


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("🚀 RAG文档向量化入库工具 - 修复版")
    logger.info("=" * 60)

    # 1. 初始化组件
    try:
        chunker = TextChunker(chunk_size=500, overlap=50)
        embedding_service = EmbeddingService(OLLAMA_URL, EMBEDDING_MODEL)
        milvus_manager = MilvusManager(MILVUS_HOST, MILVUS_PORT)
    except Exception as e:
        logger.error(f"❌ 初始化组件失败: {e}")
        logger.debug(traceback.format_exc())
        return

    # 2. 连接Milvus
    try:
        milvus_manager.connect()
    except Exception as e:
        logger.error(f"❌ 连接Milvus失败: {e}")
        return

    # 3. 创建集合
    try:
        milvus_manager.create_collection(COLLECTION_NAME, VECTOR_DIM)
    except Exception as e:
        logger.error(f"❌ 创建集合失败: {e}")
        return

    # 4. 处理文件
    try:
        data = process_files(FILE_PATH, chunker, embedding_service)
        if not data:
            logger.error("❌ 数据处理失败，退出")
            return
    except Exception as e:
        logger.error(f"❌ 处理文件失败: {e}")
        logger.debug(traceback.format_exc())
        return

    # 5. 插入数据
    try:
        milvus_manager.insert_data(data)
    except Exception as e:
        logger.error(f"❌ 插入数据失败: {e}")
        return

    logger.info("\n" + "=" * 60)
    logger.info("🎉 所有操作完成！")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
