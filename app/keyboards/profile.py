"""Inline-клавиатуры для регистрации и редактирования профиля."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.models.enums import Gender

# Callback-data префиксы. Короткие, чтобы влезть в 64 байта Telegram'а.
CB_GENDER_PREFIX = "prof:gender"
CB_CONFIRM = "prof:confirm"
CB_CANCEL = "prof:cancel"
CB_START_REG = "prof:reg:start"
CB_EDIT_NAME = "prof:edit:name"
CB_EDIT_DOB = "prof:edit:dob"
CB_EDIT_GENDER = "prof:edit:gender"
CB_EDIT_RESTART = "prof:edit:restart"

_GENDER_LABELS: dict[Gender, str] = {
    Gender.MALE: "♂ Мужской",
    Gender.FEMALE: "♀ Женский",
    Gender.OTHER: "⚧ Иное",
}


def build_gender_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора пола (используется и при первичной регистрации,
    и при точечном редактировании)."""
    builder = InlineKeyboardBuilder()
    for gender, label in _GENDER_LABELS.items():
        builder.button(
            text=label,
            callback_data=f"{CB_GENDER_PREFIX}:{gender.value}",
        )
    builder.button(text="✖ Отмена", callback_data=CB_CANCEL)
    builder.adjust(3, 1)
    return builder.as_markup()


def build_confirm_keyboard() -> InlineKeyboardMarkup:
    """Финальное подтверждение/отмена данных регистрации."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✓ Подтвердить", callback_data=CB_CONFIRM)
    builder.button(text="✖ Отмена", callback_data=CB_CANCEL)
    builder.adjust(2)
    return builder.as_markup()


def build_edit_keyboard() -> InlineKeyboardMarkup:
    """Меню точечного редактирования профиля."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✎ Имя", callback_data=CB_EDIT_NAME)
    builder.button(text="✎ Дата рождения", callback_data=CB_EDIT_DOB)
    builder.button(text="✎ Пол", callback_data=CB_EDIT_GENDER)
    builder.button(text="↻ Пройти заново", callback_data=CB_EDIT_RESTART)
    builder.adjust(1)
    return builder.as_markup()


def build_register_start_keyboard() -> InlineKeyboardMarkup:
    """Кнопка-приглашение к началу регистрации."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✨ Начать регистрацию",
                    callback_data=CB_START_REG,
                )
            ]
        ]
    )


def gender_from_callback(callback_data: str) -> Gender | None:
    """Достать `Gender` из callback_data вида `prof:gender:<value>`."""
    prefix = f"{CB_GENDER_PREFIX}:"
    if not callback_data.startswith(prefix):
        return None
    value = callback_data[len(prefix) :]
    try:
        return Gender(value)
    except ValueError:
        return None


__all__ = [
    "CB_CANCEL",
    "CB_CONFIRM",
    "CB_EDIT_DOB",
    "CB_EDIT_GENDER",
    "CB_EDIT_NAME",
    "CB_EDIT_RESTART",
    "CB_GENDER_PREFIX",
    "CB_START_REG",
    "build_confirm_keyboard",
    "build_edit_keyboard",
    "build_gender_keyboard",
    "build_register_start_keyboard",
    "gender_from_callback",
]
