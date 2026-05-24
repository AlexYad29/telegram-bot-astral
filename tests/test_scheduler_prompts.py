"""Тесты канал-промптов и `AIService.generate_channel_post`."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pytest

from app.models.enums import PostKind
from app.services.ai.prompts import (
    SYSTEM_PROMPT,
    build_channel_day_energy_prompt,
    build_channel_day_forecast_prompt,
    build_channel_day_number_prompt,
    build_channel_mystical_warning_prompt,
    build_channel_viral_prompt,
)
from app.services.ai.service import AIService


@dataclass
class FakeAIClient:
    reply: str = "канал-пост"
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


_TODAY = date(2026, 5, 18)


def test_day_forecast_prompt_includes_date() -> None:
    prompt = build_channel_day_forecast_prompt(today=_TODAY)
    assert "2026-05-18" in prompt
    assert "канал" in prompt.lower()


def test_day_number_prompt_includes_number() -> None:
    prompt = build_channel_day_number_prompt(today=_TODAY, day_number=7)
    assert "Число дня: 7" in prompt
    assert "2026-05-18" in prompt


def test_day_energy_prompt_includes_date() -> None:
    prompt = build_channel_day_energy_prompt(today=_TODAY)
    assert "2026-05-18" in prompt
    assert "энерги" in prompt.lower()


def test_mystical_warning_prompt_is_warning_themed() -> None:
    prompt = build_channel_mystical_warning_prompt(today=_TODAY)
    assert "2026-05-18" in prompt
    assert "предупрежден" in prompt.lower()


def test_viral_prompt_mentions_structure() -> None:
    prompt = build_channel_viral_prompt(today=_TODAY)
    assert "2026-05-18" in prompt
    assert "вирусн" in prompt.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        PostKind.DAY_FORECAST,
        PostKind.DAY_ENERGY,
        PostKind.MYSTICAL_WARNING,
        PostKind.VIRAL,
    ],
)
async def test_generate_channel_post_dispatches_correct_prompt(kind: PostKind) -> None:
    fake = FakeAIClient(reply=f"reply-{kind.value}")
    service = AIService(fake)
    result = await service.generate_channel_post(kind=kind, today=_TODAY)
    assert result == f"reply-{kind.value}"
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["system_prompt"] == SYSTEM_PROMPT
    assert "2026-05-18" in call["user_prompt"]


@pytest.mark.asyncio
async def test_generate_channel_post_day_number_requires_value() -> None:
    fake = FakeAIClient()
    service = AIService(fake)
    with pytest.raises(ValueError, match="day_number"):
        await service.generate_channel_post(kind=PostKind.DAY_NUMBER, today=_TODAY)


@pytest.mark.asyncio
async def test_generate_channel_post_day_number_carries_number() -> None:
    fake = FakeAIClient(reply="семёрка")
    service = AIService(fake)
    result = await service.generate_channel_post(
        kind=PostKind.DAY_NUMBER, today=_TODAY, day_number=7
    )
    assert result == "семёрка"
    assert "Число дня: 7" in fake.calls[0]["user_prompt"]
