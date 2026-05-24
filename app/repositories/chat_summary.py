"""Репозиторий компактных summary-памяти на пользователя."""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.chat_summary import ChatSummary
from app.repositories.base import BaseRepository


class ChatSummaryRepository(BaseRepository[ChatSummary]):
    model = ChatSummary

    async def get_for_user(self, user_id: int) -> ChatSummary | None:
        return await self.session.get(ChatSummary, user_id)

    async def upsert(
        self,
        *,
        user_id: int,
        summary_text: str,
        messages_covered: int,
    ) -> ChatSummary:
        """Перезаписать summary пользователя одним атомарным upsert'ом."""
        stmt = (
            pg_insert(ChatSummary)
            .values(
                user_id=user_id,
                summary_text=summary_text,
                messages_covered=messages_covered,
            )
            .on_conflict_do_update(
                index_elements=[ChatSummary.user_id],
                set_={
                    "summary_text": summary_text,
                    "messages_covered": messages_covered,
                },
            )
            .returning(ChatSummary)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()


__all__ = ["ChatSummaryRepository"]
