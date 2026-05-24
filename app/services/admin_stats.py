"""Сервис админ-статистики.

Тянет агрегаты из репозиториев и собирает в `AdminStats` dataclass — удобно
форматировать в текстовое сообщение бота и при необходимости отдавать в API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PostKind, PostStatus
from app.repositories.generated_post import GeneratedPostRepository
from app.repositories.user import UserRepository


@dataclass(frozen=True, slots=True)
class AdminStats:
    """Снимок ключевых метрик бота на момент `as_of`."""

    as_of: datetime
    users_total: int
    users_with_profile: int
    users_active_24h: int
    users_active_7d: int
    users_blocked: int
    posts_by_status: dict[PostStatus, int]
    posts_by_kind_7d: dict[PostKind, int]


class AdminStatsService:
    """Считает срез метрик одной транзакцией."""

    def __init__(self, session: AsyncSession) -> None:
        self._users = UserRepository(session)
        self._posts = GeneratedPostRepository(session)

    async def collect(self) -> AdminStats:
        now = datetime.now(tz=UTC)
        return AdminStats(
            as_of=now,
            users_total=await self._users.count(),
            users_with_profile=await self._users.count_with_profile(),
            users_active_24h=await self._users.count_active_since(now - timedelta(days=1)),
            users_active_7d=await self._users.count_active_since(now - timedelta(days=7)),
            users_blocked=await self._users.count_blocked(),
            posts_by_status=await self._posts.count_by_status(),
            posts_by_kind_7d=await self._posts.count_by_kind_since(
                now - timedelta(days=7)
            ),
        )


_KIND_RU: dict[PostKind, str] = {
    PostKind.DAY_FORECAST: "Прогноз дня",
    PostKind.DAY_NUMBER: "Число дня",
    PostKind.DAY_ENERGY: "Энергия дня",
    PostKind.MYSTICAL_WARNING: "Предупреждение",
    PostKind.VIRAL: "Вирусный пост",
}

_STATUS_RU: dict[PostStatus, str] = {
    PostStatus.SCHEDULED: "запланировано",
    PostStatus.SENT: "отправлено",
    PostStatus.FAILED: "ошибка",
}


def format_admin_stats(stats: AdminStats) -> str:
    """Превратить `AdminStats` в HTML-сообщение Telegram."""
    lines: list[str] = [
        "<b>📊 Статистика бота</b>",
        f"<i>на {stats.as_of.strftime('%Y-%m-%d %H:%M UTC')}</i>",
        "",
        "<b>Пользователи</b>",
        f"• всего: {stats.users_total}",
        f"• с профилем: {stats.users_with_profile}",
        f"• активны 24ч: {stats.users_active_24h}",
        f"• активны 7д: {stats.users_active_7d}",
        f"• заблокировали бота: {stats.users_blocked}",
        "",
        "<b>Авто-посты</b>",
    ]
    if not stats.posts_by_status:
        lines.append("• ещё ни одного")
    else:
        for status in (PostStatus.SCHEDULED, PostStatus.SENT, PostStatus.FAILED):
            count = stats.posts_by_status.get(status, 0)
            lines.append(f"• {_STATUS_RU[status]}: {count}")
    lines.append("")
    lines.append("<b>За 7 дней по типам</b>")
    if not stats.posts_by_kind_7d:
        lines.append("• ничего")
    else:
        for kind in PostKind:
            count = stats.posts_by_kind_7d.get(kind, 0)
            if count:
                lines.append(f"• {_KIND_RU[kind]}: {count}")
    return "\n".join(lines)


__all__ = ["AdminStats", "AdminStatsService", "format_admin_stats"]
