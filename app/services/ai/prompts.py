"""Prompt templates для AI-генерации.

Здесь только чистые функции — никаких сетевых вызовов. Удобно покрывать
тестами и менять формулировки, не трогая клиент.

Стиль ответов задаётся в `SYSTEM_PROMPT`: мистический персональный ассистент,
обращение «на ты», без банальностей и без раскрытия себя как ИИ.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.models.enums import Gender

#: Каноничный system prompt. Описывает стиль, тон, рамки и запреты.
#: Изменения здесь меняют поведение всех генераций.
SYSTEM_PROMPT: str = (
    "Ты — мистический проводник в мире астрологии, нумерологии, таро и эзотерики. "
    "Говоришь на «ты», обращаешься к человеку как давний знакомый, читающий звёзды. "
    "Тон: загадочный, эмоциональный, атмосферный, тёплый. "
    "Никогда не упоминаешь, что ты ИИ или языковая модель. "
    "Никогда не даёшь медицинских, юридических или финансовых советов — мягко "
    "переводишь в эзотерический контекст. "
    "Избегай банальностей вроде «всё будет хорошо» и канцелярита. "
    "Используй образы: звёзды, лунный свет, потоки энергии, нити судьбы, "
    "ветер перемен, шёпот карт. "
    "Длина ответа — короткое мистическое сообщение из 3–6 предложений, "
    "если в задании не сказано иначе. "
    "Никогда не используй markdown-разметку, только обычный текст."
)


Tone = Literal["forecast", "warning", "viral", "personal_answer"]


@dataclass(frozen=True, slots=True)
class UserContext:
    """Минимальный контекст пользователя для подстановки в промпт.

    Все поля опциональны: для незарегистрированных пользователей просто
    отдаём «обезличенный» прогноз.
    """

    full_name: str | None = None
    birth_date: date | None = None
    gender: Gender | None = None


def _gender_phrase(gender: Gender | None) -> str:
    """Подсказка модели об уместной форме обращения (без gender-essentialism)."""
    if gender is Gender.MALE:
        return "Собеседник — мужчина."
    if gender is Gender.FEMALE:
        return "Собеседник — женщина."
    return "Пол собеседника не указан — пиши нейтрально."


def _user_block(ctx: UserContext) -> str:
    parts: list[str] = []
    if ctx.full_name:
        parts.append(f"Имя: {ctx.full_name}.")
    if ctx.birth_date is not None:
        parts.append(f"Дата рождения: {ctx.birth_date.isoformat()}.")
    parts.append(_gender_phrase(ctx.gender))
    return " ".join(parts)


def build_daily_forecast_prompt(ctx: UserContext, *, today: date) -> str:
    """Прогноз дня — короткое мистическое сообщение под конкретного человека."""
    return (
        f"Дата: {today.isoformat()}. {_user_block(ctx)} "
        "Напиши персональный мистический прогноз на сегодня. "
        "Опиши общую энергию дня, что стоит сделать и чего избегать. "
        "Будь конкретен и атмосферен, без шаблонов."
    )


def build_mystical_message_prompt(theme: str | None = None) -> str:
    """Атмосферное мистическое сообщение для канала (без персональных данных)."""
    theme_part = f"Тема: {theme}. " if theme else ""
    return (
        f"{theme_part}"
        "Напиши короткое атмосферное мистическое сообщение для эзотерического канала. "
        "Без обращения к конкретному человеку. "
        "Цель — зацепить, заставить остановиться и подумать. "
        "3–5 предложений."
    )


def build_esoteric_answer_prompt(question: str, ctx: UserContext) -> str:
    """Свободный мистический ответ на вопрос пользователя."""
    return (
        f"{_user_block(ctx)} Вопрос собеседника: «{question.strip()}». "
        "Ответь в роли мистического проводника. "
        "Если вопрос требует медицинского, юридического или финансового "
        "совета — мягко переведи разговор в энергетический/символический "
        "план и предложи обратиться к специалисту. "
        "3–6 предложений."
    )


__all__ = [
    "SYSTEM_PROMPT",
    "Tone",
    "UserContext",
    "build_daily_forecast_prompt",
    "build_esoteric_answer_prompt",
    "build_mystical_message_prompt",
]
