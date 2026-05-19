"""AI service layer.

Бизнес-логика поверх `AIClient`: знает, какие промпты собирать и куда подставлять
данные пользователя. Хендлеры зовут именно `AIService`, а не клиент напрямую —
это позволяет менять модели и формулировки без правок в роутерах.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Protocol

from app.models.enums import Gender, PostKind
from app.models.user import User as DbUser
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


class AIService:
    """Фасад над `AIClient` с готовыми сценариями генерации."""

    def __init__(self, client: AIClient) -> None:
        self._client = client

    async def generate_daily_forecast(
        self,
        user: DbUser | None,
        *,
        today: date | None = None,
    ) -> str:
        prompt = build_daily_forecast_prompt(
            _ctx_from_user(user),
            today=today or date.today(),
        )
        return await self._client.complete(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
        )

    async def generate_mystical_message(self, theme: str | None = None) -> str:
        prompt = build_mystical_message_prompt(theme)
        return await self._client.complete(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            # для коротких канал-постов — меньше токенов, больше «плотности».
            max_tokens=300,
        )

    async def generate_esoteric_answer(
        self,
        question: str,
        user: DbUser | None,
    ) -> str:
        prompt = build_esoteric_answer_prompt(question, _ctx_from_user(user))
        return await self._client.complete(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
        )

    async def generate_tarot_interpretation(
        self,
        *,
        user: DbUser | None,
        question: str | None,
        cards: tuple[TarotCardContext, ...],
    ) -> str:
        """Сгенерировать связное толкование трёхкарточного расклада."""
        prompt = build_tarot_interpretation_prompt(
            user=_ctx_from_user(user),
            question=question,
            cards=cards,
        )
        return await self._client.complete(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=600,
        )

    async def generate_channel_post(
        self,
        *,
        kind: PostKind,
        today: date,
        day_number: int | None = None,
    ) -> str:
        """Сгенерировать тело автопоста в канал.

        `day_number` обязателен только для `PostKind.DAY_NUMBER` — это уже
        вычисленное число дня (1..9 или мастер 11/22/33). Если для остальных
        видов он передан — игнорируется.
        """
        if kind is PostKind.DAY_FORECAST:
            prompt = build_channel_day_forecast_prompt(today=today)
            max_tokens = 500
        elif kind is PostKind.DAY_NUMBER:
            if day_number is None:
                raise ValueError("day_number обязателен для PostKind.DAY_NUMBER")
            prompt = build_channel_day_number_prompt(today=today, day_number=day_number)
            max_tokens = 350
        elif kind is PostKind.DAY_ENERGY:
            prompt = build_channel_day_energy_prompt(today=today)
            max_tokens = 350
        elif kind is PostKind.MYSTICAL_WARNING:
            prompt = build_channel_mystical_warning_prompt(today=today)
            max_tokens = 350
        elif kind is PostKind.VIRAL:
            prompt = build_channel_viral_prompt(today=today)
            max_tokens = 350
        else:  # pragma: no cover — защита от добавления нового PostKind без правки.
            raise ValueError(f"неподдерживаемый PostKind: {kind!s}")
        return await self._client.complete(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=max_tokens,
        )

    async def generate_compatibility_interpretation(
        self,
        *,
        user: DbUser,
        partner_name: str,
        partner_birth_date: date,
        scores: CompatibilityScoresProtocol,
    ) -> str:
        """Сгенерировать развёрнутую интерпретацию совместимости.

        `scores` принимаем как Protocol — чтобы не тащить сюда сервис
        нумерологии и не плодить циклические импорты.
        """
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
        return await self._client.complete(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=600,
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
