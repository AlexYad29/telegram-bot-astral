"""Тесты `AdminStatsService` и `format_admin_stats`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import BigInteger
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles

from app.models.enums import Gender, PostKind, PostStatus
from app.models.generated_post import GeneratedPost
from app.models.user import User
from app.services.admin_stats import (
    AdminStats,
    AdminStatsService,
    format_admin_stats,
)


# Те же причины, что и в test_scheduler_job: SQLite не умеет автоинкремент
# на BIGINT. Преобразуем BigInteger → INTEGER для диалекта sqlite.
@compiles(BigInteger, "sqlite")  # type: ignore[misc]
def _bigint_to_integer_for_sqlite(element: object, compiler: object, **kw: object) -> str:
    return "INTEGER"


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
        await conn.run_sync(GeneratedPost.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_collect_empty_state(session: AsyncSession) -> None:
    stats = await AdminStatsService(session).collect()
    assert stats.users_total == 0
    assert stats.users_with_profile == 0
    assert stats.users_active_24h == 0
    assert stats.users_active_7d == 0
    assert stats.users_blocked == 0
    assert stats.posts_by_status == {}
    assert stats.posts_by_kind_7d == {}


@pytest.mark.asyncio
async def test_collect_counts_users(session: AsyncSession) -> None:
    now = datetime.now(tz=UTC)
    # 4 пользователя:
    #   1: только зарегистрирован, без профиля, активен сейчас
    #   2: с профилем, активен 2 дня назад
    #   3: с профилем, активен 10 дней назад
    #   4: заблокировал бота
    session.add_all(
        [
            User(
                id=1,
                last_active_at=now,
            ),
            User(
                id=2,
                full_name="Анна",
                birth_date=datetime(1990, 1, 1).date(),
                gender=Gender.FEMALE,
                last_active_at=now - timedelta(days=2),
            ),
            User(
                id=3,
                full_name="Борис",
                birth_date=datetime(1980, 5, 5).date(),
                gender=Gender.MALE,
                last_active_at=now - timedelta(days=10),
            ),
            User(
                id=4,
                is_blocked=True,
                last_active_at=now - timedelta(hours=2),
            ),
        ]
    )
    await session.commit()

    stats = await AdminStatsService(session).collect()
    assert stats.users_total == 4
    assert stats.users_with_profile == 2
    assert stats.users_blocked == 1
    # active_24h: пользователь 1 (сейчас) + пользователь 4 (минута назад)
    assert stats.users_active_24h == 2
    # active_7d: 1, 2, 4 (10 дней назад — за границей)
    assert stats.users_active_7d == 3


@pytest.mark.asyncio
async def test_collect_counts_posts(session: AsyncSession) -> None:
    now = datetime.now(tz=UTC)
    session.add_all(
        [
            GeneratedPost(
                kind=PostKind.DAY_FORECAST,
                body="a",
                channel_id="@c",
                scheduled_for=now,
                status=PostStatus.SENT,
            ),
            GeneratedPost(
                kind=PostKind.DAY_FORECAST,
                body="b",
                channel_id="@c",
                scheduled_for=now - timedelta(days=3),
                status=PostStatus.SENT,
            ),
            GeneratedPost(
                kind=PostKind.DAY_NUMBER,
                body="c",
                channel_id="@c",
                scheduled_for=now - timedelta(days=20),  # вне 7-дневного окна
                status=PostStatus.SENT,
            ),
            GeneratedPost(
                kind=PostKind.VIRAL,
                body="d",
                channel_id="@c",
                scheduled_for=now,
                status=PostStatus.FAILED,
                error="boom",
            ),
            GeneratedPost(
                kind=PostKind.MYSTICAL_WARNING,
                body="e",
                channel_id="@c",
                scheduled_for=now + timedelta(hours=1),
                status=PostStatus.SCHEDULED,
            ),
        ]
    )
    await session.commit()

    stats = await AdminStatsService(session).collect()
    assert stats.posts_by_status == {
        PostStatus.SENT: 3,
        PostStatus.FAILED: 1,
        PostStatus.SCHEDULED: 1,
    }
    # за 7 дней — два DAY_FORECAST, один VIRAL, один MYSTICAL_WARNING
    # (DAY_NUMBER 20 дней назад — не входит).
    assert stats.posts_by_kind_7d == {
        PostKind.DAY_FORECAST: 2,
        PostKind.VIRAL: 1,
        PostKind.MYSTICAL_WARNING: 1,
    }


def test_format_admin_stats_includes_all_sections() -> None:
    now = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)
    stats = AdminStats(
        as_of=now,
        users_total=10,
        users_with_profile=6,
        users_active_24h=3,
        users_active_7d=8,
        users_blocked=1,
        posts_by_status={PostStatus.SENT: 7, PostStatus.FAILED: 1},
        posts_by_kind_7d={PostKind.DAY_FORECAST: 4, PostKind.VIRAL: 2},
    )
    text = format_admin_stats(stats)
    assert "Статистика бота" in text
    assert "2026-05-18 12:00 UTC" in text
    assert "всего: 10" in text
    assert "с профилем: 6" in text
    assert "активны 24ч: 3" in text
    assert "активны 7д: 8" in text
    assert "заблокировали бота: 1" in text
    assert "отправлено: 7" in text
    assert "ошибка: 1" in text
    assert "Прогноз дня: 4" in text
    assert "Вирусный пост: 2" in text


def test_format_admin_stats_handles_empty_post_history() -> None:
    now = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)
    stats = AdminStats(
        as_of=now,
        users_total=0,
        users_with_profile=0,
        users_active_24h=0,
        users_active_7d=0,
        users_blocked=0,
        posts_by_status={},
        posts_by_kind_7d={},
    )
    text = format_admin_stats(stats)
    assert "ещё ни одного" in text
    assert "ничего" in text
