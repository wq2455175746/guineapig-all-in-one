"""
LLM 流式请求/响应的 Pydantic 模型
"""

from pydantic import BaseModel
from typing import Optional


class SkillInfo(BaseModel):
    """用户已开启的 Skill 信息"""
    name: str
    description: str
    object_key: str  # S3 key: skills/{userId}/{date}/{name}.zip


class CommandItem(BaseModel):
    """LLM 返回的待执行命令"""
    type: str            # "shell" | "python" | "npx"
    description: str
    command: str
    cwd: Optional[str] = None
    risk: str            # "low" | "medium" | "high"


class RagContext(BaseModel):
    """RAG 知识库检索配置"""
    rag_names: list[str]                       # Milvus 集合名称列表
    embedding_api_url: str
    embedding_api_key: str
    embedding_model_name: str
    reranker_api_url: str
    reranker_api_key: str
    reranker_model_name: str
    top_k: int = 20                            # Milvus 检索数量
    rerank_top_k: int = 3                      # 重排后返回数量


class LLMStreamRequest(BaseModel):
    """LLM 流式请求参数"""
    messages: list[dict]                # 完整的消息上下文：[{"role":"system","content":"..."}, ...]
    model: Optional[str] = None         # 模型名称（来自 UserAiModel）
    api_key: Optional[str] = None       # API Key（后端解密后传入）
    base_url: Optional[str] = None      # API 地址（来自 UserAiModel）
    temperature: Optional[float] = 0.7  # 温度参数
    max_tokens: Optional[int] = 2048    # 最大 token 数
    stream: bool = True                 # 是否流式（固定为 True）
    skills: Optional[list[SkillInfo]] = None   # 用户已开启的 skills
    user_id: Optional[int] = None              # 用户 ID
    session_id: Optional[str] = ""             # 会话 ID（格式: conv_{conversation_id}）
    web_search_enabled: bool = False           # 是否开启联网搜索
    rag_context: Optional[RagContext] = None   # RAG 知识库检索配置
