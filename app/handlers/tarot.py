"""Хендлер `/tarot` — трёхкарточный расклад «Прошлое — Настоящее — Будущее».

Поток:
    /tarot (или кнопка «Таро»)
        ↓
    Шаг 1 — пользователь пишет вопрос или жмёт «без вопроса»
        ↓
    тянем 3 уникальные карты старших арканов (часть может выпасть
    в перевёрнутом положении)
        ↓
    показываем карточку с картами → AI-толкование → сохраняем
    в `tarot_history`

Свой профиль для регистрации НЕ требуется — Таро доступно и анонимам,
просто прогноз будет обезличенным.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from openai import OpenAIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards.main_menu import BTN_TAROT
from app.keyboards.tarot import (
    CB_TAROT_CANCEL,
    CB_TAROT_DRAW_NO_QUESTION,
    build_pre_draw_keyboard,
)
from app.models.enums import TarotSpreadKind
from app.models.user import User as DbUser
from app.repositories.tarot_history import TarotHistoryRepository
from app.services.ai.prompts import TarotCardContext
from app.services.ai.service import AIService
from app.services.tarot import (
    DeckError,
    DrawnCard,
    draw_three_card_spread,
    position_label_ru,
)
from app.states.tarot import TarotStates

logger = logging.getLogger(__name__)
router = Router(name="tarot")


_FALLBACK_AI = (
    "🃏 Карты легли, но голос их сегодня тих. "
    "Сам расклад уже у тебя выше — попробуй вернуться за толкованием чуть позже."
)
_DECK_ERROR_MSG = (
    "🃏 Колода куда-то запропастилась. Я уже зову её обратно — попробуй чуть позже."
)


def _format_cards_message(cards: tuple[DrawnCard, ...]) -> str:
    lines: list[str] = ["🃏 <b>Расклад «Прошлое — Настоящее — Будущее»</b>\n"]
    for drawn in cards:
        orient = " <i>(перевёрнутая)</i>" if drawn.reversed else ""
        lines.append(
            f"<b>{position_label_ru(drawn.position)}</b> — "
            f"{drawn.card.name_ru}{orient}\n"
            f"<i>{drawn.card.meaning(reversed_=drawn.reversed)}</i>"
        )
    return "\n\n".join(lines)


def _to_card_contexts(cards: tuple[DrawnCard, ...]) -> tuple[TarotCardContext, ...]:
    return tuple(
        TarotCardContext(
            position_label=position_label_ru(drawn.position),
            name_ru=drawn.card.name_ru,
            name_en=drawn.card.name_en,
            reversed=drawn.reversed,
            keywords=drawn.card.keywords,
            meaning_short=drawn.card.meaning(reversed_=drawn.reversed),
        )
        for drawn in cards
    )


# --------------------------------------------------------------------------- #
# Точка входа
# --------------------------------------------------------------------------- #
async def _start_flow(target: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(TarotStates.question)
    text = (
        "🃏 <b>Расклад на трёх картах</b>\n\n"
        "Сформулируй вопрос, на который ищешь ответ — одной фразой. "
        "Или нажми «Без вопроса», чтобы получить общий расклад на ближайшее время."
    )
    if isinstance(target, CallbackQuery):
        if target.message is not None:
            await target.message.answer(text, reply_markup=build_pre_draw_keyboard())
        await target.answer()
    else:
        await target.answer(text, reply_markup=build_pre_draw_keyboard())


@router.message(Command("tarot"), StateFilter("*"))
async def cmd_tarot(message: Message, state: FSMContext) -> None:
    await _start_flow(message, state)


@router.message(F.text == BTN_TAROT)
async def menu_tarot(message: Message, state: FSMContext) -> None:
    await _start_flow(message, state)


# --------------------------------------------------------------------------- #
# Шаг 1а — пользователь прислал текст вопроса
# --------------------------------------------------------------------------- #
@router.message(TarotStates.question, F.text)
async def step_tarot_question(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    ai_service: AIService,
    user: DbUser | None = None,
) -> None:
    raw = (message.text or "").strip()
    # Длинные вопросы режем — это идёт в БД и в промпт.
    question = raw[:500] if raw else None
    await _draw_and_reply(
        target=message,
        state=state,
        session=session,
        ai_service=ai_service,
        user=user,
        question=question,
    )


# --------------------------------------------------------------------------- #
# Шаг 1б — пользователь нажал «без вопроса»
# --------------------------------------------------------------------------- #
@router.callback_query(TarotStates.question, F.data == CB_TAROT_DRAW_NO_QUESTION)
async def cb_tarot_draw_no_question(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    ai_service: AIService,
    user: DbUser | None = None,
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    await _draw_and_reply(
        target=callback.message,
        state=state,
        session=session,
        ai_service=ai_service,
        user=user,
        question=None,
    )
    await callback.answer()


@router.callback_query(TarotStates.question, F.data == CB_TAROT_CANCEL)
async def cb_tarot_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is not None:
        await callback.message.answer(
            "Хорошо, оставим карты в колоде. Когда будешь готов — снова /tarot."
        )
    await callback.answer()


# --------------------------------------------------------------------------- #
# Сам розыгрыш + AI + сохранение
# --------------------------------------------------------------------------- #
async def _draw_and_reply(
    *,
    target: Message,
    state: FSMContext,
    session: AsyncSession,
    ai_service: AIService,
    user: DbUser | None,
    question: str | None,
) -> None:
    await state.clear()

    try:
        cards = draw_three_card_spread()
    except DeckError:
        logger.exception("tarot deck failure")
        await target.answer(_DECK_ERROR_MSG)
        return

    await target.answer(_format_cards_message(cards))

    interpretation = await _ai_interpretation(
        ai_service=ai_service,
        user=user,
        question=question,
        cards=cards,
    )

    if user is not None:
        await TarotHistoryRepository(session).create(
            user_id=user.id,
            spread_kind=TarotSpreadKind.THREE_CARD,
            cards=[drawn.as_dict() for drawn in cards],
            interpretation=interpretation,
        )

    await target.answer(f"🔮 <b>Толкование расклада</b>\n\n{interpretation}")


async def _ai_interpretation(
    *,
    ai_service: AIService,
    user: DbUser | None,
    question: str | None,
    cards: tuple[DrawnCard, ...],
) -> str:
    try:
        return await ai_service.generate_tarot_interpretation(
            user=user,
            question=question,
            cards=_to_card_contexts(cards),
        )
    except OpenAIError:
        logger.exception(
            "openai failure in /tarot for user_id=%s", getattr(user, "id", None)
        )
        return _FALLBACK_AI
    except Exception:
        logger.exception(
            "unexpected error in /tarot for user_id=%s", getattr(user, "id", None)
        )
        return _FALLBACK_AI


__all__ = ["cmd_tarot", "router"]
