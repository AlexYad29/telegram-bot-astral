"""Структурные проверки клавиатур."""

from __future__ import annotations

from app.keyboards.main_menu import (
    BTN_COMPATIBILITY,
    BTN_FORECAST,
    BTN_HELP,
    BTN_NUMEROLOGY,
    BTN_PROFILE,
    BTN_TAROT,
    build_main_menu,
)


def test_main_menu_has_all_expected_buttons() -> None:
    kb = build_main_menu()
    assert kb.resize_keyboard is True
    assert kb.is_persistent is True
    flat = {btn.text for row in kb.keyboard for btn in row}
    assert flat == {
        BTN_FORECAST,
        BTN_TAROT,
        BTN_COMPATIBILITY,
        BTN_NUMEROLOGY,
        BTN_PROFILE,
        BTN_HELP,
    }
