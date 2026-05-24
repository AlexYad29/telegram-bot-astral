"""Главное меню (ReplyKeyboard) — постоянно висит снизу, как телефонная клавиатура."""

from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_FORECAST = "🔮 Прогноз дня"
BTN_TAROT = "🃏 Таро"
BTN_COMPATIBILITY = "💞 Совместимость"
BTN_NUMEROLOGY = "🧮 Нумерология"
BTN_PROFILE = "👤 Профиль"
BTN_HELP = "❓ Помощь"


def build_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_FORECAST)],
            [
                KeyboardButton(text=BTN_TAROT),
                KeyboardButton(text=BTN_COMPATIBILITY),
                KeyboardButton(text=BTN_NUMEROLOGY),
            ],
            [
                KeyboardButton(text=BTN_PROFILE),
                KeyboardButton(text=BTN_HELP),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Спроси у звёзд…",
    )


__all__ = [
    "BTN_COMPATIBILITY",
    "BTN_FORECAST",
    "BTN_HELP",
    "BTN_NUMEROLOGY",
    "BTN_PROFILE",
    "BTN_TAROT",
    "build_main_menu",
]
