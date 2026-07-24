from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.core.log import logger
from app.services.memory_monitor_service import memory_monitor


class MemorySchedulerService:
    """内存监控定时任务调度器"""

    def __init__(self):
        self.scheduler = None
        self.is_running = False

    def start_memory_monitoring(self, interval_minutes: int = 1):
        """启动内存监控定时任务

        Args:
            interval_minutes: 监控间隔时间（分钟），默认5分钟
        """
        if self.is_running:
            logger.warning("内存监控定时任务已经在运行中")
            return

        try:
            # 创建后台调度器
            self.scheduler = BackgroundScheduler()

            # 添加定时任务
            trigger = IntervalTrigger(minutes=interval_minutes)
            self.scheduler.add_job(
                func=memory_monitor.log_memory_usage,
                trigger=trigger,
                id="memory_monitoring",
                name="内存使用情况监控",
                replace_existing=True,
            )

            # 启动调度器
            self.scheduler.start()
            self.is_running = True

            logger.info(f"内存监控定时任务已启动，每{interval_minutes}分钟执行一次")

        except Exception as e:
            logger.error(f"启动内存监控定时任务失败: {e}")
            self.is_running = False

    def stop_memory_monitoring(self):
        """停止内存监控定时任务"""
        if not self.is_running or not self.scheduler:
            logger.warning("内存监控定时任务未在运行")
            return

        try:
            self.scheduler.shutdown(wait=False)
            self.is_running = False
            logger.info("内存监控定时任务已停止")
        except Exception as e:
            logger.error(f"停止内存监控定时任务失败: {e}")

    def get_scheduler_status(self) -> dict:
        """获取调度器状态"""
        if not self.scheduler:
            return {"status": "not_started", "jobs": []}

        jobs_info = []
        for job in self.scheduler.get_jobs():
            jobs_info.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": (
                        str(job.next_run_time) if job.next_run_time else None
                    ),
                }
            )

        return {
            "status": "running" if self.is_running else "stopped",
            "jobs": jobs_info,
        }


# 全局实例
memory_scheduler = MemorySchedulerService()
