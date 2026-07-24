# app/schemas/asr_models.py

from pydantic import BaseModel


class AsrRequest(BaseModel):
    """ASR 请求模型"""
    objectKey: str


class AsrResponse(BaseModel):
    """ASR 响应模型"""
    text: str
