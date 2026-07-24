import os
import asyncio
from loguru import logger

# 移除默认的日志处理器
logger.remove()

# 从环境变量 PROJ_LOG_LEVEL 读取日志级别（如 DEBUG/INFO/WARNING），若未配置则默认 INFO；
# 将读取到的日志级别设置为 loguru 的全局级别，确保 loguru 遵循该级别过滤日志。
USER_DEFINED_LOG_LEVEL = os.getenv("PROJ_LOG_LEVEL", "INFO")
os.environ["LOGURU_LEVEL"] = USER_DEFINED_LOG_LEVEL


# 自定义上下文处理器来获取协程 id
def get_coroutine_id():
    try:
        # 获取当前正在运行的异步任务（协程任务）
        current_task = asyncio.current_task()
        if current_task:
            # 获取任务对应的协程对象
            return id(current_task.get_coro())
        return None
    except RuntimeError:
        return None


logger.configure(extra={"coroutine_id": get_coroutine_id})

# 配置生产环境日志，在logs文件夹下按天输出日志
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 日志轮转规则：每天 0 点自动新建一个日志文件，旧文件归档
# 日志保留规则：只保留最近 180 天的日志，过期自动删除
# 压缩规则：过期的日志文件会被压缩为 ZIP 格式，节省磁盘空间
# 日志级别过滤：只输出该级别及以上的日志（如 INFO 级别会过滤 DEBUG）
# 日志格式定义，最终每条日志示例
# 配置生产环境日志，在logs文件夹下按天输出日志
logger.add(
    os.path.join(log_dir, "log_{time:YYYY-MM-DD}.log"),
    rotation="00:00",
    retention="180 days",
    compression="zip",
    level=USER_DEFINED_LOG_LEVEL,
    # 格式精确到毫秒，添加线程名和协程id
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {thread.name} | {thread.id} | {extra[coroutine_id]} | {message}",
)

# 配置IDE控制台日志输出（适用于PyCharm/IDEA等开发环境）
# 使用更简洁的格式，便于在IDE控制台中查看
logger.add(
    lambda msg: print(msg, end=""),  # 直接输出到标准输出，避免额外的换行符
    level=USER_DEFINED_LOG_LEVEL,
    # IDE控制台专用格式：彩色显示，简化时间戳，突出级别信息
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{thread.name}</cyan> | <magenta>{extra[coroutine_id]}</magenta> | {message}",
    colorize=True,  # 启用颜色支持
    backtrace=False,  # 在控制台中不显示完整的回溯信息，保持简洁
    diagnose=False,  # 关闭诊断信息，减少控制台输出
)

# 定义模块的导出列表，确保其他模块通过 from xxx import * 时只导入配置好的 logger，避免导出无关变量。
__all__ = ["logger"]
