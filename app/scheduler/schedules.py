"""Cron-расписание для автопостинга в канал.

Времена интерпретируются в `Settings.timezone` (по умолчанию Europe/Moscow).
Если нужно «отключить» какой-то тип — убирать его из словаря, а не выставлять
расписание в прошлое.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import PostKind


@dataclass(frozen=True, slots=True)
class CronSpec:
    """Cron-выражение в формате APScheduler (`CronTrigger`)."""

    hour: int
    minute: int
    day_of_week: str = "*"  # `mon,tue,...` или `*`

    def as_dict(self) -> dict[str, int | str]:
        """Передать в `AsyncIOScheduler.add_job(..., trigger="cron", **spec)`."""
        return {
            "hour": self.hour,
            "minute": self.minute,
            "day_of_week": self.day_of_week,
        }


#: Базовое расписание авто-постов. Подобраны разные слоты дня, чтобы
#: посты не толпились в одну минуту.
DEFAULT_SCHEDULE: dict[PostKind, CronSpec] = {
    PostKind.DAY_FORECAST: CronSpec(hour=9, minute=0),
    PostKind.DAY_NUMBER: CronSpec(hour=10, minute=30),
    PostKind.DAY_ENERGY: CronSpec(hour=14, minute=0),
    PostKind.MYSTICAL_WARNING: CronSpec(hour=18, minute=30),
    PostKind.VIRAL: CronSpec(hour=21, minute=0, day_of_week="fri,sat"),
}


__all__ = ["DEFAULT_SCHEDULE", "CronSpec"]
