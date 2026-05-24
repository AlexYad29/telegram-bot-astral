"""Юнит-тесты cost-optimization слоя ETAP 12.

Покрываем самое критичное (без сети и БД):

* `task_config_for(...)` — стратификация моделей и cache_enabled;
* `count_text_tokens` / `count_messages_tokens` — детерминированы;
* `estimate_cost_usd` + micro_cents conversion — арифметика;
* cache key builders — стабильность и симметричность compatibility;
* `AICache` — get/set/invalidate против fake-Redis.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.config.settings import Settings
from app.services.ai.cache import (
    AICache,
    make_channel_post_key,
    make_compatibility_key,
    make_daily_forecast_key,
    make_esoteric_answer_key,
)
from app.services.ai.tasks import AITask, ModelTier, task_config_for
from app.services.ai.tokens import (
    TokenUsage,
    count_messages_tokens,
    count_text_tokens,
    estimate_cost_usd,
    from_micro_cents,
    to_micro_cents,
)


# ---------- Settings fixture ----------
def _make_settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        bot_token="dummy",  # type: ignore[arg-type]
        openai_api_key="dummy",  # type: ignore[arg-type]
    )


# ---------- Task routing ----------
@pytest.mark.parametrize(
    ("task", "expected_tier"),
    [
        (AITask.CHANNEL_DAY_FORECAST, ModelTier.NANO),
        (AITask.CHANNEL_DAY_NUMBER, ModelTier.NANO),
        (AITask.CHANNEL_DAY_ENERGY, ModelTier.NANO),
        (AITask.CHANNEL_MYSTICAL_WARNING, ModelTier.NANO),
        (AITask.CHANNEL_VIRAL, ModelTier.NANO),
        (AITask.MYSTICAL_MESSAGE, ModelTier.NANO),
        (AITask.DAILY_FORECAST, ModelTier.NANO),
        (AITask.SUMMARY_BUILD, ModelTier.NANO),
        (AITask.ESOTERIC_ANSWER, ModelTier.MINI),
        (AITask.TAROT_INTERPRETATION, ModelTier.MINI),
        (AITask.COMPATIBILITY_INTERPRETATION, ModelTier.MINI),
    ],
)
def test_task_config_for_assigns_correct_tier(
    task: AITask, expected_tier: ModelTier
) -> None:
    settings = _make_settings()
    cfg = task_config_for(task, settings)
    assert cfg.tier is expected_tier
    if expected_tier is ModelTier.NANO:
        assert cfg.model == settings.openai_model_nano
    else:
        assert cfg.model == settings.openai_model_mini


def test_task_config_for_tarot_is_not_cached() -> None:
    """Tarot интерпретации уникальные — кэш не должен включаться."""
    settings = _make_settings()
    cfg = task_config_for(AITask.TAROT_INTERPRETATION, settings)
    assert cfg.cache_enabled is False
    assert cfg.cache_ttl_seconds == 0


def test_task_config_for_daily_forecast_is_cached_with_ttl() -> None:
    settings = _make_settings()
    cfg = task_config_for(AITask.DAILY_FORECAST, settings)
    assert cfg.cache_enabled is True
    assert cfg.cache_ttl_seconds == settings.ai_cache_ttl_daily_forecast_seconds


def test_task_config_respects_global_cache_kill_switch() -> None:
    """`ai_cache_enabled=False` отключает кэш всем задачам."""
    settings = Settings(  # type: ignore[call-arg]
        bot_token="dummy",  # type: ignore[arg-type]
        openai_api_key="dummy",  # type: ignore[arg-type]
        ai_cache_enabled=False,
    )
    cfg = task_config_for(AITask.DAILY_FORECAST, settings)
    assert cfg.cache_enabled is False


# ---------- Tokens / pricing ----------
def test_count_text_tokens_is_nonzero_and_deterministic() -> None:
    text = "Сегодня лунный свет ведёт тебя."
    a = count_text_tokens(text)
    b = count_text_tokens(text)
    assert a == b
    assert a > 0


def test_count_text_tokens_empty_is_zero() -> None:
    assert count_text_tokens("") == 0


def test_count_messages_tokens_includes_overhead() -> None:
    msgs = [
        {"role": "system", "content": "you are a mystic"},
        {"role": "user", "content": "ask"},
    ]
    pure = count_text_tokens("you are a mystic") + count_text_tokens("ask")
    chat_total = count_messages_tokens(msgs)
    # +4 на каждое сообщение + 2 финальных
    assert chat_total >= pure + 4 * 2 + 2


def test_estimate_cost_usd_nano_cheaper_than_mini() -> None:
    settings = _make_settings()
    nano = estimate_cost_usd(
        model=settings.openai_model_nano,
        prompt_tokens=1000,
        completion_tokens=500,
        settings=settings,
    )
    mini = estimate_cost_usd(
        model=settings.openai_model_mini,
        prompt_tokens=1000,
        completion_tokens=500,
        settings=settings,
    )
    assert 0 < nano < mini


def test_micro_cents_roundtrip() -> None:
    usd = 0.000123
    mc = to_micro_cents(usd)
    back = from_micro_cents(mc)
    # 6-знаковая точность достаточна.
    assert abs(back - usd) < 1e-7


def test_token_usage_is_immutable() -> None:
    usage = TokenUsage(10, 5, 15)
    with pytest.raises((AttributeError, Exception)):
        usage.prompt_tokens = 999  # type: ignore[misc]


# ---------- Cache key builders ----------
def test_channel_post_key_contains_task_and_date() -> None:
    key = make_channel_post_key(
        AITask.CHANNEL_DAY_FORECAST, day=date(2026, 5, 18)
    )
    assert "channel" in key
    assert AITask.CHANNEL_DAY_FORECAST.value in key
    assert "2026-05-18" in key


def test_daily_forecast_key_carries_user_id_and_day() -> None:
    key = make_daily_forecast_key(user_id=42, day=date(2026, 5, 18))
    assert ":42:" in key
    assert "2026-05-18" in key


def test_esoteric_key_is_stable_for_same_question() -> None:
    a = make_esoteric_answer_key("Стоит ли менять работу?")
    b = make_esoteric_answer_key("стоит ли менять работу?  ")  # case + ws
    assert a == b


def test_esoteric_key_differs_for_different_question() -> None:
    a = make_esoteric_answer_key("Стоит ли менять работу?")
    b = make_esoteric_answer_key("Когда я найду любовь?")
    assert a != b


def test_compatibility_key_is_symmetric_in_dates() -> None:
    a = make_compatibility_key(date(1990, 1, 1), date(1985, 6, 5))
    b = make_compatibility_key(date(1985, 6, 5), date(1990, 1, 1))
    assert a == b


# ---------- AICache against a fake Redis ----------
class _FakeRedis:
    """Минимальный фейк Redis-клиента."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self.last_ttl: int | None = None

    async def get(self, key: str) -> Any:
        return self._store.get(key)

    async def set(self, key: str, value: str, *, ex: int | None = None) -> None:
        self._store[key] = value
        self.last_ttl = ex

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


@pytest.mark.asyncio
async def test_aicache_miss_returns_none() -> None:
    cache = AICache(_FakeRedis())  # type: ignore[arg-type]
    assert await cache.get("missing") is None


@pytest.mark.asyncio
async def test_aicache_set_then_get_returns_value() -> None:
    redis = _FakeRedis()
    cache = AICache(redis)  # type: ignore[arg-type]
    await cache.set("k", "звёзды шепчут", ttl_seconds=60)
    assert redis.last_ttl == 60
    assert await cache.get("k") == "звёзды шепчут"


@pytest.mark.asyncio
async def test_aicache_set_skips_empty_or_zero_ttl() -> None:
    redis = _FakeRedis()
    cache = AICache(redis)  # type: ignore[arg-type]
    await cache.set("k1", "", ttl_seconds=60)
    await cache.set("k2", "value", ttl_seconds=0)
    assert await cache.get("k1") is None
    assert await cache.get("k2") is None


@pytest.mark.asyncio
async def test_aicache_invalidate_removes_key() -> None:
    redis = _FakeRedis()
    cache = AICache(redis)  # type: ignore[arg-type]
    await cache.set("k", "x", ttl_seconds=60)
    await cache.invalidate("k")
    assert await cache.get("k") is None


@pytest.mark.asyncio
async def test_aicache_get_decodes_bytes() -> None:
    redis = _FakeRedis()
    redis._store["k"] = b"bytes-value"
    cache = AICache(redis)  # type: ignore[arg-type]
    assert await cache.get("k") == "bytes-value"
