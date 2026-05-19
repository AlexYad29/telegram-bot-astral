"""Тесты планировщика: сборка APScheduler и регистрация cron-задач."""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.config.settings import Settings
from app.models.enums import PostKind
from app.scheduler import build_scheduler, register_channel_jobs
from app.scheduler.jobs import _day_number_for
from app.scheduler.schedules import DEFAULT_SCHEDULE, CronSpec


def _settings(channel_id: str | None) -> Settings:
    return Settings(  # type: ignore[call-arg]
        bot_token="123:abc",
        openai_api_key="sk-test",
        channel_id=channel_id,
        timezone="Europe/Moscow",
    )


def test_build_scheduler_uses_settings_timezone() -> None:
    scheduler = build_scheduler(_settings("@channel"))
    # AsyncIOScheduler хранит tzinfo на уровне ._timezone, доступного через timezone.
    # Сравниваем через str — pytz/ZoneInfo дают разные классы.
    assert "Europe/Moscow" in str(scheduler.timezone)


def test_register_jobs_skips_when_channel_missing() -> None:
    scheduler = build_scheduler(_settings(None))
    job_ids = register_channel_jobs(
        scheduler,
        settings=_settings(None),
        sessionmaker=AsyncMock(),  # type: ignore[arg-type]
        ai_service=AsyncMock(),
        bot=AsyncMock(),
    )
    assert job_ids == []
    assert scheduler.get_jobs() == []


def test_register_jobs_registers_every_post_kind() -> None:
    settings = _settings("@astrochannel")
    scheduler = build_scheduler(settings)
    job_ids = register_channel_jobs(
        scheduler,
        settings=settings,
        sessionmaker=AsyncMock(),  # type: ignore[arg-type]
        ai_service=AsyncMock(),
        bot=AsyncMock(),
    )
    assert set(job_ids) == {f"channel:{k.value}" for k in DEFAULT_SCHEDULE}
    jobs = {j.id: j for j in scheduler.get_jobs()}
    assert set(jobs) == set(job_ids)


def test_register_jobs_custom_schedule() -> None:
    settings = _settings("@astrochannel")
    scheduler = build_scheduler(settings)
    custom = {PostKind.DAY_FORECAST: CronSpec(hour=7, minute=15)}
    job_ids = register_channel_jobs(
        scheduler,
        settings=settings,
        sessionmaker=AsyncMock(),  # type: ignore[arg-type]
        ai_service=AsyncMock(),
        bot=AsyncMock(),
        schedule=custom,
    )
    assert job_ids == ["channel:day_forecast"]


def test_cron_spec_as_dict_is_apscheduler_compatible() -> None:
    spec = CronSpec(hour=9, minute=0, day_of_week="mon,tue")
    payload: dict[str, Any] = spec.as_dict()
    assert payload == {"hour": 9, "minute": 0, "day_of_week": "mon,tue"}


def test_day_number_for_uses_numerology() -> None:
    # 2026-05-18 → 2+0+2+6+0+5+1+8 = 24 → 6.
    assert _day_number_for(date(2026, 5, 18)) == 6
    # 2022-11-29 → 2+0+2+2+1+1+2+9 = 19 → 10 → 1.
    assert _day_number_for(date(2022, 11, 29)) == 1
    # 1990-01-01 → 1+9+9+0+0+1+0+1 = 21 → 3.
    assert _day_number_for(date(1990, 1, 1)) == 3


@pytest.mark.asyncio
async def test_register_jobs_passes_channel_id_via_partial() -> None:
    """`partial` подставляет channel_id в job — проверяем через `args`/`kwargs`."""
    settings = _settings("@x")
    scheduler = build_scheduler(settings)
    register_channel_jobs(
        scheduler,
        settings=settings,
        sessionmaker=AsyncMock(),  # type: ignore[arg-type]
        ai_service=AsyncMock(),
        bot=AsyncMock(),
    )
    job = scheduler.get_job("channel:day_forecast")
    assert job is not None
    # APScheduler оборачивает callable; partial хранится в .func.
    func = job.func
    assert getattr(func, "keywords", None) is not None
    assert func.keywords["channel_id"] == "@x"
    assert func.keywords["kind"] is PostKind.DAY_FORECAST
