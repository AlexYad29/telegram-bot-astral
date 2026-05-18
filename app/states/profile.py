"""FSM-состояния для пошаговой регистрации/редактирования профиля."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ProfileRegistrationStates(StatesGroup):
    """Состояния FSM: имя → дата рождения → пол → подтверждение."""

    name = State()
    birth_date = State()
    gender = State()
    confirm = State()


__all__ = ["ProfileRegistrationStates"]
