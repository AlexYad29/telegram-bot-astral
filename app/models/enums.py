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
    """Тарифные планы."""

    FREE = "free"
    PREMIUM = "premium"
    VIP = "vip"
    LIFETIME = "lifetime"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELED = "canceled"


class PaymentProvider(StrEnum):
    """Платёжный шлюз. На MVP — Telegram Stars (XTR), у остальных — заготовка."""

    TELEGRAM_STARS = "telegram_stars"
    YOOKASSA = "yookassa"
    STRIPE = "stripe"
    MANUAL = "manual"  # ручной grant админом


class PaymentStatus(StrEnum):
    PENDING = "pending"  # invoice выставлен, ждём оплаты
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


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
    "PaymentProvider",
    "PaymentStatus",
    "PostKind",
    "PostStatus",
    "SubscriptionPlan",
    "SubscriptionStatus",
    "TarotSpreadKind",
]
