"""Репозиторий истории раскладов Таро."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select

from app.models.enums import TarotSpreadKind
from app.models.tarot_history import TarotHistory
from app.repositories.base import BaseRepository


class TarotHistoryRepository(BaseRepository[TarotHistory]):
    model = TarotHistory

    async def create(
        self,
        *,
        user_id: int,
        spread_kind: TarotSpreadKind,
        cards: list[dict[str, Any]],
        interpretation: str,
    ) -> TarotHistory:
        entry = TarotHistory(
            user_id=user_id,
            spread_kind=spread_kind,
            cards=cards,
            interpretation=interpretation,
        )
        return await self.add(entry)

    async def last_for_user(self, user_id: int, limit: int = 5) -> Sequence[TarotHistory]:
        stmt = (
            select(TarotHistory)
            .where(TarotHistory.user_id == user_id)
            .order_by(TarotHistory.created_at.desc())
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return result.all()


__all__ = ["TarotHistoryRepository"]
