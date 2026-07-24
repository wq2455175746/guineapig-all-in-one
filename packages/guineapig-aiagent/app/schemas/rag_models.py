"""RAG 嵌入请求/响应模型"""

from pydantic import BaseModel, Field


class RagDeleteEmbeddingsRequest(BaseModel):
    """RAG 删除嵌入请求"""
    file_id: int = Field(..., description="文件 ID")
    rag_name: str = Field(..., description="知识库名称（Milvus 集合名称）")


class RagEmbedRequest(BaseModel):
    """RAG 文件嵌入请求"""
    file_id: int = Field(..., description="文件 ID")
    res_rag_id: int = Field(..., description="知识库 ID")
    task_id: str = Field(..., description="任务 ID")
    rag_name: str = Field(..., description="知识库名称")
    chunk_size: int = Field(500, description="分段大小")
    overlap_size: int = Field(50, description="重叠大小")
    dimension_size: int = Field(1024, description="向量维度")
    embedding_model_url: str = Field(..., description="嵌入模型 URL")
    embedding_model_name: str = Field(..., description="嵌入模型名称")
    s3_key: str = Field(..., description="S3 对象键")
    user_id: int = Field(..., description="用户 ID")


class RagEmbedResponse(BaseModel):
    """RAG 嵌入响应"""
    task_id: str = Field(..., description="任务 ID")
    message: str = Field("embedding started", description="响应消息")
