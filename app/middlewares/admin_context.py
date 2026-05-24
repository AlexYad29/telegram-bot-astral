"""Middleware, прокидывающий контекст админских команд: `scheduler` и `settings`.

Делается отдельным middleware (а не общим), чтобы публичные хендлеры
не зависели от планировщика и наоборот.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from app.config.settings import Settings


class AdminContextMiddleware(BaseMiddleware):
    """Кладёт `scheduler` и `settings` в data хендлеров."""

    def __init__(
        self,
        *,
        scheduler: AsyncIOScheduler,
        settings: Settings,
    ) -> None:
        self._scheduler = scheduler
        self._settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["scheduler"] = self._scheduler
        data["settings"] = self._settings
        return await handler(event, data)


__all__ = ["AdminContextMiddleware"]
