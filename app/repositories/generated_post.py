"""Репозиторий авто-постов в канал."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update

from app.models.enums import PostKind, PostStatus
from app.models.generated_post import GeneratedPost
from app.repositories.base import BaseRepository


class GeneratedPostRepository(BaseRepository[GeneratedPost]):
    model = GeneratedPost

    async def create(
        self,
        *,
        kind: PostKind,
        body: str,
        channel_id: str,
        scheduled_for: datetime,
        title: str | None = None,
    ) -> GeneratedPost:
        post = GeneratedPost(
            kind=kind,
            body=body,
            channel_id=channel_id,
            scheduled_for=scheduled_for,
            title=title,
            status=PostStatus.SCHEDULED,
        )
        return await self.add(post)

    async def count_by_status(self) -> dict[PostStatus, int]:
        """`{SCHEDULED: 5, SENT: 120, FAILED: 1}` — для админ-статистики."""
        stmt = select(GeneratedPost.status, func.count(GeneratedPost.id)).group_by(
            GeneratedPost.status
        )
        result = await self.session.execute(stmt)
        return {status: int(count) for status, count in result.all()}

    async def count_by_kind_since(
        self, threshold: datetime
    ) -> dict[PostKind, int]:
        """Сколько постов каждого вида создано не раньше `threshold`."""
        stmt = (
            select(GeneratedPost.kind, func.count(GeneratedPost.id))
            .where(GeneratedPost.scheduled_for >= threshold)
            .group_by(GeneratedPost.kind)
        )
        result = await self.session.execute(stmt)
        return {kind: int(count) for kind, count in result.all()}

    async def last_n(self, limit: int = 5) -> Sequence[GeneratedPost]:
        """Последние `limit` записей по `scheduled_for` — для админ-просмотра."""
        stmt = (
            select(GeneratedPost)
            .order_by(GeneratedPost.scheduled_for.desc())
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return result.all()

    async def list_due(self, *, now: datetime, limit: int = 50) -> Sequence[GeneratedPost]:
        stmt = (
            select(GeneratedPost)
            .where(
                GeneratedPost.status == PostStatus.SCHEDULED,
                GeneratedPost.scheduled_for <= now,
            )
            .order_by(GeneratedPost.scheduled_for.asc())
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return result.all()

    async def mark_sent(
        self, post_id: int, *, telegram_message_id: int, sent_at: datetime
    ) -> None:
        stmt = (
            update(GeneratedPost)
            .where(GeneratedPost.id == post_id)
            .values(
                status=PostStatus.SENT,
                telegram_message_id=telegram_message_id,
                sent_at=sent_at,
            )
        )
        await self.session.execute(stmt)

    async def mark_failed(self, post_id: int, *, error: str) -> None:
        stmt = (
            update(GeneratedPost)
            .where(GeneratedPost.id == post_id)
            .values(status=PostStatus.FAILED, error=error[:2000])
        )
        await self.session.execute(stmt)


__all__ = ["GeneratedPostRepository"]
