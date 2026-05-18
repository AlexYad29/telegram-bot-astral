"""FSM-состояния флоу `/compatibility`."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class CompatibilityStates(StatesGroup):
    """Этапы ввода данных партнёра.

    Собственные данные пользователя берутся из профиля — повторно их
    спрашивать не нужно.
    """

    partner_name = State()
    partner_birth_date = State()
    confirm = State()


__all__ = ["CompatibilityStates"]
