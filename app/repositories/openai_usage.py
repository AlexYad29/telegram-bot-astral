"""Репозиторий логов OpenAI usage'а.

Используется UsageTracker для записи каждой строки, и `/admin_usage` —
для агрегатов за период.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Integer, cast, func, select

from app.models.openai_usage import OpenAIUsage
from app.repositories.base import BaseRepository


@dataclass(frozen=True, slots=True)
class UsageAggregate:
    """Срез usage'а за период — для отчётов."""

    requests: int
    cache_hits: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_micro_cents: int


@dataclass(frozen=True, slots=True)
class TaskBreakdownRow:
    """Строка отчёта по конкретной задаче."""

    task: str
    requests: int
    total_tokens: int
    cost_micro_cents: int


class OpenAIUsageRepository(BaseRepository[OpenAIUsage]):
    model = OpenAIUsage

    async def log(
        self,
        *,
        user_id: int | None,
        task: str,
        model: str,
        tier: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        cost_micro_cents: int,
        cache_hit: bool,
    ) -> OpenAIUsage:
        row = OpenAIUsage(
            user_id=user_id,
            task=task,
            model=model,
            tier=tier,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_micro_cents=cost_micro_cents,
            cache_hit=cache_hit,
        )
        return await self.add(row)

    async def aggregate_since(self, since: datetime) -> UsageAggregate:
        """Сумма usage'а за период `[since, now]`."""
        stmt = select(
            func.count(OpenAIUsage.id),
            func.coalesce(
                func.sum(cast(OpenAIUsage.cache_hit, Integer)), 0
            ),
            func.coalesce(func.sum(OpenAIUsage.prompt_tokens), 0),
            func.coalesce(func.sum(OpenAIUsage.completion_tokens), 0),
            func.coalesce(func.sum(OpenAIUsage.total_tokens), 0),
            func.coalesce(func.sum(OpenAIUsage.cost_micro_cents), 0),
        ).where(OpenAIUsage.created_at >= since)
        result = await self.session.execute(stmt)
        row = result.one()
        requests, hits, pt, ct, tt, mc = row
        return UsageAggregate(
            requests=int(requests or 0),
            cache_hits=int(hits or 0),
            prompt_tokens=int(pt or 0),
            completion_tokens=int(ct or 0),
            total_tokens=int(tt or 0),
            cost_micro_cents=int(mc or 0),
        )

    async def task_breakdown_since(
        self, since: datetime, *, limit: int = 20
    ) -> Sequence[TaskBreakdownRow]:
        """Разбивка по задачам за период (для админ-отчёта)."""
        stmt = (
            select(
                OpenAIUsage.task,
                func.count(OpenAIUsage.id),
                func.coalesce(func.sum(OpenAIUsage.total_tokens), 0),
                func.coalesce(func.sum(OpenAIUsage.cost_micro_cents), 0),
            )
            .where(OpenAIUsage.created_at >= since)
            .group_by(OpenAIUsage.task)
            .order_by(func.sum(OpenAIUsage.cost_micro_cents).desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [
            TaskBreakdownRow(
                task=str(task),
                requests=int(req or 0),
                total_tokens=int(tt or 0),
                cost_micro_cents=int(mc or 0),
            )
            for task, req, tt, mc in result.all()
        ]


__all__ = [
    "OpenAIUsageRepository",
    "TaskBreakdownRow",
    "UsageAggregate",
]
