"""记忆归纳请求模型"""
from pydantic import BaseModel


class ModelInfo(BaseModel):
    api_key: str
    base_url: str
    model_name: str


class ConvBrief(BaseModel):
    id: int
    title: str
    created_at: str


class MsgBrief(BaseModel):
    conversation_id: int
    role: str
    content: str
    created_at: str


class ExistingMemoryBrief(BaseModel):
    """已有的记忆记录摘要（用于 AI 融合时参考）"""
    id: int
    name: str
    mem_type: str
    mem: str
    time_range_start_at: str | None = None
    time_range_end_at: str | None = None
    version: int = 1
    created_at: str


class MemorySummarizeRequest(BaseModel):
    memory_id: int
    memory_ids: dict[str, int]
    user_id: int
    model_info: ModelInfo
    conversations: list[ConvBrief]
    messages: list[MsgBrief]
    time_range_start: str
    time_range_end: str
    existing_memories: list[ExistingMemoryBrief] = []
