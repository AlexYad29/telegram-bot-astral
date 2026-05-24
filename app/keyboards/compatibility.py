"""Inline-клавиатуры для флоу `/compatibility`."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

CB_COMPAT_CONFIRM = "compat:confirm"
CB_COMPAT_CANCEL = "compat:cancel"


def build_confirm_keyboard() -> InlineKeyboardMarkup:
    """Подтвердить / отменить расчёт совместимости."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔮 Считать", callback_data=CB_COMPAT_CONFIRM),
                InlineKeyboardButton(text="✖️ Отмена", callback_data=CB_COMPAT_CANCEL),
            ]
        ]
    )


__all__ = [
    "CB_COMPAT_CANCEL",
    "CB_COMPAT_CONFIRM",
    "build_confirm_keyboard",
]
