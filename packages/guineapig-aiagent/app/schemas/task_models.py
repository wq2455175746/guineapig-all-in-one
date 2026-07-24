# app/schemas/task_models.py

from typing import Optional

from pydantic import BaseModel


class TaskSubmitRequest(BaseModel):
    """提交任务请求模型"""
    sessionId: str
    taskId: str
    requestId: str
    its: int
    objectKey: str


class TaskSubmitResponse(BaseModel):
    """提交任务响应模型"""
    sessionId: str
    taskId: str
    requestId: str
    its: int
    objectKey: Optional[str] = None