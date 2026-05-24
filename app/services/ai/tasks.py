"""Каталог AI-задач и привязка их к моделям/токенам/кэшу.

Цель — единая точка стратификации:

* какая модель идёт на какую задачу (Nano для массового, Mini для пользовательского);
* какой лимит `max_tokens` ставим на ответ (режем длину = режем стоимость);
* можно ли кэшировать результат и на какой срок;
* какая категория задачи нужна для usage-репортов.

Хендлеры и сервисы не должны хардкодить модели или числа — только обращаться
к `task_config_for(task)`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.config.settings import Settings


class AITask(StrEnum):
    """Каноничный перечень AI-операций в проекте.

    Используется и в роутинге моделей, и в метриках, и в ключах кэша.
    """

    # ---- Канал / массовое ----
    CHANNEL_DAY_FORECAST = "channel_day_forecast"
    CHANNEL_DAY_NUMBER = "channel_day_number"
    CHANNEL_DAY_ENERGY = "channel_day_energy"
    CHANNEL_MYSTICAL_WARNING = "channel_mystical_warning"
    CHANNEL_VIRAL = "channel_viral"
    MYSTICAL_MESSAGE = "mystical_message"

    # ---- Пользовательское ----
    DAILY_FORECAST = "daily_forecast"
    ESOTERIC_ANSWER = "esoteric_answer"
    TAROT_INTERPRETATION = "tarot_interpretation"
    COMPATIBILITY_INTERPRETATION = "compatibility_interpretation"

    # ---- Системное ----
    SUMMARY_BUILD = "summary_build"


class ModelTier(StrEnum):
    """Дешёвая / основная — для отчётов и pricing."""

    NANO = "nano"
    MINI = "mini"


@dataclass(frozen=True, slots=True)
class TaskConfig:
    """Снимок настроек одной AI-задачи на момент рантайма."""

    task: AITask
    model: str
    tier: ModelTier
    max_tokens: int
    temperature: float
    cache_ttl_seconds: int  # 0 = не кэшируем
    cache_enabled: bool


# Дефолтная стратификация. Соответствие задача → дешёвая/основная модель.
# Менять без settings — нужно: каждое решение обосновано в комментарии.
_TIER_BY_TASK: dict[AITask, ModelTier] = {
    # Канал — массовый контент, дёшево и в большом объёме → Nano.
    AITask.CHANNEL_DAY_FORECAST: ModelTier.NANO,
    AITask.CHANNEL_DAY_NUMBER: ModelTier.NANO,
    AITask.CHANNEL_DAY_ENERGY: ModelTier.NANO,
    AITask.CHANNEL_MYSTICAL_WARNING: ModelTier.NANO,
    AITask.CHANNEL_VIRAL: ModelTier.NANO,
    AITask.MYSTICAL_MESSAGE: ModelTier.NANO,
    # Личный прогноз — короткий, шаблонный, кэшируем на сутки → Nano.
    AITask.DAILY_FORECAST: ModelTier.NANO,
    # Personal / dialog / сложные интерпретации → Mini.
    AITask.ESOTERIC_ANSWER: ModelTier.MINI,
    AITask.TAROT_INTERPRETATION: ModelTier.MINI,
    AITask.COMPATIBILITY_INTERPRETATION: ModelTier.MINI,
    # Суммаризация истории — дешёвая, на Nano.
    AITask.SUMMARY_BUILD: ModelTier.NANO,
}


# Какие задачи имеет смысл кэшировать (детерминированный или почти-детерминированный
# контент). Tarot не кэшируем — карты случайные.
_CACHEABLE: frozenset[AITask] = frozenset(
    {
        AITask.CHANNEL_DAY_FORECAST,
        AITask.CHANNEL_DAY_NUMBER,
        AITask.CHANNEL_DAY_ENERGY,
        AITask.CHANNEL_MYSTICAL_WARNING,
        AITask.CHANNEL_VIRAL,
        AITask.MYSTICAL_MESSAGE,
        AITask.DAILY_FORECAST,
        AITask.ESOTERIC_ANSWER,
        AITask.COMPATIBILITY_INTERPRETATION,
    }
)


def _resolve_model(settings: Settings, tier: ModelTier) -> str:
    if tier is ModelTier.NANO:
        return settings.openai_model_nano
    return settings.openai_model_mini


def _resolve_max_tokens(settings: Settings, task: AITask) -> int:
    """Подобрать `max_tokens` для задачи."""
    if task in {
        AITask.CHANNEL_DAY_FORECAST,
        AITask.CHANNEL_DAY_NUMBER,
        AITask.CHANNEL_DAY_ENERGY,
        AITask.CHANNEL_MYSTICAL_WARNING,
        AITask.CHANNEL_VIRAL,
        AITask.MYSTICAL_MESSAGE,
    }:
        return settings.openai_max_tokens_channel
    if task is AITask.DAILY_FORECAST:
        return settings.openai_max_tokens_forecast
    if task is AITask.ESOTERIC_ANSWER:
        return settings.openai_max_tokens_esoteric
    if task is AITask.TAROT_INTERPRETATION:
        return settings.openai_max_tokens_tarot
    if task is AITask.COMPATIBILITY_INTERPRETATION:
        return settings.openai_max_tokens_compatibility
    if task is AITask.SUMMARY_BUILD:
        return settings.openai_max_tokens_summary
    raise ValueError(f"max_tokens не задан для {task!s}")  # pragma: no cover


def _resolve_temperature(settings: Settings, task: AITask) -> float:
    if task in {
        AITask.CHANNEL_DAY_FORECAST,
        AITask.CHANNEL_DAY_NUMBER,
        AITask.CHANNEL_DAY_ENERGY,
        AITask.CHANNEL_MYSTICAL_WARNING,
        AITask.CHANNEL_VIRAL,
        AITask.MYSTICAL_MESSAGE,
    }:
        return settings.openai_temperature_channel
    if task is AITask.SUMMARY_BUILD:
        # Суммаризация требует точности, а не творчества.
        return 0.3
    return settings.openai_temperature_personal


def _resolve_cache_ttl(settings: Settings, task: AITask) -> int:
    if task is AITask.DAILY_FORECAST:
        return settings.ai_cache_ttl_daily_forecast_seconds
    if task is AITask.ESOTERIC_ANSWER:
        return settings.ai_cache_ttl_esoteric_seconds
    if task is AITask.COMPATIBILITY_INTERPRETATION:
        return settings.ai_cache_ttl_compatibility_seconds
    # Остальные cacheable — все channel-задачи + MYSTICAL_MESSAGE.
    return settings.ai_cache_ttl_channel_seconds


def task_config_for(task: AITask, settings: Settings) -> TaskConfig:
    """Собрать `TaskConfig` для задачи из текущих настроек."""
    tier = _TIER_BY_TASK[task]
    cacheable = task in _CACHEABLE
    return TaskConfig(
        task=task,
        model=_resolve_model(settings, tier),
        tier=tier,
        max_tokens=_resolve_max_tokens(settings, task),
        temperature=_resolve_temperature(settings, task),
        cache_ttl_seconds=_resolve_cache_ttl(settings, task) if cacheable else 0,
        cache_enabled=cacheable and settings.ai_cache_enabled,
    )


__all__ = ["AITask", "ModelTier", "TaskConfig", "task_config_for"]
