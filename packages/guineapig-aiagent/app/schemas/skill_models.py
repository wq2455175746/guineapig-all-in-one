"""Skill 处理的请求/响应模型"""

from pydantic import BaseModel, Field


class SkillProcessRequest(BaseModel):
    """Skill 解析请求"""
    objectKey: str = Field(..., description="S3 对象键，格式 skills/{user_id}/{date}/{skill-name}.zip")


class SkillProcessResult(BaseModel):
    """Skill 解析结果"""
    name: str = Field(..., description="Skill 名称")
    description: str = Field(..., description="Skill 描述")
    version: str = Field("1.0.0", description="版本号")
    file_stat: str = Field("{}", description="文件类型分析（JSON 字符串）")
    metadata: str = Field("{}", description="元数据（JSON 字符串）")
