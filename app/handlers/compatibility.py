"""Хендлер `/compatibility` — анализ совместимости двух дат рождения.

Поток:
    /compatibility (или кнопка «Совместимость»)
        ↓
    Шаг 1 — имя партнёра
        ↓
    Шаг 2 — дата рождения партнёра
        ↓
    Шаг 3 — подтверждение
        ↓
    расчёт (numerology) → AI-интерпретация → сохранение → карточка

Свою дату рождения берём из профиля. Если профиля нет — ведём через /profile.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from openai import OpenAIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards.compatibility import (
    CB_COMPAT_CANCEL,
    CB_COMPAT_CONFIRM,
    build_confirm_keyboard,
)
from app.keyboards.main_menu import BTN_COMPATIBILITY
from app.keyboards.profile import build_register_start_keyboard
from app.models.user import User as DbUser
from app.repositories.compatibility_check import CompatibilityCheckRepository
from app.services.ai.service import AIService
from app.services.compatibility import CompatibilityScores, calculate_scores
from app.services.profile import (
    ProfileValidationError,
    parse_birth_date,
    parse_full_name,
)
from app.states.compatibility import CompatibilityStates

logger = logging.getLogger(__name__)
router = Router(name="compatibility")


_FALLBACK_AI = (
    "✨ Звёзды в этот миг затихли — голос их я не разобрал. "
    "Числа уже у тебя в карточке выше, попробуй спросить интерпретацию чуть позже."
)


# --------------------------------------------------------------------------- #
# Хелперы
# --------------------------------------------------------------------------- #
def _format_summary(data: dict[str, Any]) -> str:
    return (
        "<b>Проверь данные партнёра</b>\n\n"
        f"• Имя: <b>{data.get('partner_name', '—')}</b>\n"
        f"• Дата рождения: <b>{data.get('partner_birth_date', '—')}</b>\n\n"
        "Если всё верно — нажми «Считать». Если ошибся — «Отмена» и начни заново."
    )


def _format_scores_card(scores: CompatibilityScores, partner_name: str) -> str:
    """Карточка с числами — отдаётся до AI-интерпретации, чтобы пользователь
    получил мгновенный отклик даже при тормозящем OpenAI."""
    return (
        f"💞 <b>Совместимость с {partner_name}</b>\n\n"
        f"<b>Жизненные пути:</b> "
        f"{scores.user_life_path} ↔ {scores.partner_life_path}\n\n"
        f"• Эмоциональная связь: <b>{scores.emotional_score}/100</b>\n"
        f"• Конфликтность: <b>{scores.conflict_score}/100</b>\n"
        f"• Романтика: <b>{scores.romance_score}/100</b>\n"
        f"• Кармическая нить: <b>{scores.karmic_score}/100</b>\n\n"
        f"<i>Общий индекс: {scores.overall}/100</i>"
    )


# --------------------------------------------------------------------------- #
# Точка входа
# --------------------------------------------------------------------------- #
async def _start_flow(target: Message | CallbackQuery, state: FSMContext, user: DbUser | None) -> None:
    if user is None or not user.is_registered or user.birth_date is None:
        text = (
            "<b>Чтобы оценить совместимость, мне нужна твоя дата рождения.</b>\n\n"
            "Пройди короткую регистрацию через /profile."
        )
        if isinstance(target, CallbackQuery):
            if target.message is not None:
                await target.message.answer(text, reply_markup=build_register_start_keyboard())
            await target.answer()
        else:
            await target.answer(text, reply_markup=build_register_start_keyboard())
        return

    await state.clear()
    await state.set_state(CompatibilityStates.partner_name)
    text = (
        "💞 <b>Совместимость — шаг 1 из 2</b>\n\n"
        "Назови имя того, с кем хочешь проверить связь."
    )
    if isinstance(target, CallbackQuery):
        if target.message is not None:
            await target.message.answer(text)
        await target.answer()
    else:
        await target.answer(text)


@router.message(Command("compatibility"), StateFilter("*"))
async def cmd_compatibility(
    message: Message,
    state: FSMContext,
    user: DbUser | None = None,
) -> None:
    await _start_flow(message, state, user)


@router.message(F.text == BTN_COMPATIBILITY)
async def menu_compatibility(
    message: Message,
    state: FSMContext,
    user: DbUser | None = None,
) -> None:
    await _start_flow(message, state, user)


# --------------------------------------------------------------------------- #
# Шаг 1 — имя партнёра
# --------------------------------------------------------------------------- #
@router.message(CompatibilityStates.partner_name, F.text)
async def step_partner_name(message: Message, state: FSMContext) -> None:
    raw = message.text or ""
    try:
        partner_name = parse_full_name(raw)
    except ProfileValidationError as exc:
        await message.answer(str(exc))
        return

    await state.update_data(partner_name=partner_name)
    await state.set_state(CompatibilityStates.partner_birth_date)
    await message.answer(
        "💞 <b>Шаг 2 из 2 — дата рождения партнёра</b>\n\n"
        "Напиши дату в формате <code>1990-05-21</code> или <code>21.05.1990</code>."
    )


# --------------------------------------------------------------------------- #
# Шаг 2 — дата рождения партнёра
# --------------------------------------------------------------------------- #
@router.message(CompatibilityStates.partner_birth_date, F.text)
async def step_partner_birth_date(message: Message, state: FSMContext) -> None:
    raw = message.text or ""
    try:
        parsed = parse_birth_date(raw)
    except ProfileValidationError as exc:
        await message.answer(str(exc))
        return

    await state.update_data(partner_birth_date=parsed.isoformat())
    await state.set_state(CompatibilityStates.confirm)
    summary = await state.get_data()
    await message.answer(_format_summary(summary), reply_markup=build_confirm_keyboard())


# --------------------------------------------------------------------------- #
# Шаг 3 — расчёт и сохранение
# --------------------------------------------------------------------------- #
@router.callback_query(CompatibilityStates.confirm, F.data == CB_COMPAT_CONFIRM)
async def cb_compat_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    ai_service: AIService,
    user: DbUser | None = None,
) -> None:
    if user is None or user.birth_date is None or callback.from_user is None:
        await callback.answer(
            "Звёзды потеряли тебя на мгновение. /compatibility — и заново.",
            show_alert=True,
        )
        await state.clear()
        return

    data = await state.get_data()
    partner_name = data.get("partner_name")
    partner_birth_iso = data.get("partner_birth_date")
    if not partner_name or not partner_birth_iso:
        await callback.answer("Не все данные дошли до звёзд. Начнём заново.", show_alert=True)
        await state.clear()
        return

    try:
        partner_birth = date.fromisoformat(partner_birth_iso)
    except (TypeError, ValueError):
        logger.exception("invalid FSM partner birth_date for user_id=%s", user.id)
        await callback.answer("Данные испортились в дороге. /compatibility — и заново.")
        await state.clear()
        return

    scores = calculate_scores(user.birth_date, partner_birth)
    await state.clear()

    if callback.message is not None:
        await callback.message.answer(_format_scores_card(scores, partner_name))

    # AI-интерпретация — отдельным сообщением, чтобы карточка ушла мгновенно.
    interpretation = await _ai_interpretation(ai_service, user, partner_name, partner_birth, scores)

    # Сохраняем запись (даже если AI вернул fallback — числа всё равно ценны).
    await CompatibilityCheckRepository(session).create(
        user_id=user.id,
        user_birth_date=user.birth_date,
        partner_birth_date=partner_birth,
        emotional_score=scores.emotional_score,
        conflict_score=scores.conflict_score,
        romance_score=scores.romance_score,
        karmic_score=scores.karmic_score,
        interpretation=interpretation,
    )

    if callback.message is not None:
        await callback.message.answer(f"🔮 <b>Толкование</b>\n\n{interpretation}")
    await callback.answer("Готово ✨")


async def _ai_interpretation(
    ai_service: AIService,
    user: DbUser,
    partner_name: str,
    partner_birth: date,
    scores: CompatibilityScores,
) -> str:
    try:
        return await ai_service.generate_compatibility_interpretation(
            user=user,
            partner_name=partner_name,
            partner_birth_date=partner_birth,
            scores=scores,
        )
    except OpenAIError:
        logger.exception("openai failure in /compatibility for user_id=%s", user.id)
        return _FALLBACK_AI
    except Exception:
        logger.exception("unexpected error in /compatibility for user_id=%s", user.id)
        return _FALLBACK_AI


@router.callback_query(CompatibilityStates.confirm, F.data == CB_COMPAT_CANCEL)
async def cb_compat_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is not None:
        await callback.message.answer(
            "Хорошо, отложим. Когда будешь готов — снова /compatibility."
        )
    await callback.answer()


__all__ = ["cmd_compatibility", "router"]
