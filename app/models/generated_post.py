"""Авто-пост, который планировщик публикует в Telegram-канал."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.models.enums import PostKind, PostStatus
from app.models.mixins import TimestampMixin


class GeneratedPost(TimestampMixin, Base):
    __tablename__ = "generated_posts"
    __table_args__ = (
        Index("ix_generated_posts_status_scheduled", "status", "scheduled_for"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    kind: Mapped[PostKind] = mapped_column(
        Enum(PostKind, name="post_kind", native_enum=False, length=32),
        nullable=False,
    )
    status: Mapped[PostStatus] = mapped_column(
        Enum(PostStatus, name="post_status", native_enum=False, length=16),
        nullable=False,
        default=PostStatus.SCHEDULED,
    )

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    channel_id: Mapped[str] = mapped_column(String(64), nullable=False)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<GeneratedPost id={self.id} kind={self.kind!s} "
            f"status={self.status!s} scheduled_for={self.scheduled_for.isoformat()}>"
        )


__all__ = ["GeneratedPost"]
