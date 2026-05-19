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


def build_channel_day_forecast_prompt(*, today: date) -> str:
    """Прогноз дня для канала — без обращения к конкретному человеку."""
    return (
        f"Дата: {today.isoformat()}. "
        "Напиши прогноз дня для эзотерического канала. "
        "Обращайся ко всем читателям сразу, во множественном числе или "
        "безлично. Опиши общую энергию дня, на что обратить внимание и чего "
        "избегать. 4–6 предложений, без шаблонов, атмосферно."
    )


def build_channel_day_number_prompt(*, today: date, day_number: int) -> str:
    """Число дня — короткий нумерологический пост для канала.

    `day_number` — это уже вычисленное число дня (1..9 или мастер 11/22/33).
    Модель ничего не пересчитывает, только переплавляет в образы.
    """
    return (
        f"Дата: {today.isoformat()}. Число дня: {day_number}. "
        "Напиши короткий мистический пост о числе дня для эзотерического канала. "
        "Не упоминай формулу и не пересчитывай — переплавь число в образы. "
        "Опиши, какую энергию это число приносит сегодня и что подсказывает делать. "
        "3–5 предложений."
    )


def build_channel_day_energy_prompt(*, today: date) -> str:
    """Энергия дня — атмосферный пост без чисел, про настроение."""
    return (
        f"Дата: {today.isoformat()}. "
        "Напиши короткий пост про энергию сегодняшнего дня для эзотерического канала. "
        "Опиши настроение дня через образы стихий, лунного света, ветра, потоков. "
        "Дай одну тонкую подсказку, как с этой энергией обойтись. "
        "3–5 предложений."
    )


def build_channel_mystical_warning_prompt(*, today: date) -> str:
    """Мистическое предупреждение — слегка тревожный, но не пугающий пост."""
    return (
        f"Дата: {today.isoformat()}. "
        "Напиши короткое мистическое предупреждение для эзотерического канала. "
        "Атмосфера — настороженная, но не пугающая. Без катастроф и магического "
        "обмана. Скажи, чего сегодня лучше не делать и почему — через образы, "
        "не через запугивание. 3–5 предложений."
    )


def build_channel_viral_prompt(*, today: date) -> str:
    """Вирусный эзотерический пост — хук + крючок + микро-ритуал."""
    return (
        f"Дата: {today.isoformat()}. "
        "Напиши короткий вирусный эзотерический пост для канала. "
        "Структура: 1) сильная первая строка-крючок, 2) одна-две строки "
        "образного описания, 3) короткий микро-ритуал или мысль, которую "
        "хочется сохранить. Без markdown и без эмодзи в избытке. "
        "До 5 предложений."
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


@dataclass(frozen=True, slots=True)
class CompatibilityContext:
    """Данные для интерпретации совместимости.

    Скоры намеренно отделены от их формул — здесь это просто числа 0..100,
    которые модель должна расшифровать в живой рассказ.
    """

    user: UserContext
    partner_name: str
    partner_birth_date: date
    user_life_path: int
    partner_life_path: int
    emotional_score: int
    conflict_score: int
    romance_score: int
    karmic_score: int


def build_compatibility_prompt(ctx: CompatibilityContext) -> str:
    """Промпт для AI-интерпретации совместимости двух людей."""
    return (
        f"{_user_block(ctx.user)} "
        f"Партнёр: {ctx.partner_name}, дата рождения "
        f"{ctx.partner_birth_date.isoformat()}.\n"
        f"Числа жизненного пути: {ctx.user_life_path} (у собеседника) и "
        f"{ctx.partner_life_path} (у партнёра).\n"
        f"Расчётные субскоры (0..100):\n"
        f"- эмоциональная связь: {ctx.emotional_score};\n"
        f"- конфликтность: {ctx.conflict_score};\n"
        f"- романтика: {ctx.romance_score};\n"
        f"- кармическая нить: {ctx.karmic_score}.\n\n"
        "Расскажи об этой паре как мистический проводник: где их сильная "
        "связь, где трение, какой у них потенциал и о чём стоит помнить. "
        "Опирайся на цифры, но не пересчитывай их — переплавь в образы. "
        "6–9 предложений, разбей мыслью на 2–3 абзаца."
    )


@dataclass(frozen=True, slots=True)
class TarotCardContext:
    """Карта в позиции расклада — для подстановки в промпт."""

    position_label: str
    name_ru: str
    name_en: str
    reversed: bool
    keywords: tuple[str, ...]
    meaning_short: str


def build_tarot_interpretation_prompt(
    *,
    user: UserContext,
    question: str | None,
    cards: tuple[TarotCardContext, ...],
) -> str:
    """Промпт для AI-толкования трёхкарточного расклада."""
    question_line = (
        f"Вопрос собеседника: «{question.strip()}».\n"
        if question and question.strip()
        else "Вопрос не сформулирован — дай общее толкование расклада.\n"
    )
    cards_block_parts: list[str] = []
    for card in cards:
        orient = "в перевёрнутом положении" if card.reversed else "в прямом положении"
        keywords = ", ".join(card.keywords) if card.keywords else "—"
        cards_block_parts.append(
            f"[{card.position_label}] {card.name_ru} ({card.name_en}), {orient}. "
            f"Ключевые слова: {keywords}. Краткий смысл: {card.meaning_short}"
        )
    cards_block = "\n".join(cards_block_parts)
    return (
        f"{_user_block(user)}\n"
        f"{question_line}"
        "Расклад «Прошлое — Настоящее — Будущее»:\n"
        f"{cards_block}\n\n"
        "Истолкуй расклад целиком, как мистический читающий таролог. "
        "Связь между картами важнее каждой карты по отдельности. "
        "Учитывай перевёрнутые положения. "
        "Не повторяй краткие смыслы дословно — переплавь в живой рассказ "
        "из 3 связных абзацев (прошлое → настоящее → будущее) и одного "
        "финального предложения-совета."
    )


__all__ = [
    "SYSTEM_PROMPT",
    "CompatibilityContext",
    "TarotCardContext",
    "Tone",
    "UserContext",
    "build_channel_day_energy_prompt",
    "build_channel_day_forecast_prompt",
    "build_channel_day_number_prompt",
    "build_channel_mystical_warning_prompt",
    "build_channel_viral_prompt",
    "build_compatibility_prompt",
    "build_daily_forecast_prompt",
    "build_esoteric_answer_prompt",
    "build_mystical_message_prompt",
    "build_tarot_interpretation_prompt",
]
