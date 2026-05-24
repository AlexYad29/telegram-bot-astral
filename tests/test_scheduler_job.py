"""Интеграционный тест job'а авто-постинга поверх SQLite + моков AI/bot."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import BigInteger, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles

from app.models.enums import PostKind, PostStatus
from app.models.generated_post import GeneratedPost
from app.scheduler.jobs import run_channel_post_job


# В production используется Postgres `BIGINT` + sequence. На SQLite автоинкремент
# работает только для `INTEGER PRIMARY KEY`, поэтому в тестах для диалекта
# `sqlite` рендерим BigInteger как INTEGER — без правок production-модели.
@compiles(BigInteger, "sqlite")  # type: ignore[misc]
def _bigint_to_integer_for_sqlite(element: object, compiler: object, **kw: object) -> str:
    return "INTEGER"


class _FakeSent:
    def __init__(self, message_id: int) -> None:
        self.message_id = message_id


class _FakeBot:
    """Мок aiogram-Bot — пишет аргументы и (опционально) кидает ошибку."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str | int, str]] = []

    async def send_message(self, chat_id: str | int, text: str) -> _FakeSent:
        self.calls.append((chat_id, text))
        if self.fail:
            raise RuntimeError("telegram down")
        return _FakeSent(message_id=777)


class _FakeAIService:
    """Минимальный мок `AIService.generate_channel_post`."""

    def __init__(self, *, reply: str = "пост", raise_exc: bool = False) -> None:
        self.reply = reply
        self.raise_exc = raise_exc
        self.calls: list[dict[str, object]] = []

    async def generate_channel_post(
        self,
        *,
        kind: PostKind,
        today: date,
        day_number: int | None = None,
    ) -> str:
        self.calls.append({"kind": kind, "today": today, "day_number": day_number})
        if self.raise_exc:
            raise RuntimeError("openai down")
        return self.reply


@pytest_asyncio.fixture
async def sessionmaker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """SQLite-in-memory только с таблицей `generated_posts`.

    Берём именно нужную таблицу из метаданных, чтобы не тащить JSONB-зависимые
    модели (`tarot_history`) — на SQLite их не скомпилировать.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(GeneratedPost.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_job_happy_path_persists_and_sends(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    ai = _FakeAIService(reply="звёздное сообщение")
    bot = _FakeBot()
    await run_channel_post_job(
        kind=PostKind.DAY_FORECAST,
        sessionmaker=sessionmaker,
        ai_service=ai,  # type: ignore[arg-type]
        bot=bot,
        channel_id="@astro",
        today=date(2026, 5, 18),
    )
    assert bot.calls == [("@astro", "звёздное сообщение")]
    async with sessionmaker() as session:
        rows = (await session.scalars(select(GeneratedPost))).all()
    assert len(rows) == 1
    post = rows[0]
    assert post.kind is PostKind.DAY_FORECAST
    assert post.status is PostStatus.SENT
    assert post.telegram_message_id == 777
    assert post.body == "звёздное сообщение"
    assert post.error is None


@pytest.mark.asyncio
async def test_job_day_number_passes_computed_day_number(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    ai = _FakeAIService(reply="семёрка")
    bot = _FakeBot()
    await run_channel_post_job(
        kind=PostKind.DAY_NUMBER,
        sessionmaker=sessionmaker,
        ai_service=ai,  # type: ignore[arg-type]
        bot=bot,
        channel_id="@astro",
        today=date(2026, 5, 18),  # → 6
    )
    assert ai.calls == [{
        "kind": PostKind.DAY_NUMBER,
        "today": date(2026, 5, 18),
        "day_number": 6,
    }]


@pytest.mark.asyncio
async def test_job_ai_failure_does_not_create_row(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    ai = _FakeAIService(raise_exc=True)
    bot = _FakeBot()
    await run_channel_post_job(
        kind=PostKind.DAY_FORECAST,
        sessionmaker=sessionmaker,
        ai_service=ai,  # type: ignore[arg-type]
        bot=bot,
        channel_id="@astro",
        today=date(2026, 5, 18),
    )
    assert bot.calls == []
    async with sessionmaker() as session:
        rows = (await session.scalars(select(GeneratedPost))).all()
    assert rows == []


@pytest.mark.asyncio
async def test_job_send_failure_marks_post_failed(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    ai = _FakeAIService(reply="звёзды")
    bot = _FakeBot(fail=True)
    await run_channel_post_job(
        kind=PostKind.DAY_FORECAST,
        sessionmaker=sessionmaker,
        ai_service=ai,  # type: ignore[arg-type]
        bot=bot,
        channel_id="@astro",
        today=date(2026, 5, 18),
    )
    async with sessionmaker() as session:
        rows = (await session.scalars(select(GeneratedPost))).all()
    assert len(rows) == 1
    post = rows[0]
    assert post.status is PostStatus.FAILED
    assert post.error is not None
    assert "telegram down" in post.error


@pytest.mark.asyncio
async def test_job_empty_ai_reply_skips_db_and_send(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    ai = _FakeAIService(reply="   ")
    bot = _FakeBot()
    await run_channel_post_job(
        kind=PostKind.DAY_ENERGY,
        sessionmaker=sessionmaker,
        ai_service=ai,  # type: ignore[arg-type]
        bot=bot,
        channel_id="@astro",
        today=date(2026, 5, 18),
    )
    assert bot.calls == []
    async with sessionmaker() as session:
        rows = (await session.scalars(select(GeneratedPost))).all()
    assert rows == []


@pytest.mark.asyncio
async def test_job_empty_channel_is_noop(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    ai = _FakeAIService()
    bot = _FakeBot()
    await run_channel_post_job(
        kind=PostKind.DAY_FORECAST,
        sessionmaker=sessionmaker,
        ai_service=ai,  # type: ignore[arg-type]
        bot=bot,
        channel_id="",
        today=date(2026, 5, 18),
    )
    assert ai.calls == []
    assert bot.calls == []
    async with sessionmaker() as session:
        rows = (await session.scalars(select(GeneratedPost))).all()
    assert rows == []
