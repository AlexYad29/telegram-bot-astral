"""Прогноз дня — первый AI-хендлер.

Стрим/долгие генерации пока не используем: один запрос → один ответ.
Анти-спам уже навешен глобально на уровне middleware, дополнительный лимит
здесь не нужен.
"""

from __future__ import annotations

import logging
from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from openai import OpenAIError

from app.config.settings import get_settings
from app.keyboards.main_menu import BTN_FORECAST
from app.keyboards.profile import build_register_start_keyboard
from app.models.user import User as DbUser
from app.services.ai.service import AIService

logger = logging.getLogger(__name__)
router = Router(name="forecast")


_FALLBACK = (
    "✨ Звёзды сейчас затянуло облаком — голос их слышу нечётко. "
    "Попробуй спросить ещё раз чуть позже."
)


async def _send_daily_forecast(
    message: Message,
    user: DbUser | None,
    ai_service: AIService,
) -> None:
    if user is None or not user.is_registered:
        await message.answer(
            "<b>Чтобы прочитать твой день, нужна точка отсчёта</b> — "
            "имя и дата рождения.\n\n"
            "Пройди короткую регистрацию через /profile.",
            reply_markup=build_register_start_keyboard(),
        )
        return

    settings = get_settings()
    try:
        # Локальное «сегодня» в часовой зоне приложения — позже, когда подключим
        # tz-aware utilities, заменим на нормальный `now(settings.timezone)`.
        text = await ai_service.generate_daily_forecast(user, today=date.today())
    except OpenAIError:
        logger.exception("openai failure in /forecast for user_id=%s", user.id)
        await message.answer(_FALLBACK)
        return
    except Exception:
        logger.exception("unexpected error in /forecast for user_id=%s", user.id)
        await message.answer(_FALLBACK)
        return

    if not text:
        logger.warning(
            "empty AI response for /forecast user_id=%s model=%s",
            user.id,
            settings.openai_model,
        )
        await message.answer(_FALLBACK)
        return

    await message.answer(f"🌙 <b>Твой прогноз на сегодня</b>\n\n{text}")


@router.message(Command("forecast"))
async def cmd_forecast(
    message: Message,
    ai_service: AIService,
    user: DbUser | None = None,
) -> None:
    await _send_daily_forecast(message, user, ai_service)


@router.message(F.text == BTN_FORECAST)
async def menu_forecast(
    message: Message,
    ai_service: AIService,
    user: DbUser | None = None,
) -> None:
    await _send_daily_forecast(message, user, ai_service)


@router.callback_query(F.data == "forecast:retry")
async def cb_forecast_retry(
    callback: CallbackQuery,
    ai_service: AIService,
    user: DbUser | None = None,
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    if isinstance(callback.message, Message):
        await _send_daily_forecast(callback.message, user, ai_service)
    await callback.answer()


__all__ = ["cmd_forecast", "router"]
