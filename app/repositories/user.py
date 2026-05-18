"""Репозиторий пользователей."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.enums import Gender
from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return await self.session.get(User, telegram_id)

    async def upsert_from_telegram(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        language_code: str | None,
    ) -> User:
        """Создать или обновить пользователя по данным из Telegram update.

        Использует PostgreSQL `INSERT ... ON CONFLICT DO UPDATE`, чтобы за один
        round-trip получить актуальный объект.
        """
        now = datetime.now(tz=UTC)
        stmt = (
            pg_insert(User)
            .values(
                id=telegram_id,
                telegram_username=username,
                telegram_first_name=first_name,
                telegram_last_name=last_name,
                language_code=language_code,
                last_active_at=now,
            )
            .on_conflict_do_update(
                index_elements=[User.id],
                set_={
                    "telegram_username": username,
                    "telegram_first_name": first_name,
                    "telegram_last_name": last_name,
                    "language_code": language_code,
                    "last_active_at": now,
                },
            )
            .returning(User)
        )
        result = await self.session.execute(stmt)
        user = result.scalar_one()
        return user

    async def mark_active(self, telegram_id: int) -> None:
        stmt = (
            update(User)
            .where(User.id == telegram_id)
            .values(last_active_at=datetime.now(tz=UTC))
        )
        await self.session.execute(stmt)

    async def update_profile(
        self,
        telegram_id: int,
        *,
        full_name: str | None = None,
        birth_date: date | None = None,
        gender: Gender | None = None,
    ) -> User | None:
        """Точечный апдейт профильных полей (этап 4)."""
        values: dict[str, Any] = {}
        if full_name is not None:
            values["full_name"] = full_name
        if birth_date is not None:
            values["birth_date"] = birth_date
        if gender is not None:
            values["gender"] = gender
        if not values:
            return await self.get_by_telegram_id(telegram_id)
        stmt = (
            update(User)
            .where(User.id == telegram_id)
            .values(**values)
            .returning(User)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def set_blocked(self, telegram_id: int, blocked: bool) -> None:
        stmt = update(User).where(User.id == telegram_id).values(is_blocked=blocked)
        await self.session.execute(stmt)

    async def count(self) -> int:
        from sqlalchemy import func

        result = await self.session.execute(select(func.count(User.id)))
        return int(result.scalar_one())


__all__ = ["UserRepository"]
