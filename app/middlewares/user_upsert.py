"""Middleware, который гарантирует, что для каждого аутентифицированного
Telegram-пользователя есть актуальная запись в таблице `users`.

Опирается на сессию, которую кладёт `DbSessionMiddleware` (поэтому
регистрируется ПОСЛЕ него).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user import UserRepository

logger = logging.getLogger(__name__)


class UserUpsertMiddleware(BaseMiddleware):
    """Создаёт/обновляет `User` по `event_from_user` и кладёт ORM-объект в `data["user"]`."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: User | None = data.get("event_from_user")
        session: AsyncSession | None = data.get("session")

        if tg_user is None or tg_user.is_bot or session is None:
            return await handler(event, data)

        repo = UserRepository(session)
        try:
            user = await repo.upsert_from_telegram(
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                language_code=tg_user.language_code,
            )
        except Exception:
            logger.exception("user upsert failed for user_id=%s", tg_user.id)
            raise
        data["user"] = user
        return await handler(event, data)


__all__ = ["UserUpsertMiddleware"]
