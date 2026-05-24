"""Smoke-тесты админ-хендлеров: проверяем форматирование ответов и
что команды управления планировщиком вызывают нужные методы.

Не дёргаем реальный aiogram dispatcher — собираем `aiogram.types.Message`-mock
и зовём хендлеры напрямую.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters import CommandObject

from app.handlers.admin import (
    cmd_admin,
    cmd_post_now,
    cmd_scheduler,
    cmd_scheduler_pause,
    cmd_scheduler_resume,
    cmd_stats,
)
from app.models.enums import PostKind, PostStatus
from app.services.admin_stats import AdminStats


@dataclass
class _FakeUser:
    id: int = 42


@dataclass
class _FakeMessage:
    text: str | None = None
    from_user: _FakeUser | None = field(default_factory=_FakeUser)
    answers: list[str] = field(default_factory=list)

    async def answer(self, text: str, **kwargs: Any) -> None:
        self.answers.append(text)


@dataclass
class _FakeSettings:
    channel_id: str | None = "@astro"


def _command(args: str | None = None, prefix: str = "/") -> CommandObject:
    return CommandObject(
        prefix=prefix, command="post_now", mention=None, args=args, regexp_match=None
    )


# ---------- /admin ----------

@pytest.mark.asyncio
async def test_cmd_admin_lists_commands() -> None:
    message = _FakeMessage()
    await cmd_admin(message)  # type: ignore[arg-type]
    assert len(message.answers) == 1
    text = message.answers[0]
    assert "/stats" in text
    assert "/post_now" in text
    assert "/scheduler" in text


# ---------- /stats ----------

@pytest.mark.asyncio
async def test_cmd_stats_calls_service(monkeypatch: pytest.MonkeyPatch) -> None:
    message = _FakeMessage()
    fake_stats = AdminStats(
        as_of=datetime(2026, 5, 18, 12, 0, tzinfo=UTC),
        users_total=1,
        users_with_profile=1,
        users_active_24h=1,
        users_active_7d=1,
        users_blocked=0,
        posts_by_status={PostStatus.SENT: 1},
        posts_by_kind_7d={PostKind.DAY_FORECAST: 1},
    )

    fake_service = MagicMock()
    fake_service.collect = AsyncMock(return_value=fake_stats)
    monkeypatch.setattr(
        "app.handlers.admin.AdminStatsService",
        lambda session: fake_service,
    )

    await cmd_stats(message, session=MagicMock())  # type: ignore[arg-type]
    assert len(message.answers) == 1
    assert "Статистика бота" in message.answers[0]


# ---------- /post_now ----------

@pytest.mark.asyncio
async def test_cmd_post_now_without_args_shows_help() -> None:
    message = _FakeMessage()
    await cmd_post_now(
        message,  # type: ignore[arg-type]
        command=_command(args=None),
        session=MagicMock(),
        ai_service=MagicMock(),
        bot=MagicMock(),
        settings=_FakeSettings(),  # type: ignore[arg-type]
    )
    assert any("Использование" in a for a in message.answers)


@pytest.mark.asyncio
async def test_cmd_post_now_unknown_kind() -> None:
    message = _FakeMessage()
    await cmd_post_now(
        message,  # type: ignore[arg-type]
        command=_command(args="unknown"),
        session=MagicMock(),
        ai_service=MagicMock(),
        bot=MagicMock(),
        settings=_FakeSettings(),  # type: ignore[arg-type]
    )
    assert any("Неизвестный тип поста" in a for a in message.answers)


@pytest.mark.asyncio
async def test_cmd_post_now_missing_channel() -> None:
    message = _FakeMessage()
    await cmd_post_now(
        message,  # type: ignore[arg-type]
        command=_command(args="forecast"),
        session=MagicMock(),
        ai_service=MagicMock(),
        bot=MagicMock(),
        settings=_FakeSettings(channel_id=None),  # type: ignore[arg-type]
    )
    assert any("CHANNEL_ID" in a for a in message.answers)


@pytest.mark.asyncio
async def test_cmd_post_now_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    message = _FakeMessage()
    fake_job = AsyncMock()
    monkeypatch.setattr("app.handlers.admin.run_channel_post_job", fake_job)
    monkeypatch.setattr(
        "app.database.session.get_sessionmaker", lambda: MagicMock()
    )

    await cmd_post_now(
        message,  # type: ignore[arg-type]
        command=_command(args="forecast"),
        session=MagicMock(),
        ai_service=MagicMock(),
        bot=MagicMock(),
        settings=_FakeSettings(),  # type: ignore[arg-type]
    )
    assert fake_job.await_count == 1
    kwargs = fake_job.call_args.kwargs
    assert kwargs["kind"] is PostKind.DAY_FORECAST
    assert kwargs["channel_id"] == "@astro"
    assert any("Готово" in a for a in message.answers)


@pytest.mark.asyncio
async def test_cmd_post_now_job_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    message = _FakeMessage()
    fake_job = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr("app.handlers.admin.run_channel_post_job", fake_job)
    monkeypatch.setattr(
        "app.database.session.get_sessionmaker", lambda: MagicMock()
    )

    await cmd_post_now(
        message,  # type: ignore[arg-type]
        command=_command(args="viral"),
        session=MagicMock(),
        ai_service=MagicMock(),
        bot=MagicMock(),
        settings=_FakeSettings(),  # type: ignore[arg-type]
    )
    assert any("Не получилось" in a for a in message.answers)


# ---------- /scheduler* ----------


def _scheduler_with_jobs(*, running: bool = True, jobs: list[Any] | None = None) -> Any:
    sched = MagicMock()
    sched.running = running
    sched.get_jobs.return_value = jobs or []
    return sched


@pytest.mark.asyncio
async def test_cmd_scheduler_stopped() -> None:
    message = _FakeMessage()
    sched = _scheduler_with_jobs(running=False)
    await cmd_scheduler(message, scheduler=sched)  # type: ignore[arg-type]
    assert any("остановлен" in a for a in message.answers)


@pytest.mark.asyncio
async def test_cmd_scheduler_empty() -> None:
    message = _FakeMessage()
    sched = _scheduler_with_jobs(running=True, jobs=[])
    await cmd_scheduler(message, scheduler=sched)  # type: ignore[arg-type]
    assert any("job'ов нет" in a for a in message.answers)


@pytest.mark.asyncio
async def test_cmd_scheduler_lists_jobs() -> None:
    message = _FakeMessage()
    job = MagicMock()
    job.id = "channel:day_forecast"
    job.next_run_time = datetime(2026, 5, 18, 9, 0, tzinfo=UTC)
    sched = _scheduler_with_jobs(running=True, jobs=[job])
    await cmd_scheduler(message, scheduler=sched)  # type: ignore[arg-type]
    assert any("channel:day_forecast" in a for a in message.answers)


@pytest.mark.asyncio
async def test_cmd_scheduler_pause() -> None:
    message = _FakeMessage()
    sched = _scheduler_with_jobs(running=True)
    await cmd_scheduler_pause(message, scheduler=sched)  # type: ignore[arg-type]
    sched.pause.assert_called_once()
    assert any("паузу" in a for a in message.answers)


@pytest.mark.asyncio
async def test_cmd_scheduler_pause_when_stopped() -> None:
    message = _FakeMessage()
    sched = _scheduler_with_jobs(running=False)
    await cmd_scheduler_pause(message, scheduler=sched)  # type: ignore[arg-type]
    sched.pause.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_scheduler_resume_when_running() -> None:
    message = _FakeMessage()
    sched = _scheduler_with_jobs(running=True)
    await cmd_scheduler_resume(message, scheduler=sched)  # type: ignore[arg-type]
    sched.resume.assert_called_once()
    sched.start.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_scheduler_resume_when_stopped() -> None:
    message = _FakeMessage()
    sched = _scheduler_with_jobs(running=False)
    await cmd_scheduler_resume(message, scheduler=sched)  # type: ignore[arg-type]
    sched.start.assert_called_once()
    sched.resume.assert_not_called()
