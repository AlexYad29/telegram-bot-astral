"""Репозиторий платежей."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update

from app.models.enums import PaymentProvider, PaymentStatus, SubscriptionPlan
from app.models.payment import Payment
from app.repositories.base import BaseRepository


class PaymentRepository(BaseRepository[Payment]):
    model = Payment

    async def create_pending(
        self,
        *,
        user_id: int,
        provider: PaymentProvider,
        plan: SubscriptionPlan,
        currency: str,
        amount: int,
        duration_days: int,
        invoice_payload: str,
    ) -> Payment:
        payment = Payment(
            user_id=user_id,
            provider=provider,
            status=PaymentStatus.PENDING,
            plan=plan,
            currency=currency,
            amount=amount,
            duration_days=duration_days,
            invoice_payload=invoice_payload,
        )
        return await self.add(payment)

    async def get_by_payload(self, invoice_payload: str) -> Payment | None:
        stmt = (
            select(Payment)
            .where(Payment.invoice_payload == invoice_payload)
            .order_by(Payment.id.desc())
            .limit(1)
        )
        result = await self.session.scalars(stmt)
        return result.first()

    async def get_by_provider_payment_id(
        self, provider: PaymentProvider, provider_payment_id: str
    ) -> Payment | None:
        stmt = select(Payment).where(
            Payment.provider == provider,
            Payment.provider_payment_id == provider_payment_id,
        )
        result = await self.session.scalars(stmt)
        return result.first()

    async def mark_paid(
        self,
        payment_id: int,
        *,
        provider_payment_id: str | None,
        subscription_id: int | None,
        paid_at: datetime | None = None,
    ) -> Payment | None:
        values: dict[str, Any] = {
            "status": PaymentStatus.PAID,
            "paid_at": paid_at or datetime.now(tz=UTC),
            "provider_payment_id": provider_payment_id,
            "subscription_id": subscription_id,
        }
        stmt = (
            update(Payment)
            .where(Payment.id == payment_id)
            .values(**values)
            .returning(Payment)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_failed(self, payment_id: int) -> None:
        stmt = (
            update(Payment)
            .where(Payment.id == payment_id)
            .values(status=PaymentStatus.FAILED)
        )
        await self.session.execute(stmt)

    async def aggregate_revenue(
        self, *, since: datetime | None = None, currency: str = "XTR"
    ) -> int:
        """Сумма успешных платежей в указанной валюте."""
        stmt = select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == PaymentStatus.PAID,
            Payment.currency == currency,
        )
        if since is not None:
            stmt = stmt.where(Payment.paid_at >= since)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def count_paid(self, *, since: datetime | None = None) -> int:
        stmt = select(func.count(Payment.id)).where(
            Payment.status == PaymentStatus.PAID
        )
        if since is not None:
            stmt = stmt.where(Payment.paid_at >= since)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def count_paid_last_days(self, days: int) -> int:
        return await self.count_paid(since=datetime.now(tz=UTC) - timedelta(days=days))


__all__ = ["PaymentRepository"]
