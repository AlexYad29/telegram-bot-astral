"""Inline-клавиатуры для подписки и платежей."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.subscription import PlanOffer

# Префикс callback'ов — короткий, чтобы влезть в Telegram-лимит 64 байта.
CB_UPGRADE_PREFIX = "sub:buy:"
CB_CANCEL = "sub:cancel"
CB_RENEW = "sub:renew"


def build_offers_keyboard(offers: list[PlanOffer]) -> InlineKeyboardMarkup:
    """Сетка из офферов: каждая кнопка — отдельный тариф."""
    rows: list[list[InlineKeyboardButton]] = []
    for offer in offers:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{offer.title} — {offer.price_stars} ⭐",
                    callback_data=f"{CB_UPGRADE_PREFIX}{offer.code}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_subscription_status_keyboard(
    *, is_premium: bool, has_active: bool
) -> InlineKeyboardMarkup:
    """Кнопки под «текущий статус подписки»."""
    rows: list[list[InlineKeyboardButton]] = []
    if is_premium:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔁 Продлить", callback_data=CB_RENEW
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="⭐ Открыть Premium", callback_data=CB_RENEW
                )
            ]
        )
    if has_active:
        rows.append(
            [
                InlineKeyboardButton(
                    text="❌ Отменить авто-продление",
                    callback_data=CB_CANCEL,
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


__all__ = [
    "CB_CANCEL",
    "CB_RENEW",
    "CB_UPGRADE_PREFIX",
    "build_offers_keyboard",
    "build_subscription_status_keyboard",
]
