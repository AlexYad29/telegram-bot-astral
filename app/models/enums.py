"""Перечисления, используемые в ORM-моделях.

Все enum'ы лежат тут, чтобы их можно было импортировать и из моделей,
и из сервисов / клавиатур без циклических импортов.
"""

from __future__ import annotations

from enum import StrEnum


class Gender(StrEnum):
    """Пол пользователя — используется в нумерологии / совместимости / стилизации текста."""

    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class SubscriptionPlan(StrEnum):
    """Тарифные планы. На MVP — только free, но схема уже готова под платную модель."""

    FREE = "free"
    PREMIUM = "premium"
    LIFETIME = "lifetime"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELED = "canceled"


class PostKind(StrEnum):
    """Тип авто-поста в канал."""

    DAY_FORECAST = "day_forecast"
    DAY_NUMBER = "day_number"
    DAY_ENERGY = "day_energy"
    MYSTICAL_WARNING = "mystical_warning"
    VIRAL = "viral"


class PostStatus(StrEnum):
    SCHEDULED = "scheduled"
    SENT = "sent"
    FAILED = "failed"


class TarotSpreadKind(StrEnum):
    SINGLE = "single"
    THREE_CARD = "three_card"


__all__ = [
    "Gender",
    "PostKind",
    "PostStatus",
    "SubscriptionPlan",
    "SubscriptionStatus",
    "TarotSpreadKind",
]
