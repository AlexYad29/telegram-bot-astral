"""Подписка пользователя.

MVP стартует на free-планe, но схема готова под платную подписку:
plan + status + период действия + ссылки на платёжного провайдера.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.enums import SubscriptionPlan, SubscriptionStatus
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    plan: Mapped[SubscriptionPlan] = mapped_column(
        Enum(SubscriptionPlan, name="subscription_plan", native_enum=False, length=16),
        nullable=False,
        default=SubscriptionPlan.FREE,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status", native_enum=False, length=16),
        nullable=False,
        default=SubscriptionStatus.ACTIVE,
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    payment_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    user: Mapped[User] = relationship(back_populates="subscriptions")

    def __repr__(self) -> str:
        return (
            f"<Subscription id={self.id} user_id={self.user_id} "
            f"plan={self.plan!s} status={self.status!s}>"
        )


__all__ = ["Subscription"]
