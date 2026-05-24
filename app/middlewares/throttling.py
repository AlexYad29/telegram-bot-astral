"""Анти-спам на Redis.

Два механизма работают одновременно:

1. **Cooldown** — между двумя событиями одного пользователя должно пройти
   не менее `default_rate` секунд (`SET key NX PX <ms>`).
2. **Per-minute limit** — за скользящую минуту не более
   `max_per_minute` событий (`INCR` + `EXPIRE` на ключе минуты).

Если событие подавлено и пользователь уже получал предупреждение в течение
ближайших 5 секунд — молча роняем. Иначе один раз отвечаем мистическим
текстом в стиле бота.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

THROTTLE_NOTICE = "✨ Не торопись. Звёзды не любят суеты — попробуй через мгновение."


class ThrottlingMiddleware(BaseMiddleware):
    """Простой Redis-based rate limiter для входящих апдейтов."""

    def __init__(
        self,
        redis: Redis,
        *,
        default_rate: float,
        max_per_minute: int,
    ) -> None:
        if default_rate <= 0:
            raise ValueError("default_rate must be positive (seconds)")
        if max_per_minute <= 0:
            raise ValueError("max_per_minute must be positive")
        self._redis = redis
        self._cooldown_ms = max(1, int(default_rate * 1000))
        self._max_per_minute = max_per_minute

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is None or user.is_bot:
            return await handler(event, data)

        # Cooldown: не чаще, чем раз в `default_rate` секунд.
        cooldown_key = f"throttle:cd:{user.id}"
        was_set = await self._redis.set(
            cooldown_key, b"1", px=self._cooldown_ms, nx=True
        )
        if not was_set:
            await self._notify_once(event, user.id)
            logger.info("throttled (cooldown) user_id=%s", user.id)
            return None

        # Per-minute window.
        minute_key = f"throttle:m:{user.id}"
        count = await self._redis.incr(minute_key)
        if count == 1:
            await self._redis.expire(minute_key, 60)
        if count > self._max_per_minute:
            await self._notify_once(event, user.id)
            logger.warning(
                "throttled (per-minute) user_id=%s count=%s limit=%s",
                user.id,
                count,
                self._max_per_minute,
            )
            return None

        return await handler(event, data)

    async def _notify_once(self, event: TelegramObject, user_id: int) -> None:
        """Один раз в 5 секунд ответить «не торопись» — чтобы не плодить шум."""
        notify_key = f"throttle:notified:{user_id}"
        first_time = await self._redis.set(notify_key, b"1", ex=5, nx=True)
        if not first_time:
            return
        with suppress(Exception):
            if isinstance(event, Message):
                await event.answer(THROTTLE_NOTICE)
            elif isinstance(event, CallbackQuery):
                await event.answer(THROTTLE_NOTICE, show_alert=False)


__all__ = ["THROTTLE_NOTICE", "ThrottlingMiddleware"]
