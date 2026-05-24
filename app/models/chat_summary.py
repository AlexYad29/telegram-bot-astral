"""Сжатая «память» о пользователе для AI-диалогов.

Один summary на пользователя. Обновляется фоновым шагом, когда история
сообщений превышает порог из настроек (`ai_summary_trigger_messages`).
Сюда уезжают интересы, стиль общения, важные факты — всё, что нужно вернуть
в системный промпт без отправки всей истории.

Длина намеренно ограничена `ai_summary_max_chars` — храним *компрессию*,
не лог.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class ChatSummary(TimestampMixin, Base):
    __tablename__ = "chat_summaries"

    # 1 строка = 1 пользователь, поэтому user_id = PK.
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        autoincrement=False,
    )

    summary_text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # На сколько последних сообщений построен текущий summary (для триггера
    # пересборки и для отладки).
    messages_covered: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    user: Mapped[User] = relationship()

    def __repr__(self) -> str:
        return (
            f"<ChatSummary user_id={self.user_id} "
            f"chars={len(self.summary_text)} covered={self.messages_covered}>"
        )


__all__ = ["ChatSummary"]
