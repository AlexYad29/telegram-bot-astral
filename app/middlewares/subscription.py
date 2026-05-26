"""Middleware, прокидывающий статус подписки в data хендлеров.

После этого middleware каждый хендлер видит:

* `data["subscription"]` — `SubscriptionStatusInfo` (всегда, даже для FREE);
* `data["subscription_service"]` — `SubscriptionService` (если нужно
  активировать/продлить из хендлера).

Должна стоять ПОСЛЕ `DbSessionMiddleware` и `UserUpsertMiddleware`, потому
что:
* нужен `data["session"]` для репозиториев;
* нужна гарантия, что юзер уже есть в `users` (FK на subscriptions/payments).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.repositories.payment import PaymentRepository
from app.repositories.referral import ReferralRepository
from app.repositories.subscription import SubscriptionRepository
from app.services.subscription import SubscriptionService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.config.settings import Settings


class SubscriptionMiddleware(BaseMiddleware):
    """Инжектит SubscriptionService + текущий статус подписки в data."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session: AsyncSession | None = data.get("session")
        if session is None:
            # Без сессии не сможем посчитать статус — пропускаем (FREE
            # по умолчанию проставится в фильтрах при необходимости).
            return await handler(event, data)

        service = SubscriptionService(
            settings=self._settings,
            subscription_repo=SubscriptionRepository(session),
            payment_repo=PaymentRepository(session),
            referral_repo=ReferralRepository(session),
        )
        data["subscription_service"] = service

        # Telegram user_id — может отсутствовать (например, на канал-апдейтах),
        # тогда статус не считаем.
        user = data.get("event_from_user")
        if user is not None:
            try:
                data["subscription"] = await service.get_status(user.id)
            except Exception:
                # БД сломалась — лучше пустить хендлер дальше как FREE, чем
                # отвечать 500 на каждое сообщение.
                pass

        return await handler(event, data)


__all__ = ["SubscriptionMiddleware"]
