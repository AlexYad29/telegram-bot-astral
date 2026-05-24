"""Подсчёт токенов и оценка стоимости запросов к OpenAI.

Использует `tiktoken` для оффлайн-оценки токенов промпта. Реальный usage всё
равно берём из `response.usage` после вызова — но pre-flight counting нужен,
чтобы:

* отрезать слишком жирные истории до отправки;
* логировать запланированный объём (полезно в alert'ах);
* считать стоимость по фактическому usage в одной точке.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

import tiktoken

from app.config.settings import Settings
from app.services.ai.tasks import ModelTier

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Снимок usage'а одного chat-completion вызова."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@lru_cache(maxsize=4)
def _encoding(name: str) -> tiktoken.Encoding:
    """Кэшируем энкодер по имени (загрузка тяжёлая, делаем один раз)."""
    try:
        return tiktoken.get_encoding(name)
    except Exception:  # pragma: no cover — оборона на случай неизвестного кодека
        logger.warning("unknown tiktoken encoding %r, falling back to o200k_base", name)
        return tiktoken.get_encoding("o200k_base")


def count_text_tokens(text: str, *, encoding_name: str = "o200k_base") -> int:
    """Сколько токенов займёт `text`."""
    if not text:
        return 0
    return len(_encoding(encoding_name).encode(text))


def count_messages_tokens(
    messages: Iterable[dict[str, str]],
    *,
    encoding_name: str = "o200k_base",
) -> int:
    """Оценка токенов чат-формата.

    Точная формула OpenAI меняется между моделями (см. их cookbook), но для
    pre-flight оценки достаточно `sum(tokens(content)) + 4*N` накладных
    (per-message overhead) + 2 финальных.
    """
    enc = _encoding(encoding_name)
    total = 0
    n = 0
    for m in messages:
        n += 1
        # role обычно 1-2 токена + content
        total += len(enc.encode(m.get("content", "")))
        total += 4
    return total + 2 if n else 0


def _tier_for_model(model: str, settings: Settings) -> ModelTier:
    if model == settings.openai_model_nano:
        return ModelTier.NANO
    if model == settings.openai_model_mini:
        return ModelTier.MINI
    # Unknown model → берём mini-pricing как более консервативную оценку.
    logger.debug("unknown model %r for pricing, defaulting to MINI tier", model)
    return ModelTier.MINI


def estimate_cost_usd(
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    settings: Settings,
) -> float:
    """Оценить стоимость одного вызова в USD.

    pricing задан per-1M токенов в `Settings`. Возвращаем float — округление
    до cent делает `to_micro_cents()`/`to_cents()` уже на месте записи в БД.
    """
    tier = _tier_for_model(model, settings)
    if tier is ModelTier.NANO:
        in_rate = settings.openai_price_nano_in_per_1m_usd
        out_rate = settings.openai_price_nano_out_per_1m_usd
    else:
        in_rate = settings.openai_price_mini_in_per_1m_usd
        out_rate = settings.openai_price_mini_out_per_1m_usd
    return (prompt_tokens / 1_000_000.0) * in_rate + (
        completion_tokens / 1_000_000.0
    ) * out_rate


def to_micro_cents(usd: float) -> int:
    """USD → миллионные доли цента, чтобы хранить как BIGINT без float-погрешностей.

    Пример: $0.000123 → 12300 micro-cents. Возможны очень дешёвые вызовы
    (доли копейки), поэтому центы — слишком грубо.
    """
    return int(round(usd * 100 * 1_000_000))


def from_micro_cents(value: int) -> float:
    """Обратное преобразование для отчётов."""
    return value / (100 * 1_000_000)


__all__ = [
    "TokenUsage",
    "count_messages_tokens",
    "count_text_tokens",
    "estimate_cost_usd",
    "from_micro_cents",
    "to_micro_cents",
]
