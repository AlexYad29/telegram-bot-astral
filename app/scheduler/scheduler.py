"""Сборка APScheduler и регистрация задач канал-постинга."""

from __future__ import annotations

import logging
from functools import partial
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.scheduler.jobs import BotProtocol, run_channel_post_job
from app.scheduler.schedules import DEFAULT_SCHEDULE, CronSpec

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.config.settings import Settings
    from app.models.enums import PostKind
    from app.services.ai.service import AIService

logger = logging.getLogger(__name__)


def build_scheduler(settings: Settings) -> AsyncIOScheduler:
    """Создать `AsyncIOScheduler` с timezone из настроек.

    Запуск/остановку контролируем сами — `start()`/`shutdown()` дёргаются в
    lifecycle бота (`__main__.on_startup` / `on_shutdown`).
    """
    return AsyncIOScheduler(timezone=settings.timezone)


def register_channel_jobs(
    scheduler: AsyncIOScheduler,
    *,
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    ai_service: AIService,
    bot: BotProtocol,
    schedule: dict[PostKind, CronSpec] | None = None,
) -> list[str]:
    """Привязать job на каждый `PostKind` из `schedule` (или дефолтного).

    Возвращает список зарегистрированных `job_id` — удобно проверять в тестах.
    Если `channel_id` не задан в настройках — задачи не регистрируются,
    предупреждаем в лог (на dev-окружении без канала это нормально).
    """
    if not settings.channel_id:
        logger.warning("scheduler: channel_id is empty, no autopost jobs registered")
        return []

    table = schedule or DEFAULT_SCHEDULE
    job_ids: list[str] = []
    for kind, spec in table.items():
        job = scheduler.add_job(
            partial(
                run_channel_post_job,
                kind=kind,
                sessionmaker=sessionmaker,
                ai_service=ai_service,
                bot=bot,
                channel_id=settings.channel_id,
            ),
            trigger=CronTrigger(timezone=settings.timezone, **spec.as_dict()),
            id=f"channel:{kind.value}",
            replace_existing=True,
            misfire_grace_time=60 * 30,  # 30 минут на наверстать просроченный тик
            coalesce=True,
        )
        job_ids.append(job.id)
        logger.info(
            "scheduler: registered %s at %02d:%02d (%s)",
            job.id,
            spec.hour,
            spec.minute,
            spec.day_of_week,
        )
    return job_ids


__all__ = ["build_scheduler", "register_channel_jobs"]
