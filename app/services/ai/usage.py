"""Сбор usage'а OpenAI: токены, стоимость, cache hit/miss.

Один вызов `UsageTracker.record_call(...)` — одна строка в `openai_usage`
плюс быстрые Redis-счётчики на «сейчас» (для дашбордов / алертов).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config.settings import Settings
from app.repositories.openai_usage import (
    OpenAIUsageRepository,
    TaskBreakdownRow,
    UsageAggregate,
)
from app.services.ai.tasks import AITask, ModelTier, TaskConfig
from app.services.ai.tokens import (
    TokenUsage,
    estimate_cost_usd,
    from_micro_cents,
    to_micro_cents,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


_REDIS_NS = "ai:usage"
_PERIODS_HOURS = (24, 24 * 7, 24 * 30)
_REDIS_TTL_DEFAULT = 31 * 24 * 3600  # держим месячные счётчики 31 день


@dataclass(frozen=True, slots=True)
class UsageReport:
    """Снимок usage'а за период — для админ-отчёта."""

    label: str  # "24h" / "7d" / "30d"
    since: datetime
    aggregate: UsageAggregate
    by_task: tuple[TaskBreakdownRow, ...]

    @property
    def cost_usd(self) -> float:
        return from_micro_cents(self.aggregate.cost_micro_cents)


class UsageTracker:
    """Запись usage'а OpenAI + быстрые отчёты за период.

    DB-строка — основной источник правды (для аналитики / audit).
    Redis-счётчики — для быстрых «сейчас за N часов» виджетов и rate-limit
    логики; не критично потерять при перезапуске.
    """

    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession],
        redis: Redis | None,
        settings: Settings,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._redis = redis
        self._settings = settings

    async def record_call(
        self,
        *,
        config: TaskConfig,
        user_id: int | None,
        usage: TokenUsage,
        cache_hit: bool,
    ) -> None:
        """Логируем один вызов: 1 row в DB + 4 Redis-счётчика."""
        cost_usd = (
            0.0
            if cache_hit
            else estimate_cost_usd(
                model=config.model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                settings=self._settings,
            )
        )
        cost_mc = to_micro_cents(cost_usd)
        try:
            async with self._sessionmaker() as session:
                repo = OpenAIUsageRepository(session)
                await repo.log(
                    user_id=user_id,
                    task=config.task.value,
                    model=config.model,
                    tier=config.tier.value,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    total_tokens=usage.total_tokens,
                    cost_micro_cents=cost_mc,
                    cache_hit=cache_hit,
                )
                await session.commit()
        except Exception:
            # Не валим основной флоу из-за метрик — только логируем.
            logger.exception(
                "failed to persist OpenAI usage row task=%s model=%s",
                config.task.value,
                config.model,
            )

        if self._redis is None:
            return
        try:
            now = datetime.now(tz=UTC)
            await self._bump_counters(
                now=now,
                task=config.task,
                tier=config.tier,
                usage=usage,
                cost_micro_cents=cost_mc,
                cache_hit=cache_hit,
            )
        except Exception:
            logger.debug("failed to bump Redis usage counters", exc_info=True)

    async def _bump_counters(
        self,
        *,
        now: datetime,
        task: AITask,
        tier: ModelTier,
        usage: TokenUsage,
        cost_micro_cents: int,
        cache_hit: bool,
    ) -> None:
        if self._redis is None:
            return
        # Один hour-бакет — общий и per-task. На клиенте суммируем.
        hour_key = now.strftime("%Y%m%d%H")
        keys = (
            f"{_REDIS_NS}:hour:{hour_key}",
            f"{_REDIS_NS}:hour:{hour_key}:task:{task.value}",
            f"{_REDIS_NS}:hour:{hour_key}:tier:{tier.value}",
        )
        pipe = self._redis.pipeline()
        for key in keys:
            pipe.hincrby(key, "requests", 1)
            pipe.hincrby(key, "prompt_tokens", usage.prompt_tokens)
            pipe.hincrby(key, "completion_tokens", usage.completion_tokens)
            pipe.hincrby(key, "total_tokens", usage.total_tokens)
            pipe.hincrby(key, "cost_mc", cost_micro_cents)
            if cache_hit:
                pipe.hincrby(key, "cache_hits", 1)
            pipe.expire(key, _REDIS_TTL_DEFAULT)
        await pipe.execute()

    # ---------- Отчёты ----------
    async def report_for_period(
        self, *, hours: int, label: str
    ) -> UsageReport:
        """Сводный отчёт за последние `hours` часов из БД."""
        since = datetime.now(tz=UTC) - timedelta(hours=hours)
        async with self._sessionmaker() as session:
            repo = OpenAIUsageRepository(session)
            agg = await repo.aggregate_since(since)
            by_task = tuple(await repo.task_breakdown_since(since))
        return UsageReport(
            label=label,
            since=since,
            aggregate=agg,
            by_task=by_task,
        )

    async def reports_overview(self) -> tuple[UsageReport, ...]:
        """24h / 7d / 30d — три отчёта одним вызовом."""
        labels = ("24h", "7d", "30d")
        reports: list[UsageReport] = []
        for hours, label in zip(_PERIODS_HOURS, labels, strict=True):
            reports.append(await self.report_for_period(hours=hours, label=label))
        return tuple(reports)


__all__ = ["UsageReport", "UsageTracker"]
