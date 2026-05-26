"""Отдельный rate-limiter для дорогих AI-команд.

Зачем нужен отдельно от `ThrottlingMiddleware`: общий throttle защищает от
флуда любыми сообщениями (низкий cost), а здесь — от спама именно AI-командами,
где каждый вызов стоит реальных денег.

Алгоритм — sliding window на ZSET (как и в `ThrottlingMiddleware`):

* для каждого пользователя ключ `ai-throttle:<user_id>`;
* в ZSET складываем таймстемпы вызовов в миллисекундах;
* при каждом событии чистим элементы старше 60 сек, считаем размер;
* если > `max_per_minute` → throttled.

В дополнение — короткий cooldown (`min_interval_seconds`) между вызовами одного
пользователя, чтобы не давить даже точечно («кликнул дважды → дублирующий
запрос»).

Triggers — фиксированный набор: `/forecast`, `/tarot`, `/compatibility`,
ответы в FSM-флоу совместимости/таро, текстовые сообщения, попадающие в
дефолтный «эзотерический ответ». Это покрывает все актуальные AI-точки.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

THROTTLE_NOTICE = (
    "🌑 Слишком много запросов к звёздам подряд. "
    "Подождите немного и попробуйте снова."
)

_REDIS_NS = "ai-throttle"
_WINDOW_SECONDS = 60

# Триггеры — команды и callback-data, инициирующие AI-вызов.
_AI_COMMAND_TRIGGERS: tuple[str, ...] = (
    "/forecast",
    "/tarot",
    "/compatibility",
)
_AI_CALLBACK_TRIGGERS: tuple[str, ...] = (
    "forecast:retry",
    "tarot:draw",
    "compat:run",
)


def _looks_like_ai_call(event: TelegramObject) -> bool:
    """Эвристика: сообщение/коллбек инициирует AI-вызов?

    Сознательно широкая, но не покрывает 100% — точечные команды покрыты
    явно, а текстовые «эзотерические вопросы» защищаются на уровне самого
    эндпоинта (через `AIService` cache + DB-tracking).

    Работает по duck-typing (а не isinstance), чтобы быть легко протестируемым
    без подделки полноценного `aiogram.types.Message`.
    """
    text_attr = getattr(event, "text", None)
    if isinstance(text_attr, str):
        text = text_attr.strip()
        if not text:
            return False
        # Команда вида "/forecast" или "/forecast@bot".
        lower = text.lower().split()[0].split("@")[0]
        return lower in _AI_COMMAND_TRIGGERS
    data_attr = getattr(event, "data", None)
    if isinstance(data_attr, str):
        return any(data_attr.startswith(prefix) for prefix in _AI_CALLBACK_TRIGGERS)
    return False


def _user_id(event: TelegramObject) -> int | None:
    user = getattr(event, "from_user", None)
    return user.id if user is not None else None


def _is_premium(data: dict[str, Any]) -> bool:
    """Читаем тариф из data (положено SubscriptionMiddleware)."""
    status = data.get("subscription")
    return bool(getattr(status, "is_premium", False))


class AIRequestThrottle(BaseMiddleware):
    """Per-user rate-limit на AI-вызовы (sliding window + cooldown).

    Поддерживает per-tier лимиты: Free-пользователи режутся сильнее,
    Premium/VIP — мягче. Тариф читается из `data["subscription"]`
    (`SubscriptionStatusInfo`), который кладёт `SubscriptionMiddleware`.
    Если статус не пришёл — считаем юзера Free.
    """

    def __init__(
        self,
        redis: Redis,
        *,
        max_per_minute: int = 6,
        min_interval_seconds: float = 2.0,
        max_per_minute_premium: int | None = None,
        min_interval_seconds_premium: float | None = None,
    ) -> None:
        self._redis = redis
        self._max_per_minute = max(1, int(max_per_minute))
        self._min_interval_ms = int(max(0.0, min_interval_seconds) * 1000)
        self._max_per_minute_premium = (
            max(1, int(max_per_minute_premium))
            if max_per_minute_premium is not None
            else self._max_per_minute
        )
        self._min_interval_ms_premium = (
            int(max(0.0, min_interval_seconds_premium) * 1000)
            if min_interval_seconds_premium is not None
            else self._min_interval_ms
        )

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not _looks_like_ai_call(event):
            return await handler(event, data)
        user_id = _user_id(event)
        if user_id is None:
            return await handler(event, data)

        is_premium = _is_premium(data)
        max_per_minute = (
            self._max_per_minute_premium if is_premium else self._max_per_minute
        )
        min_interval_ms = (
            self._min_interval_ms_premium if is_premium else self._min_interval_ms
        )

        if await self._is_throttled(
            user_id,
            max_per_minute=max_per_minute,
            min_interval_ms=min_interval_ms,
        ):
            await self._notify(event)
            logger.info(
                "ai-throttle: user_id=%s blocked (premium=%s max=%d/min cd=%dms)",
                user_id,
                is_premium,
                max_per_minute,
                min_interval_ms,
            )
            return None
        return await handler(event, data)

    async def _is_throttled(
        self,
        user_id: int,
        *,
        max_per_minute: int,
        min_interval_ms: int,
    ) -> bool:
        key = f"{_REDIS_NS}:{user_id}"
        now_ms = int(time.time() * 1000)
        window_start_ms = now_ms - _WINDOW_SECONDS * 1000
        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start_ms)
        pipe.zrange(key, -1, -1, withscores=True)
        pipe.zcard(key)
        _, last_items, current_count = await pipe.execute()

        # Cooldown между вызовами.
        if min_interval_ms > 0 and last_items:
            try:
                _, last_ts = last_items[0]
                if now_ms - int(last_ts) < min_interval_ms:
                    return True
            except (TypeError, ValueError):
                pass

        if current_count >= max_per_minute:
            return True

        # Регистрируем текущий вызов. Добавляем uuid-суффикс к member'у, чтобы не
        # перезаписывать запись при нескольких вызовах в одну миллисекунду.
        member = f"{now_ms}-{uuid.uuid4().hex[:8]}"
        pipe = self._redis.pipeline()
        pipe.zadd(key, {member: now_ms})
        pipe.expire(key, _WINDOW_SECONDS * 2)
        await pipe.execute()
        return False

    @staticmethod
    async def _notify(event: TelegramObject) -> None:
        # Duck-typing: любой объект с «.answer(text)» подойдёт (и Message, и
        # CallbackQuery, и тестовый fake).
        answer = getattr(event, "answer", None)
        if not callable(answer):
            return
        try:
            if isinstance(event, CallbackQuery):
                await event.answer(THROTTLE_NOTICE, show_alert=False)
            else:
                await answer(THROTTLE_NOTICE)
        except Exception:
            logger.debug("ai-throttle notice send failed", exc_info=True)


__all__ = ["AIRequestThrottle", "THROTTLE_NOTICE"]
