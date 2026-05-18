"""Inline-клавиатуры для FSM `/tarot`."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

CB_TAROT_DRAW_NO_QUESTION = "tarot:draw_no_q"
CB_TAROT_CANCEL = "tarot:cancel"


def build_pre_draw_keyboard() -> InlineKeyboardMarkup:
    """Кнопки на шаге «нужен ли вопрос»: либо без вопроса, либо отмена."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🃏 Без вопроса", callback_data=CB_TAROT_DRAW_NO_QUESTION)],
            [InlineKeyboardButton(text="Отмена", callback_data=CB_TAROT_CANCEL)],
        ]
    )


__all__ = [
    "CB_TAROT_CANCEL",
    "CB_TAROT_DRAW_NO_QUESTION",
    "build_pre_draw_keyboard",
]
