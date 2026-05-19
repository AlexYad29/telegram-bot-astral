"""APScheduler-сборка авто-постинга в Telegram-канал.

Реэкспортируем фабрики и job, чтобы вызывающий код не знал о внутренней
структуре пакета (`scheduler.py` / `jobs.py` / `schedules.py`).
"""

from __future__ import annotations

from app.scheduler.jobs import BotProtocol, run_channel_post_job
from app.scheduler.scheduler import build_scheduler, register_channel_jobs
from app.scheduler.schedules import DEFAULT_SCHEDULE, CronSpec

__all__ = [
    "DEFAULT_SCHEDULE",
    "BotProtocol",
    "CronSpec",
    "build_scheduler",
    "register_channel_jobs",
    "run_channel_post_job",
]
