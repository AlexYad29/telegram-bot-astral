"""Middleware, прокидывающий singleton `AIService` в data хендлеров.

Сам сервис создаётся один раз на старте приложения и переиспользуется —
здесь только подкладываем ссылку. Это позволяет хендлерам объявлять
`ai_service: AIService` в kwargs и не знать о том, как именно собирается клиент.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.services.ai.service import AIService


class AIServiceMiddleware(BaseMiddleware):
    """Помещает `AIService` в `data["ai_service"]`."""

    def __init__(self, ai_service: AIService) -> None:
        self._ai_service = ai_service

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["ai_service"] = self._ai_service
        return await handler(event, data)


__all__ = ["AIServiceMiddleware"]
