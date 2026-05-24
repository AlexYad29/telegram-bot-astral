"""Generic base repository.

Никакой магии — просто типизированный набор операций, которые повторяются
в каждом репозитории. Дочерние классы свободны добавлять свои методы.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Базовый репозиторий для одной ORM-модели."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, pk: Any) -> ModelT | None:
        return await self.session.get(self.model, pk)

    async def list(self, limit: int | None = None, offset: int = 0) -> Sequence[ModelT]:
        stmt = select(self.model).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.scalars(stmt)
        return result.all()

    async def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def delete(self, pk: Any) -> int:
        stmt = sa_delete(self.model).where(self.model.__table__.c.id == pk)
        result = await self.session.execute(stmt)
        return result.rowcount or 0


__all__ = ["BaseRepository"]
