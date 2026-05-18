"""Smoke-тесты для роутеров: главное меню/команды зарегистрированы и привязаны."""

from __future__ import annotations

from aiogram import Router

from app.handlers import build_main_router
from app.handlers.common import router as common_router
from app.handlers.errors import router as errors_router
from app.handlers.profile import router as profile_router


def test_main_router_wires_all_subrouters() -> None:
    root = build_main_router()
    assert isinstance(root, Router)
    names = {sub.name for sub in root.sub_routers}
    assert names == {"errors", "common", "profile"}


def test_common_router_has_start_and_help() -> None:
    # У aiogram Router каждый observer хранит зарегистрированные хендлеры в `.handlers`.
    callbacks = [h.callback.__name__ for h in common_router.message.handlers]
    assert "cmd_start" in callbacks
    assert "cmd_help" in callbacks


def test_profile_router_has_profile_handler() -> None:
    callbacks = [h.callback.__name__ for h in profile_router.message.handlers]
    assert "cmd_profile" in callbacks


def test_errors_router_has_handler() -> None:
    # ErrorEvent наблюдается в `.errors` observer'е.
    assert len(errors_router.errors.handlers) == 1
    assert errors_router.errors.handlers[0].callback.__name__ == "on_error"
