"""Redis-кэш для повторяемых AI-генераций.

Зачем: один и тот же канал-пост на дату не должен генериться дважды; «прогноз
дня» для пользователя в течение суток — то же самое; популярные эзотерические
вопросы укладываются на одинаковые формулировки.

Дизайн:

* TTL зашит в `TaskConfig` (см. `ai/tasks.py`).
* Глобальный switch `ai_cache_enabled` — если выключен, всё прозрачно становится
  miss.
* Ключи получают префикс с версией промптов (`_PROMPT_VERSION`) — чтобы при
  серьёзных правках формулировок старые ответы автоматически инвалидировались.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date
from typing import TYPE_CHECKING

from app.services.ai.tasks import AITask

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Версия зашита в ключи. Поднимаем при изменении формулировок SYSTEM_PROMPT/
# builders — старые кешированные ответы становятся недостижимы без явного flush.
_PROMPT_VERSION = "v1"

_NAMESPACE = "ai:cache"


def _hash_text(text: str) -> str:
    """SHA1 от нормализованной строки → 40 hex-символов. Достаточно от коллизий."""
    return hashlib.sha1(text.strip().lower().encode("utf-8")).hexdigest()


def _date_part(d: date) -> str:
    return d.isoformat()


def make_channel_post_key(task: AITask, *, day: date) -> str:
    """Ключ канал-постов: один пост в сутки на каждый тип."""
    return f"{_NAMESPACE}:{_PROMPT_VERSION}:channel:{task.value}:{_date_part(day)}"


def make_daily_forecast_key(*, user_id: int, day: date) -> str:
    """Ключ персонального прогноза: один прогноз в сутки на пользователя."""
    return (
        f"{_NAMESPACE}:{_PROMPT_VERSION}:forecast:{user_id}:{_date_part(day)}"
    )


def make_esoteric_answer_key(question: str) -> str:
    """Ключ эзотерических ответов: hash вопроса (общий для всех пользователей)."""
    return f"{_NAMESPACE}:{_PROMPT_VERSION}:esoteric:{_hash_text(question)}"


def make_compatibility_key(date_a: date, date_b: date) -> str:
    """Ключ интерпретации совместимости — сортируем даты, чтобы (a,b)==(b,a)."""
    lo, hi = sorted((date_a, date_b))
    return (
        f"{_NAMESPACE}:{_PROMPT_VERSION}:compat:"
        f"{_date_part(lo)}-{_date_part(hi)}"
    )


class AICache:
    """Тонкая обёртка над Redis с метриками `hit/miss`.

    Хранит только текст ответа (`str`). Если в будущем понадобится метаданные —
    можно сериализовать в JSON, но сейчас этого не требуется.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, key: str) -> str | None:
        raw = await self._redis.get(key)
        if raw is None:
            logger.debug("ai-cache MISS key=%s", key)
            return None
        if isinstance(raw, bytes):
            value = raw.decode("utf-8", errors="replace")
        else:
            value = str(raw)
        logger.info("ai-cache HIT key=%s bytes=%d", key, len(value))
        return value

    async def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        if not value or ttl_seconds <= 0:
            return
        await self._redis.set(key, value, ex=ttl_seconds)
        logger.debug("ai-cache SET key=%s ttl=%ds bytes=%d", key, ttl_seconds, len(value))

    async def invalidate(self, key: str) -> None:
        await self._redis.delete(key)


__all__ = [
    "AICache",
    "make_channel_post_key",
    "make_compatibility_key",
    "make_daily_forecast_key",
    "make_esoteric_answer_key",
]
