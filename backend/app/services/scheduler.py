"""可选定时调度器（APScheduler）。

默认关闭，仅当 EMOERA_ENABLE_SCHEDULER=true 时由 lifespan 启动。
每天在 EMOERA_DAILY_TASK_HOUR:EMOERA_DAILY_TASK_MINUTE 触发一次每日任务。
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.services.task_runner import run_daily_tasks


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_daily_tasks,
        "cron",
        hour=settings.daily_task_hour,
        minute=settings.daily_task_minute,
        id="daily_tasks",
        replace_existing=True,
    )
    return scheduler
