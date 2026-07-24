from typing import Generic, TypeVar, Optional, Any

from fastapi import status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.log import logger

# 泛型类型，支持动态指定data的类型
T = TypeVar("T")

class BaseResponse(BaseModel, Generic[T]):
    """全局统一返回结构"""
    success: bool = Field(..., description="请求是否成功")
    errCode: int = Field(..., description="状态码")
    errMessage: str = Field(..., description="错误信息")
    result: Optional[T] = Field(None, description="数据")

def success_response(message: str = "success", code: int = 0, data: Optional[Any] = None) -> JSONResponse:
    logger.debug(f"success：code={code}, message={message}")
    """成功响应工具函数"""
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=BaseResponse(
            success=True,
            errCode=code,
            errMessage=message,
            result=data
        ).model_dump()
    )

def error_response(message: str, code: int = 500, data: Optional[Any] = None) -> JSONResponse:
    """错误响应工具函数"""
    # 记录错误日志（生产环境建议完善日志配置）
    logger.debug(f"error：code={code}, message={message}")
    
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=BaseResponse(
            success=False,
            errCode=code,
            errMessage=message,
            result=data
        ).model_dump()
    )
