"""AI service layer.

Бизнес-логика поверх `AIClient`: знает, какие промпты собирать, какую модель
выбрать (Nano/Mini), нужно ли кэшировать ответ и как залогировать usage.
Хендлеры зовут именно `AIService`, а не клиент напрямую — это позволяет
менять модели и формулировки без правок в роутерах.

ETAP 12 — добавлено:

* model routing через `AITask` / `task_config_for(...)` (Nano для канала и
  массового, Mini — для tarot / compatibility / dialogs);
* Redis-кэш канал-постов и daily forecast (через `AICache`);
* запись токенов и стоимости в `OpenAIUsage` (через `UsageTracker`);
* per-task `max_tokens` и `temperature` из `Settings`.

Все новые зависимости (cache / tracker) опциональны — без них сервис ведёт
себя как в ETAP 5: просто зовёт OpenAI с заданной моделью.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Protocol

from app.config.settings import Settings
from app.models.enums import Gender, PostKind
from app.models.user import User as DbUser
from app.services.ai.cache import (
    AICache,
    make_channel_post_key,
    make_compatibility_key,
    make_daily_forecast_key,
    make_esoteric_answer_key,
)
from app.services.ai.client import AIClient
from app.services.ai.prompts import (
    SYSTEM_PROMPT,
    CompatibilityContext,
    TarotCardContext,
    UserContext,
    build_channel_day_energy_prompt,
    build_channel_day_forecast_prompt,
    build_channel_day_number_prompt,
    build_channel_mystical_warning_prompt,
    build_channel_viral_prompt,
    build_compatibility_prompt,
    build_daily_forecast_prompt,
    build_esoteric_answer_prompt,
    build_mystical_message_prompt,
    build_tarot_interpretation_prompt,
)
from app.services.ai.tasks import AITask, TaskConfig, task_config_for
from app.services.ai.tokens import TokenUsage
from app.services.ai.usage import UsageTracker

logger = logging.getLogger(__name__)


def _ctx_from_user(user: DbUser | None) -> UserContext:
    """Аккуратно собрать `UserContext` из ORM-объекта (может быть None)."""
    if user is None:
        return UserContext()
    gender: Gender | None = user.gender
    return UserContext(
        full_name=user.full_name,
        birth_date=user.birth_date,
        gender=gender,
    )


def _user_id_or_none(user: DbUser | None) -> int | None:
    return user.id if user is not None else None


class AIService:
    """Фасад над `AIClient` с готовыми сценариями генерации.

    Опциональные зависимости:

    * `settings` — если передан, используется per-task max_tokens / temperature
      и model routing. Без него падает на дефолты OpenAI client (для
      совместимости со старыми тестами).
    * `cache` — Redis-кэш канал-постов / daily forecast / esoteric Q&A.
    * `usage_tracker` — логирование token usage в БД и Redis-счётчики.
    """

    def __init__(
        self,
        client: AIClient,
        *,
        settings: Settings | None = None,
        cache: AICache | None = None,
        usage_tracker: UsageTracker | None = None,
    ) -> None:
        self._client = client
        self._settings = settings
        self._cache = cache
        self._tracker = usage_tracker

    # ---------- Внутренний универсальный путь ----------
    async def _run_task(
        self,
        *,
        task: AITask,
        user_prompt: str,
        user_id: int | None,
        cache_key: str | None = None,
        max_tokens_override: int | None = None,
    ) -> str:
        """Единая точка: cache lookup → LLM → cache set → usage tracking."""
        if self._settings is None:
            # Старый путь — для совместимости с тестами, которые передают
            # FakeAIClient без `chat_with_usage`. Без cache и без tracking.
            return await self._client.complete(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=max_tokens_override,
            )

        config = task_config_for(task, self._settings)
        max_tokens = max_tokens_override or config.max_tokens

        cached = await self._cache_get(config=config, key=cache_key)
        if cached:
            await self._record_usage(
                config=config,
                user_id=user_id,
                usage=TokenUsage(0, 0, 0),
                cache_hit=True,
            )
            return cached

        text, usage = await self._call_with_usage(
            config=config,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
        )
        if text and cache_key and config.cache_enabled:
            await self._cache_set(config=config, key=cache_key, value=text)
        await self._record_usage(
            config=config,
            user_id=user_id,
            usage=usage,
            cache_hit=False,
        )
        return text

    async def _call_with_usage(
        self,
        *,
        config: TaskConfig,
        user_prompt: str,
        max_tokens: int,
    ) -> tuple[str, TokenUsage]:
        """Запрос через `chat_with_usage`, fallback на `complete`."""
        chat_with_usage = getattr(self._client, "chat_with_usage", None)
        if chat_with_usage is None:
            text = await self._client.complete(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
                temperature=config.temperature,
                model=config.model,
            )
            return text, TokenUsage(0, 0, 0)
        return await chat_with_usage(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            model=config.model,
            max_tokens=max_tokens,
            temperature=config.temperature,
        )

    async def _cache_get(
        self, *, config: TaskConfig, key: str | None
    ) -> str | None:
        if not key or not config.cache_enabled or self._cache is None:
            return None
        try:
            return await self._cache.get(key)
        except Exception:
            logger.debug("AI cache get failed key=%s", key, exc_info=True)
            return None

    async def _cache_set(
        self, *, config: TaskConfig, key: str, value: str
    ) -> None:
        if self._cache is None:
            return
        try:
            await self._cache.set(key, value, ttl_seconds=config.cache_ttl_seconds)
        except Exception:
            logger.debug("AI cache set failed key=%s", key, exc_info=True)

    async def _record_usage(
        self,
        *,
        config: TaskConfig,
        user_id: int | None,
        usage: TokenUsage,
        cache_hit: bool,
    ) -> None:
        if self._tracker is None:
            return
        try:
            await self._tracker.record_call(
                config=config,
                user_id=user_id,
                usage=usage,
                cache_hit=cache_hit,
            )
        except Exception:
            logger.debug("usage tracker failed", exc_info=True)

    # ---------- Публичные сценарии ----------
    async def generate_daily_forecast(
        self,
        user: DbUser | None,
        *,
        today: date | None = None,
    ) -> str:
        """Прогноз дня под пользователя (Mini, кэш по user+day)."""
        the_day = today or date.today()
        prompt = build_daily_forecast_prompt(_ctx_from_user(user), today=the_day)
        cache_key = (
            make_daily_forecast_key(user_id=user.id, day=the_day)
            if user is not None
            else None
        )
        return await self._run_task(
            task=AITask.DAILY_FORECAST,
            user_prompt=prompt,
            user_id=_user_id_or_none(user),
            cache_key=cache_key,
        )

    async def generate_mystical_message(self, theme: str | None = None) -> str:
        """Короткое мистическое сообщение для канала (Nano, max 300 токенов)."""
        prompt = build_mystical_message_prompt(theme)
        return await self._run_task(
            task=AITask.MYSTICAL_MESSAGE,
            user_prompt=prompt,
            user_id=None,
            max_tokens_override=300,
        )

    async def generate_esoteric_answer(
        self,
        question: str,
        user: DbUser | None,
    ) -> str:
        """Ответ на эзотерический вопрос (Mini, кэш по hash вопроса)."""
        prompt = build_esoteric_answer_prompt(question, _ctx_from_user(user))
        cache_key = make_esoteric_answer_key(question)
        return await self._run_task(
            task=AITask.ESOTERIC_ANSWER,
            user_prompt=prompt,
            user_id=_user_id_or_none(user),
            cache_key=cache_key,
        )

    async def generate_tarot_interpretation(
        self,
        *,
        user: DbUser | None,
        question: str | None,
        cards: tuple[TarotCardContext, ...],
    ) -> str:
        """Толкование 3-карточного расклада (Mini, без кэша — каждое уникально)."""
        prompt = build_tarot_interpretation_prompt(
            user=_ctx_from_user(user),
            question=question,
            cards=cards,
        )
        return await self._run_task(
            task=AITask.TAROT_INTERPRETATION,
            user_prompt=prompt,
            user_id=_user_id_or_none(user),
            max_tokens_override=600,
        )

    async def generate_channel_post(
        self,
        *,
        kind: PostKind,
        today: date,
        day_number: int | None = None,
    ) -> str:
        """Тело автопоста для канала (Nano, кэш по kind+date)."""
        if kind is PostKind.DAY_FORECAST:
            prompt = build_channel_day_forecast_prompt(today=today)
            task = AITask.CHANNEL_DAY_FORECAST
            max_tokens = 500
        elif kind is PostKind.DAY_NUMBER:
            if day_number is None:
                raise ValueError("day_number обязателен для PostKind.DAY_NUMBER")
            prompt = build_channel_day_number_prompt(today=today, day_number=day_number)
            task = AITask.CHANNEL_DAY_NUMBER
            max_tokens = 350
        elif kind is PostKind.DAY_ENERGY:
            prompt = build_channel_day_energy_prompt(today=today)
            task = AITask.CHANNEL_DAY_ENERGY
            max_tokens = 350
        elif kind is PostKind.MYSTICAL_WARNING:
            prompt = build_channel_mystical_warning_prompt(today=today)
            task = AITask.CHANNEL_MYSTICAL_WARNING
            max_tokens = 350
        elif kind is PostKind.VIRAL:
            prompt = build_channel_viral_prompt(today=today)
            task = AITask.CHANNEL_VIRAL
            max_tokens = 350
        else:  # pragma: no cover — защита от добавления нового PostKind без правки.
            raise ValueError(f"неподдерживаемый PostKind: {kind!s}")
        cache_key = make_channel_post_key(task, day=today)
        return await self._run_task(
            task=task,
            user_prompt=prompt,
            user_id=None,
            cache_key=cache_key,
            max_tokens_override=max_tokens,
        )

    async def generate_compatibility_interpretation(
        self,
        *,
        user: DbUser,
        partner_name: str,
        partner_birth_date: date,
        scores: CompatibilityScoresProtocol,
    ) -> str:
        """Развёрнутая интерпретация совместимости (Mini, кэш по парe дат)."""
        ctx = CompatibilityContext(
            user=_ctx_from_user(user),
            partner_name=partner_name,
            partner_birth_date=partner_birth_date,
            user_life_path=scores.user_life_path,
            partner_life_path=scores.partner_life_path,
            emotional_score=scores.emotional_score,
            conflict_score=scores.conflict_score,
            romance_score=scores.romance_score,
            karmic_score=scores.karmic_score,
        )
        prompt = build_compatibility_prompt(ctx)
        user_dob = user.birth_date if user.birth_date is not None else date.today()
        cache_key = make_compatibility_key(user_dob, partner_birth_date)
        return await self._run_task(
            task=AITask.COMPATIBILITY_INTERPRETATION,
            user_prompt=prompt,
            user_id=_user_id_or_none(user),
            cache_key=cache_key,
            max_tokens_override=600,
        )


class CompatibilityScoresProtocol(Protocol):
    """Структурный контракт для скоров — реализуется `CompatibilityScores`."""

    user_life_path: int
    partner_life_path: int
    emotional_score: int
    conflict_score: int
    romance_score: int
    karmic_score: int


__all__ = ["AIService", "CompatibilityScoresProtocol", "TarotCardContext"]
