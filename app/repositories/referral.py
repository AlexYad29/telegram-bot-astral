"""Репозиторий реферальной программы."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.models.referral import Referral
from app.repositories.base import BaseRepository


class ReferralRepository(BaseRepository[Referral]):
    model = Referral

    async def attach(
        self, *, referrer_user_id: int, referred_user_id: int
    ) -> Referral | None:
        """Создать запись «X пригласил Y». UNIQUE на referred — повторно не создаст.

        Возвращает None, если referred уже привязан к другому referrer'у
        (или к этому же, не важно — UNIQUE сработал).
        """
        if referrer_user_id == referred_user_id:
            return None
        try:
            referral = Referral(
                referrer_user_id=referrer_user_id,
                referred_user_id=referred_user_id,
            )
            return await self.add(referral)
        except IntegrityError:
            await self.session.rollback()
            return None

    async def get_for_referred(self, referred_user_id: int) -> Referral | None:
        stmt = select(Referral).where(Referral.referred_user_id == referred_user_id)
        result = await self.session.scalars(stmt)
        return result.first()

    async def mark_rewarded(
        self, referred_user_id: int, *, granted_at: datetime | None = None
    ) -> Referral | None:
        stmt = (
            update(Referral)
            .where(
                Referral.referred_user_id == referred_user_id,
                Referral.reward_granted_at.is_(None),
            )
            .values(reward_granted_at=granted_at or datetime.now(tz=UTC))
            .returning(Referral)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_for_referrer(
        self, referrer_user_id: int, *, only_rewarded: bool = False
    ) -> int:
        stmt = select(func.count(Referral.id)).where(
            Referral.referrer_user_id == referrer_user_id
        )
        if only_rewarded:
            stmt = stmt.where(Referral.reward_granted_at.is_not(None))
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def total(self, *, only_rewarded: bool = False) -> int:
        stmt = select(func.count(Referral.id))
        if only_rewarded:
            stmt = stmt.where(Referral.reward_granted_at.is_not(None))
        result = await self.session.execute(stmt)
        return int(result.scalar_one())


__all__ = ["ReferralRepository"]
