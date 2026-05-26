"""Платёж пользователя за подписку.

Связан с Subscription many-to-one (одна подписка может прийти от
нескольких продлений/попыток), плюс хранит provider-specific payload
(charge_id, transaction id, raw payload для аудита).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.enums import (
    PaymentProvider,
    PaymentStatus,
    SubscriptionPlan,
)
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.subscription import Subscription
    from app.models.user import User


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_user_status", "user_id", "status"),
        Index("ix_payments_provider_payment_id", "provider", "provider_payment_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    subscription_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
    )

    provider: Mapped[PaymentProvider] = mapped_column(
        Enum(PaymentProvider, name="payment_provider", native_enum=False, length=24),
        nullable=False,
    )
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", native_enum=False, length=16),
        nullable=False,
        default=PaymentStatus.PENDING,
    )
    plan: Mapped[SubscriptionPlan] = mapped_column(
        Enum(SubscriptionPlan, name="subscription_plan", native_enum=False, length=16),
        nullable=False,
    )

    # Сумма в минимальной единице валюты:
    #   - для XTR (Telegram Stars) — целое число звёзд;
    #   - для RUB/USD — копейки/центы (Telegram payments API именно так и
    #     принимает amount).
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)

    # Длительность, которую покупаем (в днях). Удобно хранить рядом, чтобы
    # не вычислять заново при обработке successful_payment.
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)

    # ID на стороне платёжного провайдера. Для Stars — telegram_payment_charge_id.
    provider_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # ID на стороне продавца. Удобно искать в логах.
    invoice_payload: Mapped[str | None] = mapped_column(String(128), nullable=True)

    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="payments")
    subscription: Mapped[Subscription | None] = relationship(back_populates="payments")

    def __repr__(self) -> str:
        return (
            f"<Payment id={self.id} user_id={self.user_id} "
            f"provider={self.provider!s} status={self.status!s} "
            f"plan={self.plan!s} amount={self.amount} {self.currency}>"
        )


__all__ = ["Payment"]
