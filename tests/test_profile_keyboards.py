"""Тесты inline-клавиатур профиля."""

from __future__ import annotations

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
from app.models.enums import Gender


def _all_callbacks(markup) -> list[str]:
    return [btn.callback_data for row in markup.inline_keyboard for btn in row]


def test_gender_keyboard_contains_all_genders_and_cancel() -> None:
    kb = build_gender_keyboard()
    callbacks = set(_all_callbacks(kb))
    assert callbacks == {
        f"{CB_GENDER_PREFIX}:{Gender.MALE.value}",
        f"{CB_GENDER_PREFIX}:{Gender.FEMALE.value}",
        f"{CB_GENDER_PREFIX}:{Gender.OTHER.value}",
        CB_CANCEL,
    }


def test_confirm_keyboard_has_confirm_and_cancel() -> None:
    kb = build_confirm_keyboard()
    assert set(_all_callbacks(kb)) == {CB_CONFIRM, CB_CANCEL}


def test_edit_keyboard_has_all_actions() -> None:
    kb = build_edit_keyboard()
    assert set(_all_callbacks(kb)) == {
        CB_EDIT_NAME,
        CB_EDIT_DOB,
        CB_EDIT_GENDER,
        CB_EDIT_RESTART,
    }


def test_register_start_keyboard_has_start_button() -> None:
    kb = build_register_start_keyboard()
    assert set(_all_callbacks(kb)) == {CB_START_REG}


def test_gender_from_callback_parses_valid_values() -> None:
    assert gender_from_callback(f"{CB_GENDER_PREFIX}:{Gender.MALE.value}") is Gender.MALE
    assert gender_from_callback(f"{CB_GENDER_PREFIX}:{Gender.FEMALE.value}") is Gender.FEMALE
    assert gender_from_callback(f"{CB_GENDER_PREFIX}:{Gender.OTHER.value}") is Gender.OTHER


def test_gender_from_callback_returns_none_on_garbage() -> None:
    assert gender_from_callback("garbage") is None
    assert gender_from_callback(f"{CB_GENDER_PREFIX}:nope") is None
