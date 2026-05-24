"""Репозиторий сырого диалога (sliding-window memory)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select

from app.models.chat_message import ChatMessage, ChatRole
from app.repositories.base import BaseRepository


class ChatMessageRepository(BaseRepository[ChatMessage]):
    model = ChatMessage

    async def add_message(
        self,
        *,
        user_id: int,
        role: ChatRole,
        content: str,
        tokens: int = 0,
    ) -> ChatMessage:
        msg = ChatMessage(
            user_id=user_id,
            role=role,
            content=content,
            tokens=tokens,
        )
        return await self.add(msg)

    async def last_n(self, user_id: int, limit: int) -> Sequence[ChatMessage]:
        """Последние `limit` сообщений пользователя в порядке возрастания времени.

        Sliding-window нам нужен в хронологическом порядке (старые → новые),
        поэтому забираем DESC, потом разворачиваем на стороне Python — это
        дешевле, чем гонять отдельный subquery.
        """
        if limit <= 0:
            return []
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        rows = list(result.all())
        rows.reverse()
        return rows

    async def count_for_user(self, user_id: int) -> int:
        stmt = select(func.count(ChatMessage.id)).where(
            ChatMessage.user_id == user_id
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def older_than(
        self, user_id: int, *, cutoff: datetime, limit: int = 100
    ) -> Sequence[ChatMessage]:
        """Сообщения старше `cutoff` (для суммаризации перед удалением)."""
        stmt = (
            select(ChatMessage)
            .where(
                ChatMessage.user_id == user_id,
                ChatMessage.created_at < cutoff,
            )
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return result.all()

    async def delete_older_than(self, user_id: int, *, cutoff: datetime) -> int:
        """Удалить сообщения пользователя старше `cutoff` (после суммаризации).

        Возвращает количество удалённых строк.
        """
        stmt = sa_delete(ChatMessage).where(
            ChatMessage.user_id == user_id,
            ChatMessage.created_at < cutoff,
        )
        result = await self.session.execute(stmt)
        return result.rowcount or 0


__all__ = ["ChatMessageRepository"]
