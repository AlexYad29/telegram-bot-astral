"""История раскладов Таро — нужна и для UX («посмотреть предыдущий расклад»),
и для аналитики, и для anti-abuse (rate limit по типу расклада)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Enum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.enums import TarotSpreadKind
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class TarotHistory(TimestampMixin, Base):
    __tablename__ = "tarot_history"
    __table_args__ = (
        Index("ix_tarot_history_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    spread_kind: Mapped[TarotSpreadKind] = mapped_column(
        Enum(TarotSpreadKind, name="tarot_spread_kind", native_enum=False, length=16),
        nullable=False,
        default=TarotSpreadKind.THREE_CARD,
    )

    # Карты — JSONB-массив: [{"position": "past", "name": "The Fool", "reversed": false}, ...]
    cards: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)

    interpretation: Mapped[str] = mapped_column(Text, nullable=False)

    user: Mapped[User] = relationship(back_populates="tarot_history")

    def __repr__(self) -> str:
        return (
            f"<TarotHistory id={self.id} user_id={self.user_id} "
            f"spread={self.spread_kind!s}>"
        )


__all__ = ["TarotHistory"]
