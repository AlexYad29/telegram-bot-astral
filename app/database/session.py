"""Управление async-сессией SQLAlchemy.

Один движок на процесс, фабрика сессий, helper-контекстник для использования
вне Depends-механики aiogram (middleware будет вкатывать сессию в data в этапе 3).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Создать (или вернуть закэшированный) async-движок к Postgres."""
    settings = get_settings()
    return create_async_engine(
        settings.postgres_dsn,
        echo=settings.sqlalchemy_echo,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        future=True,
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Фабрика AsyncSession поверх единственного движка."""
    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        autoflush=False,
    )


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Контекстник «открыли сессию → если исключение откатили → закрыли».

    Удобен в local-скриптах и фоновых задачах (scheduler). В рамках хэндлеров
    aiogram сессия будет приходить из DbSessionMiddleware (этап 3).
    """
    factory = get_sessionmaker()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Закрыть пул соединений (вызывать при shutdown бота)."""
    engine = get_engine()
    await engine.dispose()


__all__ = [
    "dispose_engine",
    "get_engine",
    "get_sessionmaker",
    "session_scope",
]
