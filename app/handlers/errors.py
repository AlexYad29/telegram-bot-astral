"""Глобальный error handler.

Логируем исключение целиком (stack trace) и пытаемся вежливо извиниться
перед пользователем — не светя ему детали.
"""

from __future__ import annotations

import logging
from contextlib import suppress

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, ErrorEvent, Message

logger = logging.getLogger(__name__)

router = Router(name="errors")


_FALLBACK = (
    "🌫 Что-то затуманилось в энергетическом поле. "
    "Попробуй ещё раз через минуту — звёзды ответят снова."
)


@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    """Поймать любое необработанное исключение из хендлеров."""
    logger.exception(
        "unhandled error in handler: %s",
        event.exception,
        exc_info=event.exception,
    )

    update = event.update
    target: Message | CallbackQuery | None = None
    if update.message is not None:
        target = update.message
    elif update.callback_query is not None:
        target = update.callback_query

    if target is None:
        return True

    with suppress(TelegramAPIError):
        if isinstance(target, Message):
            await target.answer(_FALLBACK)
        else:
            await target.answer(_FALLBACK, show_alert=False)
    return True


__all__ = ["router"]
