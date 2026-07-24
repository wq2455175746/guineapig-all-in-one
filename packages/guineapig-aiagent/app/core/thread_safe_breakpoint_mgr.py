import fcntl  # 用于文件锁定，避免并发问题
import json
import os
import threading
from datetime import datetime
from app.core.log import logger

# 线程安全的断点管理器类
class ThreadSafeBreakpointManager:
    def __init__(self, breakpoint_file_path, initial_data=None):
        self._breakpoint_file_path = breakpoint_file_path
        self._data = initial_data or {
            "completed_files": [],
            "delete_completed_files": [],
            "current_file": None,
            "current_file_position": 0,
            "total_processed": 0,
            "last_updated": None,
        }
        self._lock = threading.Lock()
        self._completed_files_lock = threading.Lock()
        self._delete_completed_files_lock = threading.Lock()

    def get_data(self):
        with self._lock:
            return self._data.copy()

    def update_position(self, file_path, position):
        with self._lock:
            if self._data["current_file"] == file_path:
                self._data["current_file_position"] = position
                self._data["last_updated"] = datetime.now().isoformat()
                return True
            return False

    def update_total_processed(self, count):
        with self._lock:
            self._data["total_processed"] += count
            self._data["last_updated"] = datetime.now().isoformat()
            return self._data["total_processed"]

    def add_completed_file(self, file_path):
        with self._completed_files_lock:
            if file_path not in self._data["completed_files"]:
                self._data["completed_files"].append(file_path)
                self._data["last_updated"] = datetime.now().isoformat()
                return True
            return False

    def get_completed_files(self):
        with self._completed_files_lock:
            return set(self._data["completed_files"])

    def get_total_processed(self):
        with self._lock:
            return self._data["total_processed"]

    def add_delete_completed_file(self, file_path):
        """添加已处理的删除文件"""
        with self._delete_completed_files_lock:
            if file_path not in self._data["delete_completed_files"]:
                self._data["delete_completed_files"].append(file_path)
                self._data["last_updated"] = datetime.now().isoformat()
                return True
            return False

    def get_delete_completed_files(self):
        """获取已处理的删除文件列表"""
        with self._delete_completed_files_lock:
            return set(self._data["delete_completed_files"])

    def is_delete_file_completed(self, file_path):
        """检查删除文件是否已经处理完成"""
        with self._delete_completed_files_lock:
            return file_path in self._data["delete_completed_files"]

    def get_breakpoint_data(self):
        with self._lock:
            return self._data.copy()

    def load(self):
        """加载断点数据"""
        if os.path.exists(self._breakpoint_file_path):
            try:
                with open(self._breakpoint_file_path, "r", encoding="utf-8") as f:
                    # 尝试锁定文件
                    try:
                        fcntl.flock(f, fcntl.LOCK_SH)  # 共享锁
                        breakpoint_data = json.load(f)
                        with self._lock:
                            self._data = breakpoint_data
                        logger.info(
                            f"加载断点信息成功，已处理 {len(breakpoint_data.get('completed_files', []))} 个文件"
                        )
                        return True
                    finally:
                        fcntl.flock(f, fcntl.LOCK_UN)  # 释放锁
            except Exception as e:
                logger.warning(f"加载断点信息失败: {e}，将从头开始处理")
        return False

    def save(self):
        """保存断点数据"""
        try:
            with self._lock:
                breakpoint_data = self._data.copy()

            # 更新最后修改时间
            breakpoint_data["last_updated"] = datetime.now().isoformat()

            with open(self._breakpoint_file_path, "w", encoding="utf-8") as f:
                # 尝试锁定文件
                try:
                    fcntl.flock(f, fcntl.LOCK_EX)  # 排他锁
                    json.dump(breakpoint_data, f, ensure_ascii=False, indent=2)
                    logger.debug(f"断点信息已更新到 {self._breakpoint_file_path}")
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)  # 释放锁
        except Exception as e:
            logger.error(f"保存断点信息失败: {e}")

    def clear(self):
        """清除断点信息"""
        if os.path.exists(self._breakpoint_file_path):
            try:
                os.remove(self._breakpoint_file_path)
                logger.info(f"断点信息已清除: {self._breakpoint_file_path}")
            except Exception as e:
                logger.warning(f"清除断点信息失败: {e}")
