"""Запись о проверке совместимости двух дат рождения.

Хранит обе даты + 4 субскора (эмоция / конфликт / романтика / карма)
и развёрнутую AI-интерпретацию (этап 7).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, Date, ForeignKey, Index, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class CompatibilityCheck(TimestampMixin, Base):
    __tablename__ = "compatibility_checks"
    __table_args__ = (
        CheckConstraint("emotional_score BETWEEN 0 AND 100", name="emotional_score_range"),
        CheckConstraint("conflict_score BETWEEN 0 AND 100", name="conflict_score_range"),
        CheckConstraint("romance_score BETWEEN 0 AND 100", name="romance_score_range"),
        CheckConstraint("karmic_score BETWEEN 0 AND 100", name="karmic_score_range"),
        Index("ix_compatibility_checks_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    user_birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    partner_birth_date: Mapped[date] = mapped_column(Date, nullable=False)

    emotional_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    conflict_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    romance_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    karmic_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    interpretation: Mapped[str] = mapped_column(Text, nullable=False)

    user: Mapped[User] = relationship(back_populates="compatibility_checks")

    def __repr__(self) -> str:
        return (
            f"<CompatibilityCheck id={self.id} user_id={self.user_id} "
            f"partner={self.partner_birth_date.isoformat()}>"
        )


__all__ = ["CompatibilityCheck"]
