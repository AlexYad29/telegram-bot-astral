"""Реферальная программа.

Запись «X пригласил Y». Гарантируется:
  - один пользователь имеет ровно одного `referrer` (UNIQUE на referred_user_id);
  - нельзя самому себя реферить (проверяется на уровне сервиса);
  - бонус выдаётся ровно один раз (`reward_granted_at`).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class Referral(TimestampMixin, Base):
    __tablename__ = "referrals"
    __table_args__ = (
        UniqueConstraint("referred_user_id", name="uq_referrals_referred_user_id"),
        Index("ix_referrals_referrer_user_id", "referrer_user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    referrer_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    referred_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Когда бонус был фактически выдан обеим сторонам. NULL — ещё не выдан
    # (юзер не прошёл условия активации, например ещё не зарегистрировал профиль).
    reward_granted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    referrer: Mapped[User] = relationship(
        foreign_keys=[referrer_user_id],
        back_populates="referrals_made",
    )
    referred: Mapped[User] = relationship(
        foreign_keys=[referred_user_id],
        back_populates="referral_source",
    )

    def __repr__(self) -> str:
        return (
            f"<Referral id={self.id} "
            f"referrer={self.referrer_user_id} → referred={self.referred_user_id} "
            f"rewarded={self.reward_granted_at is not None}>"
        )


__all__ = ["Referral"]
