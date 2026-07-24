import psutil
import os
from datetime import datetime
from app.core.log import logger

class MemoryMonitorService:
    """内存监控服务"""
    
    def __init__(self):
        self.process = psutil.Process(os.getpid())
    
    def get_memory_usage(self) -> dict:
        """获取当前进程的内存使用情况"""
        try:
            # 获取进程内存信息
            memory_info = self.process.memory_info()
            
            # 获取系统内存信息
            system_memory = psutil.virtual_memory()
            
            return {
                "timestamp": datetime.now().isoformat(),
                "process_memory_rss": memory_info.rss,  # 常驻内存大小 (bytes)
                "process_memory_vms": memory_info.vms,  # 虚拟内存大小 (bytes)
                "process_memory_percent": self.process.memory_percent(),  # 进程内存占用百分比
                "system_memory_total": system_memory.total,  # 系统总内存 (bytes)
                "system_memory_available": system_memory.available,  # 系统可用内存 (bytes)
                "system_memory_used": system_memory.used,  # 系统已用内存 (bytes)
                "system_memory_percent": system_memory.percent,  # 系统内存使用百分比
                "process_open_files": len(self.process.open_files()),  # 打开的文件数
                "process_threads": self.process.num_threads(),  # 线程数
            }
        except Exception as e:
            logger.error(f"获取内存使用信息失败: {e}")
            return {"error": str(e)}
    
    def format_memory_info(self, memory_info: dict) -> str:
        """格式化内存信息为可读字符串"""
        if "error" in memory_info:
            return f"内存监控错误: {memory_info['error']}"
        
        def bytes_to_mb(bytes_value):
            return round(bytes_value / (1024 * 1024), 2)
        
        return (
            f"内存使用报告 - {memory_info['timestamp']}\n"
            f"进程内存: RSS={bytes_to_mb(memory_info['process_memory_rss'])}MB, "
            f"VMS={bytes_to_mb(memory_info['process_memory_vms'])}MB, "
            f"占用率={memory_info['process_memory_percent']:.2f}%\n"
            f"系统内存: 总={bytes_to_mb(memory_info['system_memory_total'])}MB, "
            f"已用={bytes_to_mb(memory_info['system_memory_used'])}MB, "
            f"可用={bytes_to_mb(memory_info['system_memory_available'])}MB, "
            f"使用率={memory_info['system_memory_percent']:.1f}%\n"
            f"进程状态: 打开文件={memory_info['process_open_files']}, "
            f"线程数={memory_info['process_threads']}"
        )
    
    def log_memory_usage(self):
        """记录内存使用情况到日志"""
        memory_info = self.get_memory_usage()
        if "error" not in memory_info:
            formatted_info = self.format_memory_info(memory_info)
            logger.info(formatted_info)
        else:
            logger.error(f"内存监控失败: {memory_info['error']}")

# 全局实例
memory_monitor = MemoryMonitorService()