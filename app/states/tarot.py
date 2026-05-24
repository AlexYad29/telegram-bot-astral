"""FSM-состояния для `/tarot`."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class TarotStates(StatesGroup):
    """Состояния короткого расклада.

    В отличие от профиля/совместимости тут одна-единственная стадия:
    ждём текст вопроса либо нажатие на «без вопроса».
    """

    question = State()


__all__ = ["TarotStates"]
