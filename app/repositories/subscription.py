"""Репозиторий подписок."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update

from app.models.enums import SubscriptionPlan, SubscriptionStatus
from app.models.subscription import Subscription
from app.repositories.base import BaseRepository


class SubscriptionRepository(BaseRepository[Subscription]):
    model = Subscription

    async def get_active_for_user(self, user_id: int) -> Subscription | None:
        stmt = (
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
            .order_by(Subscription.started_at.desc())
            .limit(1)
        )
        result = await self.session.scalars(stmt)
        return result.first()

    async def create(
        self,
        *,
        user_id: int,
        plan: SubscriptionPlan,
        started_at: datetime,
        expires_at: datetime | None,
        payment_provider: str | None = None,
        payment_id: str | None = None,
    ) -> Subscription:
        sub = Subscription(
            user_id=user_id,
            plan=plan,
            status=SubscriptionStatus.ACTIVE,
            started_at=started_at,
            expires_at=expires_at,
            payment_provider=payment_provider,
            payment_id=payment_id,
        )
        return await self.add(sub)

    async def expire_due(self, now: datetime | None = None) -> int:
        now = now or datetime.now(tz=UTC)
        stmt = (
            update(Subscription)
            .where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.expires_at.is_not(None),
                Subscription.expires_at <= now,
            )
            .values(status=SubscriptionStatus.EXPIRED)
        )
        result = await self.session.execute(stmt)
        return result.rowcount or 0


__all__ = ["SubscriptionRepository"]
