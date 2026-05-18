"""Репозиторий проверок совместимости."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select

from app.models.compatibility_check import CompatibilityCheck
from app.repositories.base import BaseRepository


class CompatibilityCheckRepository(BaseRepository[CompatibilityCheck]):
    model = CompatibilityCheck

    async def create(
        self,
        *,
        user_id: int,
        user_birth_date: date,
        partner_birth_date: date,
        emotional_score: int,
        conflict_score: int,
        romance_score: int,
        karmic_score: int,
        interpretation: str,
    ) -> CompatibilityCheck:
        check = CompatibilityCheck(
            user_id=user_id,
            user_birth_date=user_birth_date,
            partner_birth_date=partner_birth_date,
            emotional_score=emotional_score,
            conflict_score=conflict_score,
            romance_score=romance_score,
            karmic_score=karmic_score,
            interpretation=interpretation,
        )
        return await self.add(check)

    async def history_for_user(
        self, user_id: int, limit: int = 5
    ) -> Sequence[CompatibilityCheck]:
        stmt = (
            select(CompatibilityCheck)
            .where(CompatibilityCheck.user_id == user_id)
            .order_by(CompatibilityCheck.created_at.desc())
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return result.all()


__all__ = ["CompatibilityCheckRepository"]
