"""Хендлеры подписки и Telegram Stars-платежей.

Контракт:

* `/upgrade` (и кнопка «⭐ Premium») — показывает каталог тарифов inline-кнопками.
* callback `sub:buy:<code>` — отправляет invoice на оплату Stars.
* `pre_checkout_query` — валидируем payload и отвечаем ok=True.
* `successful_payment` — фиксируем Payment.PAID, активируем/продлеваем подписку,
  сообщаем пользователю.
* `/subscription` — показывает текущий статус подписки.
* callback `sub:cancel` — отменяет авто-продление.
* callback `sub:renew` — заново показывает каталог.

Все callbacks отвечают коротким `answer()` чтобы Telegram не подсвечивал
«часики» бесконечно.
"""

from __future__ import annotations

import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from app.config.settings import Settings
from app.keyboards.subscription import (
    CB_CANCEL,
    CB_RENEW,
    CB_UPGRADE_PREFIX,
    build_offers_keyboard,
    build_subscription_status_keyboard,
)
from app.models.enums import SubscriptionPlan
from app.services.subscription import (
    PlanOffer,
    SubscriptionService,
    SubscriptionStatusInfo,
)

logger = logging.getLogger(__name__)
router = Router(name="subscription")


_PLAN_LABELS: dict[SubscriptionPlan, str] = {
    SubscriptionPlan.FREE: "Free",
    SubscriptionPlan.PREMIUM: "Premium ⭐",
    SubscriptionPlan.VIP: "VIP 👑",
    SubscriptionPlan.LIFETIME: "Lifetime ♾",
}


def _format_offers_text(service: SubscriptionService) -> str:
    """Текст «купи Premium»: короткий, без длинного маркетинга."""
    return (
        "⭐ <b>Открой Premium</b>\n\n"
        "С Premium у тебя:\n"
        "• безлимитные прогнозы, таро и совместимость;\n"
        "• приоритет в очереди ответа (выше rate-limit);\n"
        "• расширенные интерпретации (длиннее, глубже).\n\n"
        "Тариф можно выбрать ниже — оплата проходит через Telegram Stars, "
        "это встроенный кошелёк Telegram, никаких карт.\n"
    )


def _format_status_text(
    status: SubscriptionStatusInfo, *, settings: Settings
) -> str:
    """Текст команды /subscription — что у юзера сейчас."""
    plan_label = _PLAN_LABELS.get(status.plan, status.plan.value)

    if not status.is_premium:
        return (
            "📜 <b>Твоя подписка</b>\n\n"
            f"Сейчас у тебя — <b>{plan_label}</b>.\n"
            "Чтобы открыть безлимит и расширенные расклады — выбери Premium ниже."
        )

    if status.expires_at is None:
        # Lifetime
        return (
            "📜 <b>Твоя подписка</b>\n\n"
            f"<b>{plan_label}</b> — бессрочно. ✨"
        )

    days = status.days_remaining or 0
    base = (
        "📜 <b>Твоя подписка</b>\n\n"
        f"Тариф: <b>{plan_label}</b>\n"
        f"Активна до: <code>{status.expires_at.strftime('%Y-%m-%d')}</code>\n"
        f"Осталось: <b>{days} дн.</b>"
    )
    if status.in_grace_period:
        base += (
            f"\n\n⚠️ Подписка истекает (grace-period — "
            f"{settings.subscription_grace_days} дн.). Продли, "
            "чтобы не потерять доступ."
        )
    return base


def _ordered_offers(service: SubscriptionService) -> list[PlanOffer]:
    """Каталог в фиксированном порядке вывода: 1m → 3m → 12m → VIP."""
    order = ("premium_1m", "premium_3m", "premium_12m", "vip_1m")
    return [service.catalog[code] for code in order if code in service.catalog]


# ---------- /upgrade ----------


@router.message(Command("upgrade"))
async def cmd_upgrade(
    message: Message,
    subscription_service: SubscriptionService,
) -> None:
    offers = _ordered_offers(subscription_service)
    await message.answer(
        _format_offers_text(subscription_service),
        reply_markup=build_offers_keyboard(offers),
    )


# ---------- /subscription ----------


@router.message(Command("subscription"))
async def cmd_subscription(
    message: Message,
    subscription_service: SubscriptionService,
    settings: Settings,
    subscription: SubscriptionStatusInfo | None = None,
) -> None:
    if subscription is None:
        if message.from_user is None:
            return
        subscription = await subscription_service.get_status(message.from_user.id)

    text = _format_status_text(subscription, settings=settings)
    await message.answer(
        text,
        reply_markup=build_subscription_status_keyboard(
            is_premium=subscription.is_premium,
            has_active=subscription.expires_at is not None,
        ),
    )


# ---------- callbacks: open offers ----------


@router.callback_query(F.data == CB_RENEW)
async def cb_renew(
    callback: CallbackQuery,
    subscription_service: SubscriptionService,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    offers = _ordered_offers(subscription_service)
    await callback.message.answer(
        _format_offers_text(subscription_service),
        reply_markup=build_offers_keyboard(offers),
    )
    await callback.answer()


@router.callback_query(F.data == CB_CANCEL)
async def cb_cancel(
    callback: CallbackQuery,
    subscription_service: SubscriptionService,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    sub = await subscription_service.cancel(callback.from_user.id)
    if sub is None:
        await callback.answer("Нет активной подписки.", show_alert=True)
        return
    await callback.answer("Авто-продление отменено.", show_alert=True)
    if isinstance(callback.message, Message):
        await callback.message.answer(
            "Готово. Подписка останется активной до конца оплаченного периода, "
            "но автоматически продлеваться не будет."
        )


# ---------- callbacks: buy ----------


@router.callback_query(F.data.startswith(CB_UPGRADE_PREFIX))
async def cb_buy(
    callback: CallbackQuery,
    subscription_service: SubscriptionService,
) -> None:
    if callback.from_user is None or callback.data is None:
        await callback.answer()
        return
    code = callback.data.removeprefix(CB_UPGRADE_PREFIX)
    offer = subscription_service.get_offer(code)
    if offer is None:
        await callback.answer("Тариф больше недоступен.", show_alert=True)
        return

    user_id = callback.from_user.id
    payload = subscription_service.new_invoice_payload(
        user_id=user_id, offer_code=offer.code
    )
    await subscription_service.create_pending_payment(
        user_id=user_id, offer=offer, invoice_payload=payload
    )

    if callback.bot is None or callback.message is None:
        await callback.answer()
        return

    try:
        await callback.bot.send_invoice(
            chat_id=callback.message.chat.id,
            title=offer.title,
            description=offer.description,
            payload=payload,
            # provider_token пуст для Stars (XTR).
            provider_token="",
            currency="XTR",
            prices=[
                LabeledPrice(label=offer.title, amount=offer.price_stars)
            ],
        )
    except Exception:
        logger.exception("send_invoice failed: user=%s offer=%s", user_id, code)
        await callback.answer(
            "Не удалось открыть оплату. Попробуй ещё раз через минуту.",
            show_alert=True,
        )
        return

    await callback.answer()


# ---------- pre_checkout_query ----------


@router.pre_checkout_query()
async def on_pre_checkout(
    query: PreCheckoutQuery,
    subscription_service: SubscriptionService,
) -> None:
    """Telegram спрашивает «можно ли провести платёж»? Валидируем payload."""
    parsed = subscription_service.parse_invoice_payload(query.invoice_payload)
    if parsed is None:
        logger.warning(
            "pre_checkout: bad payload format payload=%s user=%s",
            query.invoice_payload,
            query.from_user.id,
        )
        await query.answer(
            ok=False, error_message="Срок этой оплаты истёк. Попробуй заново через /upgrade."
        )
        return

    payload_user_id, offer_code, _nonce = parsed
    if payload_user_id != query.from_user.id:
        await query.answer(
            ok=False, error_message="Оплата привязана к другому пользователю."
        )
        return

    offer = subscription_service.get_offer(offer_code)
    if offer is None:
        await query.answer(
            ok=False, error_message="Тариф больше недоступен."
        )
        return
    if offer.price_stars != query.total_amount or query.currency != "XTR":
        await query.answer(
            ok=False, error_message="Цена тарифа изменилась. Открой /upgrade ещё раз."
        )
        return

    await query.answer(ok=True)


# ---------- successful_payment ----------


@router.message(F.successful_payment)
async def on_successful_payment(
    message: Message,
    subscription_service: SubscriptionService,
) -> None:
    payment = message.successful_payment
    if payment is None or message.from_user is None:
        return

    result = await subscription_service.handle_successful_payment(
        user_id=message.from_user.id,
        invoice_payload=payment.invoice_payload,
        provider_payment_id=payment.telegram_payment_charge_id,
        amount=payment.total_amount,
        currency=payment.currency,
        now=datetime.now(tz=__import__("datetime").timezone.utc),
    )
    if result is None:
        logger.warning(
            "successful_payment without pending row: user=%s payload=%s",
            message.from_user.id,
            payment.invoice_payload,
        )
        await message.answer(
            "Платёж получен, но я не нашёл связанный счёт. "
            "Я разберусь и активирую подписку вручную — напиши в поддержку."
        )
        return

    sub, _ = result
    plan_label = _PLAN_LABELS.get(sub.plan, sub.plan.value)
    expires = (
        sub.expires_at.strftime("%Y-%m-%d") if sub.expires_at else "бессрочно"
    )
    await message.answer(
        f"✨ <b>Подписка активна!</b>\n\n"
        f"Тариф: <b>{plan_label}</b>\n"
        f"Действует до: <code>{expires}</code>\n\n"
        "Спасибо, что доверяешь звёздам — теперь у тебя безлимит. 🌙"
    )


__all__ = ["router"]
