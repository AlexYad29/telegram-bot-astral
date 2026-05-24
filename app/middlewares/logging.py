"""Однострочное логирование входящих апдейтов.

Цель — иметь в логах кто/что/где для дебага без подключения внешнего observability.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

logger = logging.getLogger("astro.update")


class LoggingMiddleware(BaseMiddleware):
    """Логирует каждое входящее событие до вызова хендлера."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        kind, payload = _describe(event)
        logger.info(
            "update kind=%s user_id=%s username=%s payload=%s",
            kind,
            user.id if user else None,
            user.username if user else None,
            payload,
        )
        return await handler(event, data)


def _describe(event: TelegramObject) -> tuple[str, str]:
    """Краткий человекочитаемый дамп события для логов (без PII)."""
    if isinstance(event, Message):
        text = (event.text or event.caption or "")[:80]
        return "message", text
    if isinstance(event, CallbackQuery):
        return "callback_query", (event.data or "")[:80]
    return type(event).__name__, ""


__all__ = ["LoggingMiddleware"]
