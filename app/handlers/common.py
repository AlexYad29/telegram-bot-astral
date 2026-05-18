"""Базовые команды: /start, /help + хендлеры главного меню (заглушки).

Полная регистрация и FSM-регистрация профиля приедет на ЭТАПЕ 4.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.keyboards.main_menu import (
    BTN_COMPATIBILITY,
    BTN_FORECAST,
    BTN_HELP,
    BTN_NUMEROLOGY,
    BTN_PROFILE,
    BTN_TAROT,
    build_main_menu,
)
from app.models.user import User as DbUser

router = Router(name="common")


# ---------- /start ----------
@router.message(CommandStart())
async def cmd_start(message: Message, user: DbUser | None = None) -> None:
    name = (
        user.full_name
        if user and user.full_name
        else (message.from_user.first_name if message.from_user else None)
        or "странник"
    )
    text = (
        f"✨ <b>Приветствую, {name}.</b>\n\n"
        "Я — твой проводник в мир астрологии, нумерологии и таро. "
        "Я слышу шёпот звёзд и могу подсказать, что они говорят тебе сегодня.\n\n"
        "Пройди короткую регистрацию через /profile — и я смогу отвечать "
        "именно тебе, а не «вообще».\n\n"
        "Открой меню ниже или используй команды:\n"
        "• /profile — твой профиль и дата рождения\n"
        "• /help — что я умею"
    )
    await message.answer(text, reply_markup=build_main_menu())


# ---------- /help ----------
@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    text = (
        "🔮 <b>Что я умею</b>\n\n"
        "<b>Уже работает:</b>\n"
        "• /start — открыть главное меню\n"
        "• /profile — посмотреть/обновить профиль\n"
        "• /help — этот список\n\n"
        "<b>Скоро откроется:</b>\n"
        "• /numerology — числа судьбы и личности\n"
        "• /compatibility — совместимость с другим человеком\n"
        "• /tarot — расклад на сегодня и на ближайший путь\n"
    )
    await message.answer(text)


# ---------- Кнопки главного меню ----------
# Кнопки, для которых уже есть команды, перенаправим на них.
@router.message(F.text == BTN_HELP)
async def menu_help(message: Message) -> None:
    await cmd_help(message)


@router.message(F.text == BTN_PROFILE)
async def menu_profile(message: Message, user: DbUser | None = None) -> None:
    # Реальный /profile хэндлер живёт в app.handlers.profile;
    # тут только эмиссия команды на тот же контекст. `user` явно прокидываем —
    # aiogram автоматически передаёт его в kwargs только напрямую в хендлер.
    from app.handlers.profile import cmd_profile

    await cmd_profile(message, user=user)


# Кнопки, фичи под которыми появятся в ЭТАПАХ 5–8 — отвечаем «скоро».
_COMING_SOON = {
    BTN_FORECAST: (
        "🌙 Прогноз дня скоро откроется. Звёзды ещё выстраиваются в нужный узор."
    ),
    BTN_TAROT: (
        "🃏 Колода пока тасуется. Скоро смогу разложить три карты — прошлое, "
        "настоящее, будущее."
    ),
    BTN_COMPATIBILITY: (
        "💞 Анализ совместимости двух дат рождения уже на подходе. "
        "Подготовь имя и дату того, кто тебе важен."
    ),
    BTN_NUMEROLOGY: (
        "🧮 Числа судьбы и личности рассчитаются автоматически — нужна только "
        "твоя дата рождения через /profile."
    ),
}


@router.message(F.text.in_(set(_COMING_SOON.keys())))
async def menu_coming_soon(message: Message) -> None:
    if message.text is None:
        return
    await message.answer(_COMING_SOON[message.text])


__all__ = ["router"]
