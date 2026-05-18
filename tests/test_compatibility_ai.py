"""Тесты AI-обёртки для совместимости.

Проверяем, что:

* в промпт уходят все четыре субскора;
* фигурируют life path обоих партнёров;
* передаются имя/дата партнёра и `SYSTEM_PROMPT`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pytest

from app.models.enums import Gender
from app.models.user import User as DbUser
from app.services.ai.prompts import SYSTEM_PROMPT
from app.services.ai.service import AIService
from app.services.compatibility import calculate_scores


@dataclass
class FakeAIClient:
    reply: str = "лунный свет"
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


def _make_user() -> DbUser:
    user = DbUser()
    user.id = 42
    user.full_name = "Мария"
    user.birth_date = date(1990, 1, 1)
    user.gender = Gender.FEMALE
    return user


@pytest.mark.asyncio
async def test_compatibility_prompt_carries_all_signals() -> None:
    fake = FakeAIClient(reply="звёзды видят пару")
    service = AIService(fake)
    user = _make_user()
    partner_birth = date(1985, 10, 9)
    scores = calculate_scores(user.birth_date, partner_birth)

    result = await service.generate_compatibility_interpretation(
        user=user,
        partner_name="Алексей",
        partner_birth_date=partner_birth,
        scores=scores,
    )

    assert result == "звёзды видят пару"
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["system_prompt"] == SYSTEM_PROMPT
    assert "Мария" in call["user_prompt"]
    assert "Алексей" in call["user_prompt"]
    assert "1985-10-09" in call["user_prompt"]
    assert str(scores.user_life_path) in call["user_prompt"]
    assert str(scores.partner_life_path) in call["user_prompt"]
    assert str(scores.emotional_score) in call["user_prompt"]
    assert str(scores.conflict_score) in call["user_prompt"]
    assert str(scores.romance_score) in call["user_prompt"]
    assert str(scores.karmic_score) in call["user_prompt"]
    assert call["max_tokens"] == 600
