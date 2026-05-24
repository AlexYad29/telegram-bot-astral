"""Лог сообщений диалога для построения sliding-window memory.

Храним последние N реплик пользователь↔ассистент, чтобы:

* класть их в prompt (последние 3-5 — настраивается);
* поверх старых строить compact-summary в `chat_summaries`.

Не путать с `tarot_history`/`compatibility_checks` — там артефакты команд,
здесь сырой текстовый диалог.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Enum, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class ChatRole(StrEnum):
    """Роль сообщения в чате — совпадает с OpenAI role'ами."""

    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(TimestampMixin, Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        # Самый частый запрос — «последние N для user_id».
        Index("ix_chat_messages_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    role: Mapped[ChatRole] = mapped_column(
        Enum(ChatRole, name="chat_role", native_enum=False, length=16),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)

    # tokens на момент сохранения — поможет точно понимать, сколько весит окно
    # без повторного tiktoken-encode'а.
    tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    user: Mapped[User] = relationship()

    def __repr__(self) -> str:
        return (
            f"<ChatMessage id={self.id} user_id={self.user_id} role={self.role!s} "
            f"tokens={self.tokens}>"
        )


__all__ = ["ChatMessage", "ChatRole"]
