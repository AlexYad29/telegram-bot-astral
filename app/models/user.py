"""ORM-модель пользователя бота.

`id` совпадает с Telegram user_id — для Telegram это безопасно (он стабилен и уникален),
экономит JOIN'ы и упрощает кэширование.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.enums import Gender
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.compatibility_check import CompatibilityCheck
    from app.models.payment import Payment
    from app.models.referral import Referral
    from app.models.subscription import Subscription
    from app.models.tarot_history import TarotHistory


class User(TimestampMixin, Base):
    __tablename__ = "users"

    # Telegram user_id — стабильный 64-битный идентификатор.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)

    # Поля, приходящие из Telegram (могут меняться).
    telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telegram_first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    telegram_last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # Анкета пользователя — заполняется через FSM-регистрацию /profile.
    full_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[Gender | None] = mapped_column(
        Enum(Gender, name="gender", native_enum=False, length=16),
        nullable=True,
    )

    # Сервисные флаги.
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    subscriptions: Mapped[list[Subscription]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    tarot_history: Mapped[list[TarotHistory]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    compatibility_checks: Mapped[list[CompatibilityCheck]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    payments: Mapped[list[Payment]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    referrals_made: Mapped[list[Referral]] = relationship(
        foreign_keys="Referral.referrer_user_id",
        back_populates="referrer",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    referral_source: Mapped[Referral | None] = relationship(
        foreign_keys="Referral.referred_user_id",
        back_populates="referred",
        cascade="all, delete-orphan",
        lazy="raise",
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.telegram_username!r}>"

    @property
    def is_registered(self) -> bool:
        """Профиль считается заполненным, если у нас есть дата рождения."""
        return self.birth_date is not None


__all__ = ["User"]
