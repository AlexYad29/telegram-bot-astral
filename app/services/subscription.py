"""SubscriptionService — бизнес-логика подписок и платежей.

Чистая обёртка над репозиториями. Решает:

* какие тарифы существуют (`PLAN_CATALOG`) и почём;
* активировать / продлить подписку у пользователя;
* проверить, есть ли у юзера активная подписка (с учётом grace-периода);
* выдать реферальный бонус (продлить Premium на N дней) обоим участникам;
* обработать `successful_payment` от Telegram Stars.

Никаких aiogram-импортов — слой переиспользуется в admin-команде
(`/grant_premium`) и в cron-джобе (`expire_due`).
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.config.settings import Settings
from app.models.enums import (
    PaymentProvider,
    PaymentStatus,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.payment import Payment
from app.models.subscription import Subscription
from app.repositories.payment import PaymentRepository
from app.repositories.referral import ReferralRepository
from app.repositories.subscription import SubscriptionRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Каталог тарифов
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanOffer:
    """Один пункт прайс-листа: «Premium на 30 дней за 199 ⭐»."""

    code: str  # уникальный код, попадает в invoice payload
    plan: SubscriptionPlan
    duration_days: int
    price_stars: int  # сумма в XTR (Telegram Stars)
    title: str
    description: str

    @property
    def per_day_stars(self) -> float:
        return self.price_stars / max(1, self.duration_days)


def build_plan_catalog(settings: Settings) -> dict[str, PlanOffer]:
    """Собрать каталог тарифов из настроек.

    Cловарь keyed by `code` — чтобы быстро найти оффер по invoice payload.
    """
    return {
        offer.code: offer
        for offer in (
            PlanOffer(
                code="premium_1m",
                plan=SubscriptionPlan.PREMIUM,
                duration_days=settings.subscription_days_1m,
                price_stars=settings.subscription_stars_premium_1m,
                title="Premium · 1 месяц",
                description=(
                    "Безлимит на прогнозы и таро, расширенная совместимость, "
                    "приоритет в очереди ответа."
                ),
            ),
            PlanOffer(
                code="premium_3m",
                plan=SubscriptionPlan.PREMIUM,
                duration_days=settings.subscription_days_3m,
                price_stars=settings.subscription_stars_premium_3m,
                title="Premium · 3 месяца",
                description="Все возможности Premium со скидкой ~16%.",
            ),
            PlanOffer(
                code="premium_12m",
                plan=SubscriptionPlan.PREMIUM,
                duration_days=settings.subscription_days_12m,
                price_stars=settings.subscription_stars_premium_12m,
                title="Premium · 12 месяцев",
                description="Premium на год со скидкой ~37%.",
            ),
            PlanOffer(
                code="vip_1m",
                plan=SubscriptionPlan.VIP,
                duration_days=settings.subscription_days_1m,
                price_stars=settings.subscription_stars_vip_1m,
                title="VIP · 1 месяц",
                description=(
                    "Всё из Premium + длинные расклады, доступ к личным "
                    "ритуалам и расширенной нумерологии."
                ),
            ),
        )
    }


# ---------------------------------------------------------------------------
# Статус подписки
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubscriptionStatusInfo:
    """Снимок состояния подписки конкретного пользователя.

    Используется в middleware (инжектим в data) и в /subscription.
    """

    user_id: int
    plan: SubscriptionPlan
    status: SubscriptionStatus
    expires_at: datetime | None
    in_grace_period: bool

    @property
    def is_premium(self) -> bool:
        """True, если у пользователя активна Premium / VIP / Lifetime подписка
        (с учётом grace-периода)."""
        return self.plan in (
            SubscriptionPlan.PREMIUM,
            SubscriptionPlan.VIP,
            SubscriptionPlan.LIFETIME,
        ) and self.status == SubscriptionStatus.ACTIVE

    @property
    def is_vip(self) -> bool:
        return (
            self.plan in (SubscriptionPlan.VIP, SubscriptionPlan.LIFETIME)
            and self.status == SubscriptionStatus.ACTIVE
        )

    @property
    def days_remaining(self) -> int | None:
        if self.expires_at is None:
            return None
        delta = self.expires_at - datetime.now(tz=UTC)
        return max(0, int(delta.total_seconds() // 86400))


# ---------------------------------------------------------------------------
# Сервис
# ---------------------------------------------------------------------------


_FREE_STATUS = SubscriptionStatusInfo(
    user_id=0,
    plan=SubscriptionPlan.FREE,
    status=SubscriptionStatus.ACTIVE,
    expires_at=None,
    in_grace_period=False,
)


class SubscriptionService:
    """Высокоуровневый API для подписок.

    Создаётся per-request в middleware (на одной сессии БД), потому что
    напрямую работает с `AsyncSession` через репозитории.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        subscription_repo: SubscriptionRepository,
        payment_repo: PaymentRepository,
        referral_repo: ReferralRepository,
    ) -> None:
        self._settings = settings
        self._subs = subscription_repo
        self._payments = payment_repo
        self._referrals = referral_repo
        self._catalog = build_plan_catalog(settings)

    # ---------- catalog ----------

    @property
    def catalog(self) -> dict[str, PlanOffer]:
        return self._catalog

    def get_offer(self, code: str) -> PlanOffer | None:
        return self._catalog.get(code)

    # ---------- status ----------

    async def get_status(self, user_id: int) -> SubscriptionStatusInfo:
        """Текущий статус подписки. Free — если активной нет.

        Учитываем grace-период: если `expires_at` уже прошёл, но не больше
        чем на `subscription_grace_days` — статус всё ещё ACTIVE, но
        `in_grace_period=True` (бот мягко напомнит про продление).
        """
        sub = await self._subs.get_active_for_user(user_id)
        if sub is None:
            return SubscriptionStatusInfo(
                user_id=user_id,
                plan=SubscriptionPlan.FREE,
                status=SubscriptionStatus.ACTIVE,
                expires_at=None,
                in_grace_period=False,
            )

        now = datetime.now(tz=UTC)
        expires_at = _ensure_aware(sub.expires_at)
        in_grace = False
        plan = sub.plan
        status = sub.status

        if expires_at is not None and expires_at <= now:
            grace_until = expires_at + timedelta(
                days=self._settings.subscription_grace_days
            )
            if now <= grace_until:
                in_grace = True
            else:
                # Подписка реально кончилась — обновим в БД и вернём FREE.
                await self._subs.expire_due(now=now)
                return SubscriptionStatusInfo(
                    user_id=user_id,
                    plan=SubscriptionPlan.FREE,
                    status=SubscriptionStatus.EXPIRED,
                    expires_at=expires_at,
                    in_grace_period=False,
                )

        return SubscriptionStatusInfo(
            user_id=user_id,
            plan=plan,
            status=status,
            expires_at=expires_at,
            in_grace_period=in_grace,
        )

    async def is_premium(self, user_id: int) -> bool:
        status = await self.get_status(user_id)
        return status.is_premium

    # ---------- activation ----------

    async def activate_or_extend(
        self,
        *,
        user_id: int,
        plan: SubscriptionPlan,
        duration_days: int,
        provider: PaymentProvider,
        payment_id: str | None = None,
        now: datetime | None = None,
    ) -> Subscription:
        """Создать новую активную подписку или продлить уже существующую.

        Если у пользователя уже есть активная подписка того же плана (или
        текущая — FREE/EXPIRED), просто продлеваем срок. Если у юзера
        Premium и он покупает VIP — апгрейдим план и сдвигаем `expires_at`
        от текущего max(now, current_expires_at).
        """
        now = now or datetime.now(tz=UTC)
        current = await self._subs.get_active_for_user(user_id)

        if current is None:
            return await self._subs.create(
                user_id=user_id,
                plan=plan,
                started_at=now,
                expires_at=now + timedelta(days=duration_days),
                payment_provider=provider.value,
                payment_id=payment_id,
            )

        current_expires = _ensure_aware(current.expires_at)
        base = max(now, current_expires) if current_expires else now
        new_expires = base + timedelta(days=duration_days)

        # Если апгрейд с Premium→VIP — обновляем plan, сохраняя оставшееся время.
        new_plan = _max_plan(current.plan, plan)
        extended = await self._subs.extend(
            current.id,
            new_expires_at=new_expires,
            plan=new_plan,
            payment_provider=provider.value,
            payment_id=payment_id,
        )
        return extended or current

    async def cancel(self, user_id: int) -> Subscription | None:
        current = await self._subs.get_active_for_user(user_id)
        if current is None:
            return None
        return await self._subs.cancel(current.id)

    # ---------- Telegram Stars invoice flow ----------

    def new_invoice_payload(self, *, user_id: int, offer_code: str) -> str:
        """Сгенерировать уникальный invoice payload.

        Telegram передаст его обратно в `pre_checkout_query` и `successful_payment`.
        Формат: `{user_id}:{offer_code}:{nonce}` — короткий, в логи влезает.
        """
        nonce = secrets.token_hex(6)
        return f"{user_id}:{offer_code}:{nonce}"

    @staticmethod
    def parse_invoice_payload(payload: str) -> tuple[int, str, str] | None:
        """Разобрать payload обратно в (user_id, offer_code, nonce)."""
        parts = payload.split(":")
        if len(parts) != 3:
            return None
        try:
            user_id = int(parts[0])
        except ValueError:
            return None
        return user_id, parts[1], parts[2]

    async def create_pending_payment(
        self,
        *,
        user_id: int,
        offer: PlanOffer,
        invoice_payload: str,
        provider: PaymentProvider = PaymentProvider.TELEGRAM_STARS,
        currency: str = "XTR",
    ) -> Payment:
        return await self._payments.create_pending(
            user_id=user_id,
            provider=provider,
            plan=offer.plan,
            currency=currency,
            amount=offer.price_stars,
            duration_days=offer.duration_days,
            invoice_payload=invoice_payload,
        )

    async def handle_successful_payment(
        self,
        *,
        user_id: int,
        invoice_payload: str,
        provider_payment_id: str,
        amount: int,
        currency: str,
        now: datetime | None = None,
    ) -> tuple[Subscription, Payment] | None:
        """Завершить платёж: пометить Payment.PAID и активировать подписку.

        Идемпотентно: повторный вызов с тем же `invoice_payload` ничего
        не сломает (мы проверяем статус Payment перед активацией).
        """
        now = now or datetime.now(tz=UTC)
        payment = await self._payments.get_by_payload(invoice_payload)
        if payment is None:
            logger.warning(
                "Successful payment without pending row: payload=%s user=%s",
                invoice_payload,
                user_id,
            )
            return None

        if payment.status == PaymentStatus.PAID:
            # Уже обработан — возвращаем текущую подписку, если есть.
            sub = (
                await self._subs.get(payment.subscription_id)
                if payment.subscription_id
                else None
            )
            return (sub, payment) if sub is not None else None

        subscription = await self.activate_or_extend(
            user_id=user_id,
            plan=payment.plan,
            duration_days=payment.duration_days,
            provider=payment.provider,
            payment_id=provider_payment_id,
            now=now,
        )
        updated = await self._payments.mark_paid(
            payment.id,
            provider_payment_id=provider_payment_id,
            subscription_id=subscription.id,
            paid_at=now,
        )
        if updated is None:
            updated = payment

        # Если это первый платёж пользователя и у него есть referrer — выдаём
        # обоим реферальный бонус.
        await self._maybe_grant_referral_reward(referred_user_id=user_id, now=now)

        logger.info(
            "Payment OK: user=%s plan=%s duration=%sd amount=%s%s id=%s",
            user_id,
            payment.plan.value,
            payment.duration_days,
            amount,
            currency,
            provider_payment_id,
        )
        return subscription, updated

    # ---------- admin grants ----------

    async def grant_manual(
        self,
        *,
        user_id: int,
        days: int,
        plan: SubscriptionPlan = SubscriptionPlan.PREMIUM,
        now: datetime | None = None,
    ) -> Subscription:
        """Ручная выдача Premium админом — без Payment-записи."""
        return await self.activate_or_extend(
            user_id=user_id,
            plan=plan,
            duration_days=days,
            provider=PaymentProvider.MANUAL,
            payment_id=None,
            now=now,
        )

    async def revoke(self, user_id: int) -> bool:
        sub = await self.cancel(user_id)
        return sub is not None

    # ---------- referrals ----------

    async def attach_referrer(
        self, *, referrer_user_id: int, referred_user_id: int
    ) -> bool:
        """Запомнить «X пригласил Y». Бонус выдаётся позже — после
        регистрации профиля или первого платежа Y."""
        result = await self._referrals.attach(
            referrer_user_id=referrer_user_id,
            referred_user_id=referred_user_id,
        )
        return result is not None

    async def grant_referral_reward(
        self, *, referred_user_id: int, now: datetime | None = None
    ) -> bool:
        """Выдать бонус обоим: referrer + referred. Только один раз.

        Используется когда новый пользователь завершил регистрацию профиля.
        """
        return await self._maybe_grant_referral_reward(
            referred_user_id=referred_user_id, now=now
        )

    async def _maybe_grant_referral_reward(
        self, *, referred_user_id: int, now: datetime | None = None
    ) -> bool:
        ref = await self._referrals.get_for_referred(referred_user_id)
        if ref is None or ref.reward_granted_at is not None:
            return False
        now = now or datetime.now(tz=UTC)
        # Бонус Premium на N дней каждому.
        await self.grant_manual(
            user_id=ref.referrer_user_id,
            days=self._settings.referral_bonus_days_referrer,
            plan=SubscriptionPlan.PREMIUM,
            now=now,
        )
        await self.grant_manual(
            user_id=referred_user_id,
            days=self._settings.referral_bonus_days_referred,
            plan=SubscriptionPlan.PREMIUM,
            now=now,
        )
        await self._referrals.mark_rewarded(referred_user_id, granted_at=now)
        logger.info(
            "Referral reward granted: referrer=%s referred=%s (+%sd / +%sd)",
            ref.referrer_user_id,
            referred_user_id,
            self._settings.referral_bonus_days_referrer,
            self._settings.referral_bonus_days_referred,
        )
        return True


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


_PLAN_RANK: dict[SubscriptionPlan, int] = {
    SubscriptionPlan.FREE: 0,
    SubscriptionPlan.PREMIUM: 1,
    SubscriptionPlan.VIP: 2,
    SubscriptionPlan.LIFETIME: 3,
}


def _max_plan(a: SubscriptionPlan, b: SubscriptionPlan) -> SubscriptionPlan:
    return a if _PLAN_RANK[a] >= _PLAN_RANK[b] else b


def _ensure_aware(dt: datetime | None) -> datetime | None:
    """SQLite в тестах возвращает naive datetime — приводим к UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


__all__ = [
    "PlanOffer",
    "SubscriptionService",
    "SubscriptionStatusInfo",
    "build_plan_catalog",
]
