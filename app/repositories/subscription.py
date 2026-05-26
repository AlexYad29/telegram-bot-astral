"""Репозиторий подписок."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update

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

    async def get_latest_for_user(self, user_id: int) -> Subscription | None:
        """Последняя по времени подписка пользователя (любого статуса)."""
        stmt = (
            select(Subscription)
            .where(Subscription.user_id == user_id)
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

    async def extend(
        self,
        subscription_id: int,
        *,
        new_expires_at: datetime,
        plan: SubscriptionPlan | None = None,
        payment_provider: str | None = None,
        payment_id: str | None = None,
    ) -> Subscription | None:
        values: dict[str, Any] = {
            "expires_at": new_expires_at,
            "status": SubscriptionStatus.ACTIVE,
        }
        if plan is not None:
            values["plan"] = plan
        if payment_provider is not None:
            values["payment_provider"] = payment_provider
        if payment_id is not None:
            values["payment_id"] = payment_id
        stmt = (
            update(Subscription)
            .where(Subscription.id == subscription_id)
            .values(**values)
            .returning(Subscription)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def cancel(self, subscription_id: int) -> Subscription | None:
        stmt = (
            update(Subscription)
            .where(Subscription.id == subscription_id)
            .values(status=SubscriptionStatus.CANCELED)
            .returning(Subscription)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

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
            # bulk-обновление без синхронизации in-memory объектов сессии —
            # они перечитаются при следующем запросе. Это быстрее и избавляет от evaluator-эррора
            # при сравнении tz-naive datetime в сессии с tz-aware `now`.
            .execution_options(synchronize_session=False)
        )
        result = await self.session.execute(stmt)
        return result.rowcount or 0

    async def count_active_by_plan(self) -> dict[SubscriptionPlan, int]:
        stmt = (
            select(Subscription.plan, func.count(Subscription.id))
            .where(Subscription.status == SubscriptionStatus.ACTIVE)
            .group_by(Subscription.plan)
        )
        result = await self.session.execute(stmt)
        return {plan: int(cnt) for plan, cnt in result.all()}

    async def count_active(self) -> int:
        stmt = select(func.count(Subscription.id)).where(
            Subscription.status == SubscriptionStatus.ACTIVE
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())


__all__ = ["SubscriptionRepository"]
