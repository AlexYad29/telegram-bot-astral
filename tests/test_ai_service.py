"""Тесты `AIService` с замоканным `AIClient`.

Проверяем, что:

* в клиент уходит правильный `system_prompt` (из `SYSTEM_PROMPT`);
* в `user_prompt` подставляются поля юзера;
* `generate_mystical_message` режет `max_tokens` (короткие канал-посты);
* анонимный пользователь не ломает сервис.
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


@dataclass
class FakeAIClient:
    """Простая заглушка с записью вызовов."""

    reply: str = "звёзды шепчут"
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
    user.birth_date = date(1992, 3, 14)
    user.gender = Gender.FEMALE
    return user


@pytest.mark.asyncio
async def test_daily_forecast_passes_user_to_prompt() -> None:
    fake = FakeAIClient(reply="сегодня ветер судьбы")
    service = AIService(fake)

    result = await service.generate_daily_forecast(
        _make_user(),
        today=date(2025, 6, 1),
    )

    assert result == "сегодня ветер судьбы"
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["system_prompt"] == SYSTEM_PROMPT
    assert "Мария" in call["user_prompt"]
    assert "1992-03-14" in call["user_prompt"]
    assert "2025-06-01" in call["user_prompt"]
    # дневной прогноз использует дефолты — никаких override'ов.
    assert call["max_tokens"] is None
    assert call["temperature"] is None


@pytest.mark.asyncio
async def test_daily_forecast_handles_anonymous_user() -> None:
    fake = FakeAIClient()
    service = AIService(fake)

    await service.generate_daily_forecast(None, today=date(2025, 6, 1))

    assert "Имя:" not in fake.calls[0]["user_prompt"]
    assert "Пол собеседника не указан" in fake.calls[0]["user_prompt"]


@pytest.mark.asyncio
async def test_mystical_message_limits_tokens() -> None:
    fake = FakeAIClient()
    service = AIService(fake)

    await service.generate_mystical_message(theme="полнолуние")

    call = fake.calls[0]
    assert "полнолуние" in call["user_prompt"]
    assert call["max_tokens"] == 300


@pytest.mark.asyncio
async def test_esoteric_answer_includes_question() -> None:
    fake = FakeAIClient(reply="лунные тени укажут путь")
    service = AIService(fake)

    text = await service.generate_esoteric_answer("стоит ли менять работу?", _make_user())

    assert text == "лунные тени укажут путь"
    assert "стоит ли менять работу?" in fake.calls[0]["user_prompt"]
    assert "Мария" in fake.calls[0]["user_prompt"]
