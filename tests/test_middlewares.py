"""Юнит-тесты middleware'ов без запуска реального aiogram / Telegram.

Используем `unittest.mock` для AsyncSession / Redis / handler.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Update

from app.middlewares.db_session import DbSessionMiddleware
from app.middlewares.logging import LoggingMiddleware
from app.middlewares.throttling import ThrottlingMiddleware
from app.middlewares.user_upsert import UserUpsertMiddleware

# ---------- DbSessionMiddleware ----------


def _make_session_factory() -> tuple[MagicMock, MagicMock]:
    """Сделать sessionmaker, который возвращает async-context-manager-сессию."""
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock(return_value=cm)
    return factory, session


@pytest.mark.asyncio
async def test_db_session_middleware_commits_on_success() -> None:
    factory, session = _make_session_factory()
    mw = DbSessionMiddleware(factory)

    async def handler(event, data):
        assert data["session"] is session
        return "ok"

    result = await mw(handler, MagicMock(spec=Update), {})

    assert result == "ok"
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_db_session_middleware_rolls_back_on_exception() -> None:
    factory, session = _make_session_factory()
    mw = DbSessionMiddleware(factory)

    async def handler(event, data):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await mw(handler, MagicMock(spec=Update), {})

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


# ---------- LoggingMiddleware ----------


@pytest.mark.asyncio
async def test_logging_middleware_passes_through() -> None:
    mw = LoggingMiddleware()
    handler = AsyncMock(return_value="ok")
    event = MagicMock(spec=Update)

    result = await mw(handler, event, {"event_from_user": None})

    assert result == "ok"
    handler.assert_awaited_once()


# ---------- ThrottlingMiddleware ----------


def _make_redis(cooldown_set_results: list[bool], incr_results: list[int]) -> MagicMock:
    """Сэмулировать Redis.

    `cooldown_set_results` — что вернёт `SET … NX` на каждый последовательный вызов
    с `nx=True` (True = ключа не было → ставим, False = уже был → троттлим).
    `incr_results` — что вернёт `INCR` на minute-bucket.
    """
    redis = MagicMock()
    cooldown_iter = iter(cooldown_set_results)

    async def fake_set(_key, _value, *, px=None, ex=None, nx=False):
        if nx and px is not None:
            return next(cooldown_iter)
        # notify_key (ex=5, nx=True) — возвращаем True (первый раз), чтобы дойти до notify
        return True

    incr_iter = iter(incr_results)

    async def fake_incr(_key):
        return next(incr_iter)

    redis.set = fake_set
    redis.incr = fake_incr
    redis.expire = AsyncMock()
    return redis


@pytest.mark.asyncio
async def test_throttling_allows_first_event() -> None:
    redis = _make_redis(cooldown_set_results=[True], incr_results=[1])
    mw = ThrottlingMiddleware(redis, default_rate=0.5, max_per_minute=20)

    user = MagicMock(id=42, is_bot=False)
    handler = AsyncMock(return_value="ok")
    event = MagicMock(spec=Update)

    result = await mw(handler, event, {"event_from_user": user})

    assert result == "ok"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_throttling_blocks_when_cooldown_active() -> None:
    redis = _make_redis(cooldown_set_results=[False], incr_results=[])
    mw = ThrottlingMiddleware(redis, default_rate=0.5, max_per_minute=20)

    user = MagicMock(id=42, is_bot=False)
    handler = AsyncMock(return_value="ok")
    event = MagicMock(spec=Update)
    # Не Message и не CallbackQuery → notify тихо упадёт в suppress, это ок.
    result = await mw(handler, event, {"event_from_user": user})

    assert result is None
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_throttling_blocks_when_minute_quota_exceeded() -> None:
    redis = _make_redis(cooldown_set_results=[True], incr_results=[25])
    mw = ThrottlingMiddleware(redis, default_rate=0.5, max_per_minute=20)

    user = MagicMock(id=42, is_bot=False)
    handler = AsyncMock(return_value="ok")
    event = MagicMock(spec=Update)

    result = await mw(handler, event, {"event_from_user": user})

    assert result is None
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_throttling_skips_when_no_user() -> None:
    redis = _make_redis(cooldown_set_results=[], incr_results=[])
    mw = ThrottlingMiddleware(redis, default_rate=0.5, max_per_minute=20)
    handler = AsyncMock(return_value="ok")
    event = MagicMock(spec=Update)

    result = await mw(handler, event, {"event_from_user": None})

    assert result == "ok"
    handler.assert_awaited_once()


def test_throttling_rejects_bad_config() -> None:
    redis = MagicMock()
    with pytest.raises(ValueError):
        ThrottlingMiddleware(redis, default_rate=0, max_per_minute=10)
    with pytest.raises(ValueError):
        ThrottlingMiddleware(redis, default_rate=1, max_per_minute=0)


# ---------- UserUpsertMiddleware ----------


@pytest.mark.asyncio
async def test_user_upsert_skips_without_session() -> None:
    mw = UserUpsertMiddleware()
    handler = AsyncMock(return_value="ok")
    event = MagicMock(spec=Update)
    tg_user = MagicMock(id=1, is_bot=False)

    result = await mw(handler, event, {"event_from_user": tg_user, "session": None})

    assert result == "ok"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_upsert_skips_for_bots() -> None:
    mw = UserUpsertMiddleware()
    handler = AsyncMock(return_value="ok")
    event = MagicMock(spec=Update)
    tg_user = MagicMock(id=1, is_bot=True)
    session = MagicMock()

    result = await mw(handler, event, {"event_from_user": tg_user, "session": session})

    assert result == "ok"
    handler.assert_awaited_once()
