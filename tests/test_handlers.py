"""Smoke-тесты для роутеров: главное меню/команды зарегистрированы и привязаны."""

from __future__ import annotations

from aiogram import Router

from app.handlers import build_main_router
from app.handlers.common import router as common_router
from app.handlers.errors import router as errors_router
from app.handlers.forecast import router as forecast_router
from app.handlers.numerology import router as numerology_router
from app.handlers.profile import router as profile_router


def test_main_router_wires_all_subrouters() -> None:
    root = build_main_router()
    assert isinstance(root, Router)
    names = {sub.name for sub in root.sub_routers}
    assert names == {"errors", "common", "profile", "forecast", "numerology"}


def test_forecast_router_has_all_handlers() -> None:
    """В ЭТАПЕ 5 forecast-роутер регистрирует команду, кнопку и retry-колбек."""
    message_callbacks = {
        h.callback.__name__ for h in forecast_router.message.handlers
    }
    callback_callbacks = {
        h.callback.__name__ for h in forecast_router.callback_query.handlers
    }
    assert {"cmd_forecast", "menu_forecast"}.issubset(message_callbacks)
    assert "cb_forecast_retry" in callback_callbacks


def test_numerology_router_has_handlers() -> None:
    """В ЭТАПЕ 6 numerology-роутер регистрирует команду и кнопку из главного меню."""
    callbacks = {h.callback.__name__ for h in numerology_router.message.handlers}
    assert {"cmd_numerology", "menu_numerology"}.issubset(callbacks)


def test_common_router_has_start_and_help() -> None:
    # У aiogram Router каждый observer хранит зарегистрированные хендлеры в `.handlers`.
    callbacks = [h.callback.__name__ for h in common_router.message.handlers]
    assert "cmd_start" in callbacks
    assert "cmd_help" in callbacks


def test_profile_router_has_full_fsm_flow() -> None:
    """В ЭТАПЕ 4 в `profile` роутере должны быть все хендлеры FSM-регистрации
    и точечного редактирования."""
    message_callbacks = {
        h.callback.__name__ for h in profile_router.message.handlers
    }
    callback_callbacks = {
        h.callback.__name__ for h in profile_router.callback_query.handlers
    }
    assert {
        "cmd_profile",
        "cmd_edit_profile",
        "cmd_cancel",
        "step_name",
        "step_birth_date",
    }.issubset(message_callbacks)
    assert {
        "cb_start_registration",
        "step_gender",
        "step_confirm",
        "cb_cancel",
        "cb_edit_name",
        "cb_edit_dob",
        "cb_edit_gender",
        "cb_edit_restart",
    }.issubset(callback_callbacks)


def test_errors_router_has_handler() -> None:
    # ErrorEvent наблюдается в `.errors` observer'е.
    assert len(errors_router.errors.handlers) == 1
    assert errors_router.errors.handlers[0].callback.__name__ == "on_error"
