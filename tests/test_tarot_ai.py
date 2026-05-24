"""Тесты AI-обёртки для расклада Таро."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pytest

from app.models.enums import Gender
from app.models.user import User as DbUser
from app.services.ai.prompts import (
    SYSTEM_PROMPT,
    TarotCardContext,
    build_tarot_interpretation_prompt,
)
from app.services.ai.service import AIService


@dataclass
class FakeAIClient:
    reply: str = "карты заговорили"
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        return self.reply


def _user() -> DbUser:
    user = DbUser()
    user.id = 7
    user.full_name = "Лиза"
    user.birth_date = date(1995, 6, 15)
    user.gender = Gender.FEMALE
    return user


def _cards() -> tuple[TarotCardContext, ...]:
    return (
        TarotCardContext(
            position_label="Прошлое",
            name_ru="Шут",
            name_en="The Fool",
            reversed=False,
            keywords=("начало", "наивность"),
            meaning_short="свежий старт",
        ),
        TarotCardContext(
            position_label="Настоящее",
            name_ru="Башня",
            name_en="The Tower",
            reversed=True,
            keywords=("слом", "молния"),
            meaning_short="отсрочка неизбежного",
        ),
        TarotCardContext(
            position_label="Будущее",
            name_ru="Звезда",
            name_en="The Star",
            reversed=False,
            keywords=("надежда", "свет"),
            meaning_short="возвращается вера",
        ),
    )


def test_build_tarot_prompt_includes_all_cards_and_positions() -> None:
    prompt = build_tarot_interpretation_prompt(
        user=_user_ctx(),
        question="Что делать с работой?",
        cards=_cards(),
    )
    for label in ("Прошлое", "Настоящее", "Будущее"):
        assert label in prompt
    assert "Шут" in prompt and "The Fool" in prompt
    assert "Башня" in prompt and "The Tower" in prompt
    assert "Звезда" in prompt and "The Star" in prompt
    # перевёрнутость карт фиксируется в промпте
    assert "перевёрнутом положении" in prompt
    assert "в прямом положении" in prompt
    # ключевые слова подтянуты
    assert "начало" in prompt
    assert "Что делать с работой?" in prompt


def test_build_tarot_prompt_handles_missing_question() -> None:
    prompt = build_tarot_interpretation_prompt(
        user=_user_ctx(),
        question=None,
        cards=_cards(),
    )
    assert "Вопрос не сформулирован" in prompt


def test_build_tarot_prompt_handles_blank_question() -> None:
    prompt = build_tarot_interpretation_prompt(
        user=_user_ctx(),
        question="   ",
        cards=_cards(),
    )
    assert "Вопрос не сформулирован" in prompt


@pytest.mark.asyncio
async def test_service_passes_full_context_and_system_prompt() -> None:
    fake = FakeAIClient(reply="прочитано")
    service = AIService(fake)
    user = _user()
    cards = _cards()

    result = await service.generate_tarot_interpretation(
        user=user,
        question="Как быть с переездом?",
        cards=cards,
    )

    assert result == "прочитано"
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["system_prompt"] == SYSTEM_PROMPT
    assert call["max_tokens"] == 600
    user_prompt = call["user_prompt"]
    assert "Лиза" in user_prompt
    assert "1995-06-15" in user_prompt
    assert "Как быть с переездом?" in user_prompt
    for card in cards:
        assert card.name_ru in user_prompt


@pytest.mark.asyncio
async def test_service_works_for_anonymous_user() -> None:
    fake = FakeAIClient()
    service = AIService(fake)
    await service.generate_tarot_interpretation(
        user=None,
        question=None,
        cards=_cards(),
    )
    assert len(fake.calls) == 1
    # Имя в промпте не должно появиться — анонимный пользователь
    assert "Лиза" not in fake.calls[0]["user_prompt"]


def _user_ctx() -> Any:
    from app.services.ai.prompts import UserContext

    return UserContext(
        full_name="Лиза",
        birth_date=date(1995, 6, 15),
        gender=Gender.FEMALE,
    )
