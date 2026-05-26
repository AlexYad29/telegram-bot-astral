"""Фильтры подписки.

`PremiumFilter` — пропускает только пользователей с активной Premium/VIP.
`VipFilter` — только VIP/Lifetime.

Оба фильтра читают `data["subscription"]` (SubscriptionStatusInfo), которое
кладёт SubscriptionMiddleware. Если миддлвара не отработала (например,
тест) — фильтр возвращает False, не падает.
"""

from __future__ import annotations

from typing import Any

from aiogram.filters import Filter
from aiogram.types import TelegramObject

from app.services.subscription import SubscriptionStatusInfo


class PremiumFilter(Filter):
    """Пропускает Premium/VIP/Lifetime."""

    async def __call__(self, event: TelegramObject, **data: Any) -> bool:
        status: SubscriptionStatusInfo | None = data.get("subscription")
        return bool(status and status.is_premium)


class VipFilter(Filter):
    """Пропускает только VIP/Lifetime."""

    async def __call__(self, event: TelegramObject, **data: Any) -> bool:
        status: SubscriptionStatusInfo | None = data.get("subscription")
        return bool(status and status.is_vip)


__all__ = ["PremiumFilter", "VipFilter"]
