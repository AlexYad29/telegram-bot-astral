"""Тесты ETAP 13 — монетизация.

Покрываем:
* SubscriptionService: статус, активация/продление, апгрейд Free→Premium→VIP,
  идемпотентный handle_successful_payment, рефералы.
* SubscriptionMiddleware: инжект subscription/subscription_service в data.
* PremiumFilter / VipFilter: чтение `subscription` из data.
* Хендлеры /upgrade, /subscription, cb_buy, on_pre_checkout, on_successful_payment.
* AIRequestThrottle: per-tier лимиты (Free vs Premium).
* Клавиатуры build_offers_keyboard / build_subscription_status_keyboard.

Сервисные тесты гоняем поверх async SQLite в памяти (как уже делают другие тесты),
чтобы не мокать каждый запрос вручную.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import BigInteger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.config.settings import Settings
from app.filters.subscription import PremiumFilter, VipFilter
from app.handlers.subscription import (
    cb_buy,
    cb_cancel,
    cmd_subscription,
    cmd_upgrade,
    on_pre_checkout,
    on_successful_payment,
)
from app.keyboards.subscription import (
    CB_CANCEL,
    CB_RENEW,
    CB_UPGRADE_PREFIX,
    build_offers_keyboard,
    build_subscription_status_keyboard,
)
from app.middlewares.ai_throttling import AIRequestThrottle
from app.middlewares.subscription import SubscriptionMiddleware
from app.models.enums import (
    PaymentProvider,
    PaymentStatus,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.payment import Payment
from app.models.referral import Referral
from app.models.subscription import Subscription
from app.models.user import User
from app.repositories.payment import PaymentRepository
from app.repositories.referral import ReferralRepository
from app.repositories.subscription import SubscriptionRepository
from app.services.subscription import (
    SubscriptionService,
    SubscriptionStatusInfo,
    build_plan_catalog,
)


# SQLite не умеет автоинкремент по BIGINT (нужен обычный INTEGER), поэтому
# при SQLite диалекте упрощаем тип. Тот же хак, что в test_admin_stats/test_scheduler_job.
@compiles(BigInteger, "sqlite")  # type: ignore[misc]
def _bigint_to_integer_for_sqlite(
    element: object, compiler: object, **kw: object
) -> str:
    return "INTEGER"

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _make_settings() -> Settings:
    """Минимальные настройки для сервиса (только то, что он реально читает)."""
    return Settings(
        bot_token="123:abc",
        database_url="sqlite+aiosqlite:///:memory:",
        redis_host="localhost",
        redis_port=6379,
        redis_db=0,
        openai_api_key="sk-test",
        log_level="INFO",
        admin_ids=[],
        channel_id=None,
        environment="test",
    )


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """Изолированная async-сессия поверх SQLite в памяти.

    Создаём только нужные таблицы (не `metadata.create_all`), чтобы не
    приходилось тащить JSONB-колонку `tarot_history.cards` (не компилируется
    под SQLite).
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
        await conn.run_sync(Subscription.__table__.create)
        await conn.run_sync(Payment.__table__.create)
        await conn.run_sync(Referral.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def service(session: AsyncSession) -> SubscriptionService:
    return SubscriptionService(
        settings=_make_settings(),
        subscription_repo=SubscriptionRepository(session),
        payment_repo=PaymentRepository(session),
        referral_repo=ReferralRepository(session),
    )


async def _seed_user(session: AsyncSession, user_id: int) -> None:
    """Положить пользователя в users (FK для subscriptions/payments/referrals)."""
    user = User(id=user_id, telegram_username=f"u{user_id}")
    session.add(user)
    await session.flush()


# ---------------------------------------------------------------------------
# build_plan_catalog
# ---------------------------------------------------------------------------


def test_build_plan_catalog_contains_expected_offers() -> None:
    catalog = build_plan_catalog(_make_settings())
    assert {"premium_1m", "premium_3m", "premium_12m", "vip_1m"} <= set(catalog.keys())
    p1 = catalog["premium_1m"]
    assert p1.plan == SubscriptionPlan.PREMIUM
    assert p1.duration_days > 0
    assert p1.price_stars > 0
    # 3m выгоднее 1m в пересчёте на день.
    assert catalog["premium_3m"].per_day_stars <= p1.per_day_stars
    assert catalog["premium_12m"].per_day_stars < p1.per_day_stars
    # VIP дороже за день, чем Premium 1m.
    assert catalog["vip_1m"].per_day_stars > p1.per_day_stars


# ---------------------------------------------------------------------------
# SubscriptionService.get_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_status_returns_free_when_no_subscription(
    service: SubscriptionService,
    session: AsyncSession,
) -> None:
    await _seed_user(session, 42)
    status = await service.get_status(42)
    assert status.plan == SubscriptionPlan.FREE
    assert status.status == SubscriptionStatus.ACTIVE
    assert status.is_premium is False
    assert status.is_vip is False
    assert status.expires_at is None
    assert status.in_grace_period is False


@pytest.mark.asyncio
async def test_get_status_returns_active_premium_with_days_left(
    service: SubscriptionService,
    session: AsyncSession,
) -> None:
    await _seed_user(session, 7)
    await service.activate_or_extend(
        user_id=7,
        plan=SubscriptionPlan.PREMIUM,
        duration_days=30,
        provider=PaymentProvider.TELEGRAM_STARS,
    )
    status = await service.get_status(7)
    assert status.is_premium is True
    assert status.is_vip is False
    assert status.plan == SubscriptionPlan.PREMIUM
    assert status.expires_at is not None
    assert status.days_remaining is not None
    assert 28 <= status.days_remaining <= 30


@pytest.mark.asyncio
async def test_get_status_grace_period_keeps_active(
    service: SubscriptionService,
    session: AsyncSession,
) -> None:
    """Если подписка истекла, но не прошёл grace — статус всё ещё ACTIVE
    с in_grace_period=True."""
    await _seed_user(session, 9)
    now = datetime.now(tz=UTC)
    # Истекла «вчера», grace = 2 дня (см. settings).
    sub_repo = SubscriptionRepository(session)
    await sub_repo.create(
        user_id=9,
        plan=SubscriptionPlan.PREMIUM,
        started_at=now - timedelta(days=31),
        expires_at=now - timedelta(hours=12),
    )
    status = await service.get_status(9)
    assert status.is_premium is True
    assert status.in_grace_period is True


@pytest.mark.asyncio
async def test_get_status_expired_past_grace_marks_expired(
    service: SubscriptionService,
    session: AsyncSession,
) -> None:
    await _seed_user(session, 11)
    now = datetime.now(tz=UTC)
    sub_repo = SubscriptionRepository(session)
    await sub_repo.create(
        user_id=11,
        plan=SubscriptionPlan.PREMIUM,
        started_at=now - timedelta(days=60),
        expires_at=now - timedelta(days=30),
    )
    status = await service.get_status(11)
    assert status.is_premium is False
    assert status.plan == SubscriptionPlan.FREE
    assert status.status == SubscriptionStatus.EXPIRED


# ---------------------------------------------------------------------------
# SubscriptionService.activate_or_extend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_activate_first_time_creates_subscription(
    service: SubscriptionService,
    session: AsyncSession,
) -> None:
    await _seed_user(session, 100)
    sub = await service.activate_or_extend(
        user_id=100,
        plan=SubscriptionPlan.PREMIUM,
        duration_days=30,
        provider=PaymentProvider.TELEGRAM_STARS,
    )
    assert sub.user_id == 100
    assert sub.plan == SubscriptionPlan.PREMIUM
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.expires_at is not None


@pytest.mark.asyncio
async def test_activate_extends_existing_subscription(
    service: SubscriptionService,
    session: AsyncSession,
) -> None:
    await _seed_user(session, 200)
    first = await service.activate_or_extend(
        user_id=200,
        plan=SubscriptionPlan.PREMIUM,
        duration_days=30,
        provider=PaymentProvider.TELEGRAM_STARS,
    )
    assert first.expires_at is not None
    expires_after_first = first.expires_at
    # +90 дней поверх существующей.
    second = await service.activate_or_extend(
        user_id=200,
        plan=SubscriptionPlan.PREMIUM,
        duration_days=90,
        provider=PaymentProvider.TELEGRAM_STARS,
    )
    assert second.id == first.id
    assert second.expires_at is not None
    delta = second.expires_at - expires_after_first
    # ≥89 дней потому, что между двумя вызовами могло пройти микро-время.
    assert delta.days >= 89


@pytest.mark.asyncio
async def test_activate_upgrades_premium_to_vip(
    service: SubscriptionService,
    session: AsyncSession,
) -> None:
    await _seed_user(session, 300)
    await service.activate_or_extend(
        user_id=300,
        plan=SubscriptionPlan.PREMIUM,
        duration_days=30,
        provider=PaymentProvider.TELEGRAM_STARS,
    )
    sub = await service.activate_or_extend(
        user_id=300,
        plan=SubscriptionPlan.VIP,
        duration_days=30,
        provider=PaymentProvider.TELEGRAM_STARS,
    )
    assert sub.plan == SubscriptionPlan.VIP
    status = await service.get_status(300)
    assert status.is_vip is True


# ---------------------------------------------------------------------------
# cancel / revoke
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_sets_status_cancelled(
    service: SubscriptionService,
    session: AsyncSession,
) -> None:
    await _seed_user(session, 400)
    await service.activate_or_extend(
        user_id=400,
        plan=SubscriptionPlan.PREMIUM,
        duration_days=30,
        provider=PaymentProvider.TELEGRAM_STARS,
    )
    sub = await service.cancel(400)
    assert sub is not None
    assert sub.status == SubscriptionStatus.CANCELED


@pytest.mark.asyncio
async def test_cancel_returns_none_when_no_active(
    service: SubscriptionService,
    session: AsyncSession,
) -> None:
    await _seed_user(session, 401)
    assert await service.cancel(401) is None


# ---------------------------------------------------------------------------
# invoice payload + handle_successful_payment
# ---------------------------------------------------------------------------


def test_invoice_payload_roundtrip(service: SubscriptionService) -> None:
    payload = service.new_invoice_payload(user_id=555, offer_code="premium_1m")
    parsed = SubscriptionService.parse_invoice_payload(payload)
    assert parsed is not None
    user_id, offer_code, nonce = parsed
    assert user_id == 555
    assert offer_code == "premium_1m"
    assert len(nonce) > 0


def test_invoice_payload_parse_bad() -> None:
    assert SubscriptionService.parse_invoice_payload("not-a-payload") is None
    assert SubscriptionService.parse_invoice_payload("abc:def:xyz") is None


@pytest.mark.asyncio
async def test_handle_successful_payment_activates_subscription(
    service: SubscriptionService,
    session: AsyncSession,
) -> None:
    await _seed_user(session, 700)
    offer = service.get_offer("premium_1m")
    assert offer is not None
    payload = service.new_invoice_payload(user_id=700, offer_code=offer.code)
    await service.create_pending_payment(
        user_id=700, offer=offer, invoice_payload=payload
    )

    result = await service.handle_successful_payment(
        user_id=700,
        invoice_payload=payload,
        provider_payment_id="charge_abc",
        amount=offer.price_stars,
        currency="XTR",
    )
    assert result is not None
    sub, payment = result
    assert sub.plan == SubscriptionPlan.PREMIUM
    assert sub.status == SubscriptionStatus.ACTIVE
    assert payment.status == PaymentStatus.PAID
    assert payment.provider_payment_id == "charge_abc"


@pytest.mark.asyncio
async def test_handle_successful_payment_is_idempotent(
    service: SubscriptionService,
    session: AsyncSession,
) -> None:
    await _seed_user(session, 701)
    offer = service.get_offer("premium_1m")
    assert offer is not None
    payload = service.new_invoice_payload(user_id=701, offer_code=offer.code)
    await service.create_pending_payment(
        user_id=701, offer=offer, invoice_payload=payload
    )

    first = await service.handle_successful_payment(
        user_id=701,
        invoice_payload=payload,
        provider_payment_id="charge_x",
        amount=offer.price_stars,
        currency="XTR",
    )
    second = await service.handle_successful_payment(
        user_id=701,
        invoice_payload=payload,
        provider_payment_id="charge_x",
        amount=offer.price_stars,
        currency="XTR",
    )
    assert first is not None and second is not None
    # Подписка не должна продлеваться повторно.
    assert first[0].id == second[0].id
    assert first[0].expires_at == second[0].expires_at


@pytest.mark.asyncio
async def test_handle_successful_payment_without_pending_row(
    service: SubscriptionService,
    session: AsyncSession,
) -> None:
    await _seed_user(session, 702)
    result = await service.handle_successful_payment(
        user_id=702,
        invoice_payload="nonexistent",
        provider_payment_id="charge_y",
        amount=199,
        currency="XTR",
    )
    assert result is None


# ---------------------------------------------------------------------------
# Referrals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_referrer_records_relation(
    service: SubscriptionService,
    session: AsyncSession,
) -> None:
    await _seed_user(session, 900)
    await _seed_user(session, 901)
    ok = await service.attach_referrer(referrer_user_id=900, referred_user_id=901)
    assert ok is True
    # Повторно — UNIQUE сработает, attach вернёт False.
    again = await service.attach_referrer(referrer_user_id=900, referred_user_id=901)
    assert again is False


@pytest.mark.asyncio
async def test_attach_referrer_rejects_self_invite(
    service: SubscriptionService,
    session: AsyncSession,
) -> None:
    await _seed_user(session, 902)
    ok = await service.attach_referrer(referrer_user_id=902, referred_user_id=902)
    assert ok is False


@pytest.mark.asyncio
async def test_grant_referral_reward_extends_both_users(
    service: SubscriptionService,
    session: AsyncSession,
) -> None:
    await _seed_user(session, 1000)
    await _seed_user(session, 1001)
    await service.attach_referrer(referrer_user_id=1000, referred_user_id=1001)

    granted = await service.grant_referral_reward(referred_user_id=1001)
    assert granted is True

    s_referrer = await service.get_status(1000)
    s_referred = await service.get_status(1001)
    assert s_referrer.is_premium is True
    assert s_referred.is_premium is True

    # Идемпотентность: повторный вызов не выдаёт ещё.
    again = await service.grant_referral_reward(referred_user_id=1001)
    assert again is False


# ---------------------------------------------------------------------------
# grant_manual / revoke
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grant_manual_creates_premium(
    service: SubscriptionService,
    session: AsyncSession,
) -> None:
    await _seed_user(session, 1100)
    sub = await service.grant_manual(user_id=1100, days=7)
    assert sub.plan == SubscriptionPlan.PREMIUM
    assert sub.payment_provider == PaymentProvider.MANUAL.value
    status = await service.get_status(1100)
    assert status.is_premium is True


@pytest.mark.asyncio
async def test_revoke_returns_false_when_no_subscription(
    service: SubscriptionService,
    session: AsyncSession,
) -> None:
    await _seed_user(session, 1101)
    assert await service.revoke(1101) is False


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


def _free_status() -> SubscriptionStatusInfo:
    return SubscriptionStatusInfo(
        user_id=1,
        plan=SubscriptionPlan.FREE,
        status=SubscriptionStatus.ACTIVE,
        expires_at=None,
        in_grace_period=False,
    )


def _premium_status() -> SubscriptionStatusInfo:
    return SubscriptionStatusInfo(
        user_id=1,
        plan=SubscriptionPlan.PREMIUM,
        status=SubscriptionStatus.ACTIVE,
        expires_at=datetime.now(tz=UTC) + timedelta(days=30),
        in_grace_period=False,
    )


def _vip_status() -> SubscriptionStatusInfo:
    return SubscriptionStatusInfo(
        user_id=1,
        plan=SubscriptionPlan.VIP,
        status=SubscriptionStatus.ACTIVE,
        expires_at=datetime.now(tz=UTC) + timedelta(days=30),
        in_grace_period=False,
    )


@pytest.mark.asyncio
async def test_premium_filter_passes_premium_and_vip() -> None:
    pf = PremiumFilter()
    event = MagicMock()
    assert await pf(event, subscription=_premium_status()) is True
    assert await pf(event, subscription=_vip_status()) is True


@pytest.mark.asyncio
async def test_premium_filter_blocks_free() -> None:
    pf = PremiumFilter()
    event = MagicMock()
    assert await pf(event, subscription=_free_status()) is False
    # без subscription в data — тоже не пускаем.
    assert await pf(event) is False


@pytest.mark.asyncio
async def test_vip_filter_passes_only_vip_and_lifetime() -> None:
    vf = VipFilter()
    event = MagicMock()
    assert await vf(event, subscription=_vip_status()) is True
    assert await vf(event, subscription=_premium_status()) is False
    assert await vf(event, subscription=_free_status()) is False


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------


def test_build_offers_keyboard_has_button_per_offer() -> None:
    settings = _make_settings()
    catalog = build_plan_catalog(settings)
    offers = list(catalog.values())
    kb = build_offers_keyboard(offers)
    flat = [btn for row in kb.inline_keyboard for btn in row]
    assert len(flat) == len(offers)
    assert all(btn.callback_data is not None for btn in flat)
    assert all(btn.callback_data.startswith(CB_UPGRADE_PREFIX) for btn in flat)


def test_build_subscription_status_keyboard_for_free_shows_renew_only() -> None:
    kb = build_subscription_status_keyboard(is_premium=False, has_active=False)
    flat = [btn for row in kb.inline_keyboard for btn in row]
    assert len(flat) == 1
    assert flat[0].callback_data == CB_RENEW


def test_build_subscription_status_keyboard_for_premium_shows_renew_and_cancel() -> None:
    kb = build_subscription_status_keyboard(is_premium=True, has_active=True)
    cb_values = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert CB_RENEW in cb_values
    assert CB_CANCEL in cb_values


# ---------------------------------------------------------------------------
# SubscriptionMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscription_middleware_skips_without_session() -> None:
    mw = SubscriptionMiddleware(_make_settings())
    handler = AsyncMock(return_value="ok")
    data: dict = {}
    result = await mw(handler, MagicMock(), data)
    assert result == "ok"
    assert "subscription_service" not in data
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_subscription_middleware_injects_status_and_service(
    session: AsyncSession,
) -> None:
    await _seed_user(session, 55)
    mw = SubscriptionMiddleware(_make_settings())
    captured: dict = {}

    async def handler(event, data) -> str:
        captured.update(data)
        return "ok"

    user = MagicMock(id=55)
    data = {"session": session, "event_from_user": user}
    result = await mw(handler, MagicMock(), data)

    assert result == "ok"
    assert isinstance(captured["subscription_service"], SubscriptionService)
    assert isinstance(captured["subscription"], SubscriptionStatusInfo)
    assert captured["subscription"].plan == SubscriptionPlan.FREE


# ---------------------------------------------------------------------------
# AIRequestThrottle per-tier
# ---------------------------------------------------------------------------


class _FakeRedis:
    """Минимальный Redis-стаб с pipeline().execute(): просто хранит ZSET в памяти."""

    def __init__(self) -> None:
        self._zsets: dict[str, dict[str, float]] = {}
        self._queue: list = []

    def pipeline(self) -> _FakeRedis:
        self._queue = []
        return self

    def zremrangebyscore(self, key, min_score, max_score) -> None:
        zset = self._zsets.get(key, {})
        for member, score in list(zset.items()):
            if min_score <= score <= max_score:
                zset.pop(member, None)
        self._queue.append(("zrem", None))

    def zrange(self, key, start, stop, *, withscores=False) -> None:
        zset = self._zsets.get(key, {})
        items = sorted(zset.items(), key=lambda kv: kv[1])
        sliced = items[start:] if stop == -1 else items[start:stop + 1]
        self._queue.append(("zrange", sliced if withscores else [m for m, _ in sliced]))

    def zcard(self, key) -> None:
        self._queue.append(("zcard", len(self._zsets.get(key, {}))))

    def zadd(self, key, mapping) -> None:
        self._zsets.setdefault(key, {}).update(mapping)
        self._queue.append(("zadd", None))

    def expire(self, key, ttl) -> None:
        self._queue.append(("expire", None))

    async def execute(self) -> list:
        results = [v for _, v in self._queue]
        self._queue = []
        return results


def _fake_message(text: str, user_id: int = 1) -> MagicMock:
    msg = MagicMock()
    msg.text = text
    msg.data = None
    msg.from_user = MagicMock(id=user_id)
    msg.answer = AsyncMock()
    return msg


@pytest.mark.asyncio
async def test_ai_throttle_free_tier_blocks_after_limit() -> None:
    throttle = AIRequestThrottle(
        _FakeRedis(), max_per_minute=2, min_interval_seconds=0
    )
    handler = AsyncMock(return_value="ok")
    msg = _fake_message("/forecast")
    # 2 разрешённых вызова.
    await throttle(handler, msg, {})
    await throttle(handler, msg, {})
    # 3-й должен быть заблокирован для Free.
    result = await throttle(handler, msg, {})
    assert result is None
    assert handler.await_count == 2


@pytest.mark.asyncio
async def test_ai_throttle_premium_gets_higher_limit() -> None:
    throttle = AIRequestThrottle(
        _FakeRedis(),
        max_per_minute=2,
        min_interval_seconds=0,
        max_per_minute_premium=10,
        min_interval_seconds_premium=0,
    )
    handler = AsyncMock(return_value="ok")
    msg = _fake_message("/forecast")
    data = {"subscription": _premium_status()}
    # Премиум проходит 5 запросов без проблем (лимит 10).
    for _ in range(5):
        result = await throttle(handler, msg, data)
        assert result == "ok"
    assert handler.await_count == 5


@pytest.mark.asyncio
async def test_ai_throttle_ignores_non_ai_calls() -> None:
    throttle = AIRequestThrottle(
        _FakeRedis(), max_per_minute=1, min_interval_seconds=0
    )
    handler = AsyncMock(return_value="ok")
    msg = _fake_message("/profile")  # не AI-команда
    for _ in range(5):
        result = await throttle(handler, msg, {})
        assert result == "ok"
    assert handler.await_count == 5


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cmd_upgrade_sends_offers() -> None:
    service = MagicMock(spec=SubscriptionService)
    settings = _make_settings()
    service.catalog = build_plan_catalog(settings)
    message = MagicMock()
    message.answer = AsyncMock()

    await cmd_upgrade(message=message, subscription_service=service)
    message.answer.assert_awaited_once()
    args, kwargs = message.answer.call_args
    assert "Premium" in args[0]
    assert kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_cmd_subscription_shows_status_text() -> None:
    service = MagicMock(spec=SubscriptionService)
    settings = _make_settings()
    service.catalog = build_plan_catalog(settings)
    service.get_status = AsyncMock(return_value=_free_status())

    message = MagicMock()
    message.answer = AsyncMock()
    message.from_user = MagicMock(id=1)

    await cmd_subscription(
        message=message,
        subscription_service=service,
        settings=settings,
        subscription=None,
    )
    message.answer.assert_awaited_once()
    text = message.answer.call_args.args[0]
    assert "подписка" in text.lower()
    assert "free" in text.lower()


@pytest.mark.asyncio
async def test_cb_buy_calls_send_invoice() -> None:
    service = MagicMock(spec=SubscriptionService)
    service.catalog = build_plan_catalog(_make_settings())
    service.get_offer = MagicMock(return_value=service.catalog["premium_1m"])
    service.new_invoice_payload = MagicMock(return_value="payload-xyz")
    service.create_pending_payment = AsyncMock()

    bot = MagicMock()
    bot.send_invoice = AsyncMock()

    cb = MagicMock()
    cb.from_user = MagicMock(id=42)
    cb.data = f"{CB_UPGRADE_PREFIX}premium_1m"
    cb.message = MagicMock()
    cb.message.chat = MagicMock(id=42)
    cb.bot = bot
    cb.answer = AsyncMock()

    await cb_buy(callback=cb, subscription_service=service)

    bot.send_invoice.assert_awaited_once()
    kwargs = bot.send_invoice.call_args.kwargs
    assert kwargs["currency"] == "XTR"
    assert kwargs["payload"] == "payload-xyz"
    service.create_pending_payment.assert_awaited_once()


@pytest.mark.asyncio
async def test_cb_buy_unknown_offer_alerts() -> None:
    service = MagicMock(spec=SubscriptionService)
    service.catalog = build_plan_catalog(_make_settings())
    service.get_offer = MagicMock(return_value=None)

    cb = MagicMock()
    cb.from_user = MagicMock(id=42)
    cb.data = f"{CB_UPGRADE_PREFIX}does_not_exist"
    cb.answer = AsyncMock()

    await cb_buy(callback=cb, subscription_service=service)
    cb.answer.assert_awaited_once()
    assert cb.answer.call_args.kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_on_pre_checkout_validates_payload_and_price() -> None:
    settings = _make_settings()
    catalog = build_plan_catalog(settings)
    offer = catalog["premium_1m"]

    service = MagicMock(spec=SubscriptionService)
    service.parse_invoice_payload = SubscriptionService.parse_invoice_payload
    service.get_offer = MagicMock(return_value=offer)

    query = MagicMock()
    query.from_user = MagicMock(id=42)
    query.invoice_payload = f"42:{offer.code}:abcdef"
    query.total_amount = offer.price_stars
    query.currency = "XTR"
    query.answer = AsyncMock()

    await on_pre_checkout(query=query, subscription_service=service)
    query.answer.assert_awaited_once_with(ok=True)


@pytest.mark.asyncio
async def test_on_pre_checkout_rejects_user_mismatch() -> None:
    settings = _make_settings()
    catalog = build_plan_catalog(settings)
    offer = catalog["premium_1m"]
    service = MagicMock(spec=SubscriptionService)
    service.parse_invoice_payload = SubscriptionService.parse_invoice_payload
    service.get_offer = MagicMock(return_value=offer)

    query = MagicMock()
    query.from_user = MagicMock(id=42)
    # user_id в payload = 7, а запрос от 42 — должен отлуп.
    query.invoice_payload = f"7:{offer.code}:abcdef"
    query.total_amount = offer.price_stars
    query.currency = "XTR"
    query.answer = AsyncMock()

    await on_pre_checkout(query=query, subscription_service=service)
    query.answer.assert_awaited_once()
    assert query.answer.call_args.kwargs.get("ok") is False


@pytest.mark.asyncio
async def test_on_pre_checkout_rejects_bad_currency() -> None:
    settings = _make_settings()
    catalog = build_plan_catalog(settings)
    offer = catalog["premium_1m"]
    service = MagicMock(spec=SubscriptionService)
    service.parse_invoice_payload = SubscriptionService.parse_invoice_payload
    service.get_offer = MagicMock(return_value=offer)

    query = MagicMock()
    query.from_user = MagicMock(id=42)
    query.invoice_payload = f"42:{offer.code}:abcdef"
    query.total_amount = offer.price_stars
    query.currency = "USD"
    query.answer = AsyncMock()

    await on_pre_checkout(query=query, subscription_service=service)
    assert query.answer.call_args.kwargs.get("ok") is False


@pytest.mark.asyncio
async def test_on_successful_payment_activates_and_replies(
    service: SubscriptionService,
    session: AsyncSession,
) -> None:
    await _seed_user(session, 555)
    offer = service.get_offer("premium_1m")
    assert offer is not None
    payload = service.new_invoice_payload(user_id=555, offer_code=offer.code)
    await service.create_pending_payment(
        user_id=555, offer=offer, invoice_payload=payload
    )

    message = MagicMock()
    message.from_user = MagicMock(id=555)
    message.successful_payment = MagicMock()
    message.successful_payment.invoice_payload = payload
    message.successful_payment.telegram_payment_charge_id = "charge_xyz"
    message.successful_payment.total_amount = offer.price_stars
    message.successful_payment.currency = "XTR"
    message.answer = AsyncMock()

    await on_successful_payment(message=message, subscription_service=service)

    message.answer.assert_awaited_once()
    text = message.answer.call_args.args[0]
    assert "Подписка активна" in text or "активна" in text.lower()

    status = await service.get_status(555)
    assert status.is_premium is True


@pytest.mark.asyncio
async def test_cb_cancel_with_no_active_subscription_alerts() -> None:
    service = MagicMock(spec=SubscriptionService)
    service.cancel = AsyncMock(return_value=None)

    cb = MagicMock()
    cb.from_user = MagicMock(id=42)
    cb.answer = AsyncMock()

    await cb_cancel(callback=cb, subscription_service=service)
    cb.answer.assert_awaited_once()
    assert cb.answer.call_args.kwargs.get("show_alert") is True
