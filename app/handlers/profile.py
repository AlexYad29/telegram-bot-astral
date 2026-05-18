"""Команда /profile — на ЭТАПЕ 3 только просмотр.

Реальный FSM-flow регистрации (ввод имени → даты рождения → пола) приедет
на ЭТАПЕ 4. Сейчас бот умеет показать пустой/частичный профиль и подсказать
пользователю, что регистрация ещё не реализована.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.models.enums import Gender
from app.models.user import User as DbUser

router = Router(name="profile")


_GENDER_LABEL: dict[Gender, str] = {
    Gender.MALE: "мужской",
    Gender.FEMALE: "женский",
    Gender.OTHER: "иное",
}


@router.message(Command("profile"))
async def cmd_profile(message: Message, user: DbUser | None = None) -> None:
    """Показать текущий профиль пользователя."""
    if user is None:
        await message.answer(
            "Я тебя ещё не вижу в звёздной книге. Попробуй /start."
        )
        return

    if not user.is_registered:
        await message.answer(
            "<b>Профиль пока пуст</b> — звёздам нужна точка отсчёта.\n\n"
            "На следующем этапе мы пройдём короткую регистрацию: имя, "
            "дата рождения, пол. Тогда я смогу читать карту именно для тебя."
        )
        return

    lines: list[str] = ["<b>Твой профиль</b>"]
    if user.full_name:
        lines.append(f"• Имя: {user.full_name}")
    if user.birth_date:
        lines.append(f"• Дата рождения: {user.birth_date.isoformat()}")
    if user.gender:
        lines.append(f"• Пол: {_GENDER_LABEL.get(user.gender, '—')}")
    lines.append("")
    lines.append("На ЭТАПЕ 4 появится команда для обновления профиля.")
    await message.answer("\n".join(lines))


__all__ = ["cmd_profile", "router"]
