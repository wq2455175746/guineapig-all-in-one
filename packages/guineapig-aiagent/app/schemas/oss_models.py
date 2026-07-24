from dataclasses import dataclass
from datetime import datetime
from pydantic import BaseModel

@dataclass
class S3ObjectInfo(BaseModel):
    """S3对象信息数据类"""
    key: str
    size: int
    last_modified: datetime
    etag: str