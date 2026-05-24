"""Unit-тесты prompt builder'ов (`app.services.ai.prompts`).

Промпты — это API между бизнес-логикой и моделью. Регрессии здесь могут тихо
сломать тон или вырезать ключевую часть контекста, поэтому пытаемся ловить:

* подставляются ли поля пользователя (имя/дата/пол);
* собирается ли тема канал-поста;
* не теряется ли в `SYSTEM_PROMPT` ключевой запрет.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.models.enums import Gender
from app.services.ai.prompts import (
    SYSTEM_PROMPT,
    UserContext,
    build_daily_forecast_prompt,
    build_esoteric_answer_prompt,
    build_mystical_message_prompt,
)


def test_system_prompt_has_mystical_persona_directives() -> None:
    # Маркеры стиля; если они исчезнут — значит, кто-то сломал тон.
    assert "мистический" in SYSTEM_PROMPT.lower()
    assert "ии" in SYSTEM_PROMPT.lower() or "языковая модель" in SYSTEM_PROMPT.lower()
    assert "markdown" in SYSTEM_PROMPT.lower()


def test_daily_forecast_prompt_includes_user_fields() -> None:
    ctx = UserContext(
        full_name="Анна",
        birth_date=date(1995, 5, 21),
        gender=Gender.FEMALE,
    )
    prompt = build_daily_forecast_prompt(ctx, today=date(2025, 1, 7))
    assert "Анна" in prompt
    assert "1995-05-21" in prompt
    assert "2025-01-07" in prompt
    assert "женщина" in prompt


def test_daily_forecast_prompt_handles_anonymous_user() -> None:
    prompt = build_daily_forecast_prompt(UserContext(), today=date(2025, 1, 7))
    assert "2025-01-07" in prompt
    assert "Имя:" not in prompt
    assert "Пол собеседника не указан" in prompt


def test_mystical_message_prompt_with_and_without_theme() -> None:
    plain = build_mystical_message_prompt()
    themed = build_mystical_message_prompt(theme="новолуние")
    assert "Тема" not in plain
    assert "Тема: новолуние" in themed


def test_esoteric_answer_prompt_includes_question_and_context() -> None:
    ctx = UserContext(full_name="Игорь", gender=Gender.MALE)
    prompt = build_esoteric_answer_prompt(
        "  Что меня ждёт на работе?  ",
        ctx,
    )
    # `.strip()` внутри билдера — лишние пробелы вокруг вопроса не должны
    # просачиваться в кавычки.
    assert "«Что меня ждёт на работе?»" in prompt
    assert "Игорь" in prompt
    assert "мужчина" in prompt


@pytest.mark.parametrize(
    "gender, expected",
    [
        (Gender.MALE, "мужчина"),
        (Gender.FEMALE, "женщина"),
        (None, "не указан"),
    ],
)
def test_gender_phrase_covers_all_branches(
    gender: Gender | None,
    expected: str,
) -> None:
    prompt = build_daily_forecast_prompt(
        UserContext(gender=gender),
        today=date(2025, 1, 1),
    )
    assert expected in prompt
