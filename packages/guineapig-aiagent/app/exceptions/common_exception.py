from typing import Optional, Any

from app.exceptions.error_code import ConstantCodeEnum


class CommonException(Exception):
    """业务异常基类"""

    def __init__(
        self, code: int = 500, message: str = "error", data: Optional[Any] = None
    ):
        self.message = message
        self.code = code
        self.data = data

    @classmethod
    def throw_exception(
        cls, err_code_enum: ConstantCodeEnum, data: Optional[Any] = None
    ):
        return cls(err_code_enum.val, err_code_enum.cn_name, data)
