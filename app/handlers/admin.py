"""Админ-команды: статистика, ручной автопост, управление планировщиком.

Роутер закрыт `AdminFilter` на уровне `message`/`callback_query` — обычные
пользователи никогда не увидят эти команды и не смогут их вызвать.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.filters import AdminFilter
from app.models.enums import PostKind, SubscriptionPlan
from app.repositories.payment import PaymentRepository
from app.repositories.referral import ReferralRepository
from app.repositories.subscription import SubscriptionRepository
from app.scheduler import run_channel_post_job
from app.scheduler.jobs import _day_number_for
from app.services.admin_stats import AdminStatsService, format_admin_stats
from app.services.ai.service import AIService
from app.services.ai.tokens import from_micro_cents
from app.services.ai.usage import UsageReport, UsageTracker
from app.services.subscription import SubscriptionService

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from app.config.settings import Settings

logger = logging.getLogger(__name__)


router = Router(name="admin")
router.message.filter(AdminFilter())


# ---------- Описание PostKind для CLI ----------
_KIND_BY_ALIAS: dict[str, PostKind] = {
    "forecast": PostKind.DAY_FORECAST,
    "day_forecast": PostKind.DAY_FORECAST,
    "number": PostKind.DAY_NUMBER,
    "day_number": PostKind.DAY_NUMBER,
    "energy": PostKind.DAY_ENERGY,
    "day_energy": PostKind.DAY_ENERGY,
    "warning": PostKind.MYSTICAL_WARNING,
    "mystical_warning": PostKind.MYSTICAL_WARNING,
    "viral": PostKind.VIRAL,
}


def _kind_aliases_help() -> str:
    seen: set[PostKind] = set()
    parts: list[str] = []
    for alias, kind in _KIND_BY_ALIAS.items():
        if kind in seen:
            continue
        seen.add(kind)
        parts.append(f"• <code>{alias}</code> → {kind.value}")
    return "\n".join(parts)


# ---------- /admin ----------
@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    """Главное меню админ-команд (просто help-текст)."""
    text = (
        "<b>🛠 Админ-панель</b>\n\n"
        "Доступные команды:\n"
        "• /stats — статистика пользователей и автопостов\n"
        "• /admin_usage — OpenAI usage и стоимость за 24h/7d/30d\n"
        "• /post_now &lt;kind&gt; — вручную создать и отправить пост в канал\n"
        "• /scheduler — состояние планировщика и список job'ов\n"
        "• /scheduler_pause — поставить все job'ы на паузу\n"
        "• /scheduler_resume — снять паузу\n"
        "\n<b>Виды постов для /post_now</b>:\n"
        f"{_kind_aliases_help()}"
    )
    await message.answer(text)


# ---------- /admin_usage ----------
def _format_usage_report(report: UsageReport) -> str:
    agg = report.aggregate
    cache_pct = (
        100.0 * agg.cache_hits / agg.requests if agg.requests else 0.0
    )
    cost_usd = from_micro_cents(agg.cost_micro_cents)
    lines = [
        f"<b>• Период:</b> последние <code>{report.label}</code>",
        f"  вызовов: <code>{agg.requests}</code> "
        f"(cache hits <code>{agg.cache_hits}</code>, {cache_pct:.0f}%)",
        f"  prompt/compl/total: <code>{agg.prompt_tokens}</code> / "
        f"<code>{agg.completion_tokens}</code> / <code>{agg.total_tokens}</code>",
        f"  стоимость: <b>${cost_usd:.4f}</b>",
    ]
    if report.by_task:
        lines.append("  биллинг по задачам (топ-3 по total_tokens):")
        top = sorted(
            report.by_task, key=lambda r: r.total_tokens, reverse=True
        )[:3]
        for row in top:
            row_cost = from_micro_cents(row.cost_micro_cents)
            lines.append(
                f"    — <code>{row.task}</code>: "
                f"req <code>{row.requests}</code>, "
                f"tokens <code>{row.total_tokens}</code>, "
                f"$<code>{row_cost:.4f}</code>"
            )
    return "\n".join(lines)


@router.message(Command("admin_usage"))
async def cmd_admin_usage(
    message: Message,
    usage_tracker: UsageTracker,
) -> None:
    """OpenAI usage за 24h/7d/30d — токены, cost, cache-hit rate."""
    try:
        reports = await usage_tracker.reports_overview()
    except Exception as exc:
        logger.exception("admin_usage failed")
        await message.answer(
            f"❌ Не получилось собрать usage: "
            f"<code>{type(exc).__name__}</code> — {exc}"
        )
        return
    blocks = [_format_usage_report(r) for r in reports]
    text = "<b>📊 OpenAI usage</b>\n\n" + "\n\n".join(blocks)
    await message.answer(text)


# ---------- /stats ----------
@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession) -> None:
    service = AdminStatsService(session)
    stats = await service.collect()
    await message.answer(format_admin_stats(stats))


# ---------- /post_now <kind> ----------
@router.message(Command("post_now"))
async def cmd_post_now(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ai_service: AIService,
    bot: Bot,
    settings: Settings,
) -> None:
    """Сгенерировать и отправить пост вручную (без ожидания cron)."""
    if not command.args:
        await message.answer(
            "Использование: <code>/post_now &lt;kind&gt;</code>\n\n"
            f"{_kind_aliases_help()}"
        )
        return
    alias = command.args.strip().split()[0].lower()
    kind = _KIND_BY_ALIAS.get(alias)
    if kind is None:
        await message.answer(
            f"Неизвестный тип поста: <code>{alias}</code>.\n\n{_kind_aliases_help()}"
        )
        return
    if not settings.channel_id:
        await message.answer(
            "❌ `CHANNEL_ID` не настроен — пост отправлять некуда."
        )
        return

    await message.answer(f"⏳ Готовлю пост: <b>{kind.value}</b>…")
    try:
        # Используем ту же job-функцию, что и планировщик, — она сама
        # пишет в БД и шлёт в канал. Сессионмейкер собираем «на лету»,
        # чтобы внутри job была отдельная транзакция.
        from app.database.session import get_sessionmaker

        sessionmaker = get_sessionmaker()
        await run_channel_post_job(
            kind=kind,
            sessionmaker=sessionmaker,
            ai_service=ai_service,
            bot=bot,
            channel_id=settings.channel_id,
            today=date.today(),
        )
    except Exception as exc:
        logger.exception("admin post_now failed kind=%s", kind)
        await message.answer(f"❌ Не получилось: <code>{type(exc).__name__}</code> — {exc}")
        return
    await message.answer("✅ Готово. Пост отправлен и записан в `generated_posts`.")


# ---------- /scheduler ----------
@router.message(Command("scheduler"))
async def cmd_scheduler(message: Message, scheduler: AsyncIOScheduler) -> None:
    """Состояние и список job'ов планировщика."""
    if not scheduler.running:
        await message.answer("⏸ Планировщик остановлен. /scheduler_resume чтобы запустить.")
        return
    jobs = scheduler.get_jobs()
    if not jobs:
        await message.answer("✅ Планировщик запущен, но job'ов нет.")
        return
    lines = ["<b>⏰ Планировщик запущен</b>", ""]
    for job in jobs:
        nxt = job.next_run_time
        when = nxt.strftime("%Y-%m-%d %H:%M %Z") if nxt else "—"
        lines.append(f"• <code>{job.id}</code> → следующий запуск: <i>{when}</i>")
    await message.answer("\n".join(lines))


# ---------- /scheduler_pause ----------
@router.message(Command("scheduler_pause"))
async def cmd_scheduler_pause(
    message: Message, scheduler: AsyncIOScheduler
) -> None:
    if not scheduler.running:
        await message.answer("Планировщик и так не запущен.")
        return
    scheduler.pause()
    logger.info("admin %s paused scheduler", message.from_user.id if message.from_user else "?")
    await message.answer("⏸ Планировщик поставлен на паузу. /scheduler_resume чтобы снять.")


# ---------- /scheduler_resume ----------
@router.message(Command("scheduler_resume"))
async def cmd_scheduler_resume(
    message: Message, scheduler: AsyncIOScheduler
) -> None:
    if not scheduler.running:
        scheduler.start()
    else:
        scheduler.resume()
    logger.info("admin %s resumed scheduler", message.from_user.id if message.from_user else "?")
    await message.answer("▶️ Планировщик снова работает.")


# ---------- /grant_premium <user_id> <days> ----------
@router.message(Command("grant_premium"))
async def cmd_grant_premium(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Admin: выдать Premium пользователю."""
    if not command.args:
        await message.answer(
            "Использование: <code>/grant_premium &lt;user_id&gt; &lt;days&gt;</code>"
        )
        return
    parts = command.args.strip().split()
    if len(parts) < 2:
        await message.answer("Нужно два аргумента: <code>/grant_premium &lt;user_id&gt; &lt;days&gt;</code>")
        return
    try:
        target_user_id = int(parts[0])
        days = int(parts[1])
    except ValueError:
        await message.answer("❓ user_id и days должны быть целыми числами.")
        return
    if days <= 0 or days > 3650:
        await message.answer("❓ days должен быть от 1 до 3650.")
        return

    svc = SubscriptionService(
        settings=settings,
        subscription_repo=SubscriptionRepository(session),
        payment_repo=PaymentRepository(session),
        referral_repo=ReferralRepository(session),
    )
    sub = await svc.grant_manual(user_id=target_user_id, days=days)
    logger.info(
        "admin %s granted premium %dd to user %s",
        message.from_user.id if message.from_user else "?",
        days,
        target_user_id,
    )
    expires = sub.expires_at.strftime("%Y-%m-%d") if sub.expires_at else "бессрочно"
    await message.answer(
        f"✅ Premium выдан пользователю <code>{target_user_id}</code> "
        f"на <b>{days}</b> дней (до {expires})."
    )


# ---------- /revoke_premium <user_id> ----------
@router.message(Command("revoke_premium"))
async def cmd_revoke_premium(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if not command.args:
        await message.answer(
            "Использование: <code>/revoke_premium &lt;user_id&gt;</code>"
        )
        return
    try:
        target_user_id = int(command.args.strip().split()[0])
    except ValueError:
        await message.answer("❓ user_id должен быть числом.")
        return

    svc = SubscriptionService(
        settings=settings,
        subscription_repo=SubscriptionRepository(session),
        payment_repo=PaymentRepository(session),
        referral_repo=ReferralRepository(session),
    )
    ok = await svc.revoke(target_user_id)
    if ok:
        logger.info(
            "admin %s revoked premium from user %s",
            message.from_user.id if message.from_user else "?",
            target_user_id,
        )
        await message.answer(
            f"❌ Подписка пользователя <code>{target_user_id}</code> отменена."
        )
    else:
        await message.answer(
            f"❓ У пользователя <code>{target_user_id}</code> нет активной подписки."
        )


# ---------- /subscriptions_stats ----------
@router.message(Command("subscriptions_stats"))
async def cmd_subscriptions_stats(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    sub_repo = SubscriptionRepository(session)
    pay_repo = PaymentRepository(session)
    ref_repo = ReferralRepository(session)

    active = await sub_repo.count_active()
    by_plan: dict[str, int] = {}
    for plan in (SubscriptionPlan.PREMIUM, SubscriptionPlan.VIP, SubscriptionPlan.LIFETIME):
        cnt = await sub_repo.count_active_by_plan(plan)
        if cnt:
            by_plan[plan.value] = cnt
    paid_count = await pay_repo.count_paid()
    paid_7d = await pay_repo.count_paid_last_days(7)
    revenue = await pay_repo.aggregate_revenue()
    total_refs = await ref_repo.total()

    lines = [
        "<b>⭐ Статистика подписок</b>",
        "",
        f"Активных подписок: <b>{active}</b>",
    ]
    for plan_name, cnt in by_plan.items():
        lines.append(f"  • {plan_name}: {cnt}")
    lines.append(f"\nОплат всего: <b>{paid_count}</b> (за 7д: {paid_7d})")
    if revenue:
        for currency, total in revenue.items():
            lines.append(f"  • {currency}: <code>{total}</code>")
    lines.append(f"\nРефералов: <b>{total_refs}</b>")
    await message.answer("\n".join(lines))


# ---------- Утилиты, экспортируемые для тестов ----------
def _today_utc() -> date:
    return datetime.now(tz=UTC).date()


def _resolve_day_number(today: date) -> int:
    return _day_number_for(today)


__all__ = ["router"]
