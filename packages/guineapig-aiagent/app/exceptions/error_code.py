from enum import Enum


class ConstantCodeEnum(Enum):
    """类型枚举"""

    SERVER_ERROR = (500, "SERVER_ERROR", "服务器错误")

    def __init__(self, val, code, cn_name):
        self.val = val
        self.code = code
        self.cn_name = cn_name

    def __str__(self):
        return self.code
