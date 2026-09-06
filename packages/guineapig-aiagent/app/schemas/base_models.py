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


# 业务错误码 → HTTP 状态码映射
_ERROR_STATUS_MAP = {
    400: status.HTTP_400_BAD_REQUEST,
    401: status.HTTP_401_UNAUTHORIZED,
    403: status.HTTP_403_FORBIDDEN,
    404: status.HTTP_404_NOT_FOUND,
    422: status.HTTP_422_UNPROCESSABLE_CONTENT,
    500: status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def _error_status(code: int) -> int:
    """将业务错误码映射到 HTTP 状态码；未识别的错误码统一返回 400。"""
    return _ERROR_STATUS_MAP.get(code, status.HTTP_400_BAD_REQUEST)


def error_response(message: str, code: int = 500, data: Optional[Any] = None) -> JSONResponse:
    """错误响应工具函数"""
    # 记录错误日志（生产环境建议完善日志配置）
    logger.debug(f"error：code={code}, message={message}")

    return JSONResponse(
        status_code=_error_status(code),
        content=BaseResponse(
            success=False,
            errCode=code,
            errMessage=message,
            result=data
        ).model_dump()
    )
