"""Профиль: просмотр + FSM-регистрация + точечное редактирование полей.

Поток первичной регистрации:
    /profile (или кнопка «✨ Начать регистрацию»)
        ↓
    Шаг 1 — имя (текст)
        ↓
    Шаг 2 — дата рождения (текст, несколько форматов)
        ↓
    Шаг 3 — пол (inline-кнопки)
        ↓
    Шаг 4 — подтверждение (inline)
        ↓
    save + показать готовый профиль

Поток точечного редактирования: из меню «Редактировать» пользователь выбирает
одно поле, FSM пишет в `edit_only` маркер и выходит сразу после ввода (без
прохода по всем оставшимся шагам).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.models.user import User as DbUser
from app.repositories.user import UserRepository
from app.services.profile import (
    ProfileValidationError,
    parse_birth_date,
    parse_full_name,
)
from app.states.profile import ProfileRegistrationStates

logger = logging.getLogger(__name__)
router = Router(name="profile")


_GENDER_LABEL: dict[Gender, str] = {
    Gender.MALE: "мужской",
    Gender.FEMALE: "женский",
    Gender.OTHER: "иное",
}

# Маркеры в state.data для «точечного» редактирования одного поля.
_EDIT_NAME = "name"
_EDIT_DOB = "dob"
_EDIT_GENDER = "gender"


# --------------------------------------------------------------------------- #
# Хелперы
# --------------------------------------------------------------------------- #
def _format_profile(user: DbUser) -> str:
    lines: list[str] = ["<b>Твой профиль</b>"]
    if user.full_name:
        lines.append(f"• Имя: {user.full_name}")
    if user.birth_date:
        lines.append(f"• Дата рождения: {user.birth_date.isoformat()}")
    if user.gender:
        lines.append(f"• Пол: {_GENDER_LABEL.get(user.gender, '—')}")
    return "\n".join(lines)


def _format_summary(data: dict[str, Any]) -> str:
    gender_value = data.get("gender")
    gender_label = "—"
    if isinstance(gender_value, str):
        try:
            gender_label = _GENDER_LABEL[Gender(gender_value)]
        except ValueError:
            gender_label = "—"
    birth = data.get("birth_date") or "—"
    return (
        "<b>Проверь, всё ли верно</b>\n\n"
        f"• Имя: <b>{data.get('full_name', '—')}</b>\n"
        f"• Дата рождения: <b>{birth}</b>\n"
        f"• Пол: <b>{gender_label}</b>\n\n"
        "Если всё верно — подтверди. Иначе нажми «Отмена» и начни заново."
    )


async def _save_field(
    *,
    session: AsyncSession,
    telegram_id: int,
    full_name: str | None = None,
    birth_date: date | None = None,
    gender: Gender | None = None,
) -> DbUser | None:
    repo = UserRepository(session)
    return await repo.update_profile(
        telegram_id,
        full_name=full_name,
        birth_date=birth_date,
        gender=gender,
    )


# --------------------------------------------------------------------------- #
# /profile — точка входа
# --------------------------------------------------------------------------- #
@router.message(Command("profile"), StateFilter("*"))
async def cmd_profile(
    message: Message,
    state: FSMContext,
    user: DbUser | None = None,
) -> None:
    """Показать профиль или предложить регистрацию (доступна из любого состояния)."""
    await state.clear()
    if user is None:
        await message.answer("Я тебя ещё не вижу в звёздной книге. Попробуй /start.")
        return

    if not user.is_registered:
        await message.answer(
            "<b>Профиль пока пуст</b> — звёздам нужна точка отсчёта.\n\n"
            "Пройдём короткую регистрацию: имя → дата рождения → пол.",
            reply_markup=build_register_start_keyboard(),
        )
        return

    await message.answer(
        _format_profile(user) + "\n\nЧто изменить?",
        reply_markup=build_edit_keyboard(),
    )


# --------------------------------------------------------------------------- #
# Старт регистрации (callback / команда)
# --------------------------------------------------------------------------- #
async def _start_registration(target: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ProfileRegistrationStates.name)
    text = (
        "✨ <b>Шаг 1 из 3 — Имя</b>\n\n"
        "Как мне к тебе обращаться? Можно реальное имя или то, "
        "как тебя зовут близкие."
    )
    if isinstance(target, CallbackQuery):
        if target.message is not None:
            await target.message.answer(text)
        await target.answer()
    else:
        await target.answer(text)


@router.callback_query(F.data == CB_START_REG)
async def cb_start_registration(callback: CallbackQuery, state: FSMContext) -> None:
    await _start_registration(callback, state)


@router.message(Command("edit_profile"), StateFilter("*"))
async def cmd_edit_profile(message: Message, state: FSMContext) -> None:
    """Альтернативная команда для запуска регистрации заново."""
    await _start_registration(message, state)


# --------------------------------------------------------------------------- #
# Шаг 1 — Имя
# --------------------------------------------------------------------------- #
@router.message(ProfileRegistrationStates.name, F.text)
async def step_name(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: DbUser | None = None,
) -> None:
    raw = message.text or ""
    try:
        full_name = parse_full_name(raw)
    except ProfileValidationError as exc:
        await message.answer(str(exc))
        return

    data = await state.get_data()
    if data.get("edit_only") == _EDIT_NAME:
        if user is None or message.from_user is None:
            await state.clear()
            await message.answer("Что-то пошло не так. Попробуй /profile.")
            return
        updated = await _save_field(
            session=session,
            telegram_id=message.from_user.id,
            full_name=full_name,
        )
        await state.clear()
        if updated is not None:
            await message.answer(
                "✨ Имя обновлено.\n\n" + _format_profile(updated),
                reply_markup=build_edit_keyboard(),
            )
        return

    await state.update_data(full_name=full_name)
    await state.set_state(ProfileRegistrationStates.birth_date)
    await message.answer(
        "✨ <b>Шаг 2 из 3 — Дата рождения</b>\n\n"
        "Напиши дату своего рождения. Подойдёт формат "
        "<code>1990-05-21</code> или <code>21.05.1990</code>."
    )


# --------------------------------------------------------------------------- #
# Шаг 2 — Дата рождения
# --------------------------------------------------------------------------- #
@router.message(ProfileRegistrationStates.birth_date, F.text)
async def step_birth_date(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: DbUser | None = None,
) -> None:
    raw = message.text or ""
    try:
        parsed = parse_birth_date(raw)
    except ProfileValidationError as exc:
        await message.answer(str(exc))
        return

    data = await state.get_data()
    if data.get("edit_only") == _EDIT_DOB:
        if user is None or message.from_user is None:
            await state.clear()
            await message.answer("Что-то пошло не так. Попробуй /profile.")
            return
        updated = await _save_field(
            session=session,
            telegram_id=message.from_user.id,
            birth_date=parsed,
        )
        await state.clear()
        if updated is not None:
            await message.answer(
                "✨ Дата рождения обновлена.\n\n" + _format_profile(updated),
                reply_markup=build_edit_keyboard(),
            )
        return

    # В state кладём ISO-строку: RedisStorage по умолчанию использует json.
    await state.update_data(birth_date=parsed.isoformat())
    await state.set_state(ProfileRegistrationStates.gender)
    await message.answer(
        "✨ <b>Шаг 3 из 3 — Пол</b>\n\nВыбери:",
        reply_markup=build_gender_keyboard(),
    )


# --------------------------------------------------------------------------- #
# Шаг 3 — Пол
# --------------------------------------------------------------------------- #
@router.callback_query(
    ProfileRegistrationStates.gender,
    F.data.startswith(f"{CB_GENDER_PREFIX}:"),
)
async def step_gender(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: DbUser | None = None,
) -> None:
    if callback.data is None or callback.from_user is None:
        await callback.answer()
        return
    gender = gender_from_callback(callback.data)
    if gender is None:
        await callback.answer("Эта дорога не ведёт к ответу.", show_alert=False)
        return

    data = await state.get_data()
    if data.get("edit_only") == _EDIT_GENDER:
        if user is None:
            await state.clear()
            await callback.answer("Что-то пошло не так. Попробуй /profile.")
            return
        updated = await _save_field(
            session=session,
            telegram_id=callback.from_user.id,
            gender=gender,
        )
        await state.clear()
        if updated is not None and callback.message is not None:
            await callback.message.answer(
                "✨ Пол обновлён.\n\n" + _format_profile(updated),
                reply_markup=build_edit_keyboard(),
            )
        await callback.answer()
        return

    await state.update_data(gender=gender.value)
    await state.set_state(ProfileRegistrationStates.confirm)
    summary_data = await state.get_data()
    if callback.message is not None:
        await callback.message.answer(
            _format_summary(summary_data),
            reply_markup=build_confirm_keyboard(),
        )
    await callback.answer()


# --------------------------------------------------------------------------- #
# Шаг 4 — Подтверждение
# --------------------------------------------------------------------------- #
@router.callback_query(ProfileRegistrationStates.confirm, F.data == CB_CONFIRM)
async def step_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: DbUser | None = None,
) -> None:
    if user is None or callback.from_user is None:
        await callback.answer(
            "Звёзды потеряли тебя на мгновение. Попробуй ещё раз через /profile.",
            show_alert=True,
        )
        await state.clear()
        return

    data = await state.get_data()
    full_name = data.get("full_name")
    birth_iso = data.get("birth_date")
    gender_value = data.get("gender")

    if not full_name or not birth_iso or not gender_value:
        await callback.answer(
            "Не все данные дошли до звёзд. Начнём заново через /profile.",
            show_alert=True,
        )
        await state.clear()
        return

    try:
        birth_date = date.fromisoformat(birth_iso)
        gender = Gender(gender_value)
    except (TypeError, ValueError):
        logger.exception("invalid FSM data for user_id=%s", callback.from_user.id)
        await callback.answer("Данные испортились в дороге. /profile — и заново.")
        await state.clear()
        return

    updated = await _save_field(
        session=session,
        telegram_id=callback.from_user.id,
        full_name=full_name,
        birth_date=birth_date,
        gender=gender,
    )
    await state.clear()

    if updated is None:
        logger.warning(
            "update_profile returned None for user_id=%s", callback.from_user.id
        )
        await callback.answer()
        return

    if callback.message is not None:
        await callback.message.answer(
            "✨ <b>Профиль сохранён.</b>\n\n"
            + _format_profile(updated)
            + "\n\nТеперь звёзды видят тебя точно. "
            "Открой /help, чтобы узнать, что я умею."
        )
    await callback.answer("Готово ✨")


# --------------------------------------------------------------------------- #
# Отмена / редактирование
# --------------------------------------------------------------------------- #
@router.callback_query(F.data == CB_CANCEL)
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is not None:
        await callback.message.answer(
            "Хорошо, оставим как есть. Когда будешь готов — снова /profile."
        )
    await callback.answer()


@router.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer("Сейчас нечего отменять.")
        return
    await state.clear()
    await message.answer("Регистрация отменена. Когда захочешь — /profile.")


@router.callback_query(F.data == CB_EDIT_NAME)
async def cb_edit_name(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ProfileRegistrationStates.name)
    await state.update_data(edit_only=_EDIT_NAME)
    if callback.message is not None:
        await callback.message.answer("Напиши новое имя:")
    await callback.answer()


@router.callback_query(F.data == CB_EDIT_DOB)
async def cb_edit_dob(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ProfileRegistrationStates.birth_date)
    await state.update_data(edit_only=_EDIT_DOB)
    if callback.message is not None:
        await callback.message.answer(
            "Напиши новую дату рождения (например, <code>21.05.1990</code>):"
        )
    await callback.answer()


@router.callback_query(F.data == CB_EDIT_GENDER)
async def cb_edit_gender(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ProfileRegistrationStates.gender)
    await state.update_data(edit_only=_EDIT_GENDER)
    if callback.message is not None:
        await callback.message.answer(
            "Выбери пол:", reply_markup=build_gender_keyboard()
        )
    await callback.answer()


@router.callback_query(F.data == CB_EDIT_RESTART)
async def cb_edit_restart(callback: CallbackQuery, state: FSMContext) -> None:
    await _start_registration(callback, state)


__all__ = ["cmd_profile", "router"]
