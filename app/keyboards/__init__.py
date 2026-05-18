"""Reply / inline клавиатуры."""

from app.keyboards.main_menu import (
    BTN_COMPATIBILITY,
    BTN_FORECAST,
    BTN_HELP,
    BTN_NUMEROLOGY,
    BTN_PROFILE,
    BTN_TAROT,
    build_main_menu,
)
from app.keyboards.profile import (
    CB_CANCEL,
    CB_CONFIRM,
    CB_EDIT_DOB,
    CB_EDIT_GENDER,
    CB_EDIT_NAME,
    CB_EDIT_RESTART,
    CB_GENDER_PREFIX,
    CB_START_REG,
    build_confirm_keyboard,
    build_edit_keyboard,
    build_gender_keyboard,
    build_register_start_keyboard,
    gender_from_callback,
)

__all__ = [
    "BTN_COMPATIBILITY",
    "BTN_FORECAST",
    "BTN_HELP",
    "BTN_NUMEROLOGY",
    "BTN_PROFILE",
    "BTN_TAROT",
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
    "build_main_menu",
    "build_register_start_keyboard",
    "gender_from_callback",
]
