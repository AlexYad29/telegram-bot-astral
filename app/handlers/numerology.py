"""Хендлер `/numerology` + кнопка из главного меню.

Считаем без AI — таблица интерпретаций фиксированная и каноничная. AI можно
будет навесить отдельным «глубоким разбором» позже.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.keyboards.main_menu import BTN_NUMEROLOGY
from app.keyboards.profile import build_register_start_keyboard
from app.models.user import User as DbUser
from app.services.numerology import calculate

logger = logging.getLogger(__name__)
router = Router(name="numerology")


def _format_reading(user: DbUser) -> str:
    """Собрать форматированный ответ. Имя/дата гарантированно заполнены."""
    assert user.full_name is not None
    assert user.birth_date is not None
    reading = calculate(user.full_name, user.birth_date)
    return (
        f"🔮 <b>Числа твоей судьбы</b>\n\n"
        f"<b>Число судьбы — {reading.life_path}</b>\n"
        f"{reading.life_path_meaning}\n\n"
        f"<b>Число личности — {reading.expression}</b>\n"
        f"{reading.expression_meaning}"
    )


async def _send_numerology(message: Message, user: DbUser | None) -> None:
    if user is None or not user.is_registered or not user.full_name:
        await message.answer(
            "<b>Для расчёта чисел нужны имя и дата рождения.</b>\n\n"
            "Пройди короткую регистрацию через /profile.",
            reply_markup=build_register_start_keyboard(),
        )
        return
    await message.answer(_format_reading(user))


@router.message(Command("numerology"))
async def cmd_numerology(message: Message, user: DbUser | None = None) -> None:
    await _send_numerology(message, user)


@router.message(F.text == BTN_NUMEROLOGY)
async def menu_numerology(message: Message, user: DbUser | None = None) -> None:
    await _send_numerology(message, user)


__all__ = ["cmd_numerology", "router"]
