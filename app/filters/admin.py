"""Фильтр «только админ»: пропускает событие, только если автор события
есть в `Settings.admin_ids`.

Используется и как `Message.filter(AdminFilter())`, и как фильтр на уровне
роутера (`router.message.filter(...)`), чтобы закрыть весь admin-роутер
одним вызовом.
"""

from __future__ import annotations

from collections.abc import Iterable

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message, TelegramObject


def _extract_user_id(event: TelegramObject) -> int | None:
    if isinstance(event, Message):
        return event.from_user.id if event.from_user else None
    if isinstance(event, CallbackQuery):
        return event.from_user.id if event.from_user else None
    return None


class AdminFilter(Filter):
    """Истина, если `event.from_user.id` — известный админ."""

    def __init__(self, admin_ids: Iterable[int] | None = None) -> None:
        # Если `admin_ids` не передали — берём из Settings во время вызова,
        # чтобы можно было менять список без пересборки фильтра.
        self._explicit_admin_ids: tuple[int, ...] | None = (
            tuple(admin_ids) if admin_ids is not None else None
        )

    async def __call__(self, event: TelegramObject) -> bool:
        user_id = _extract_user_id(event)
        if user_id is None:
            return False
        admin_ids = self._explicit_admin_ids
        if admin_ids is None:
            # Импортируем лениво — Settings зависит от env, а фильтр
            # инициализируется на старте, ещё до полной готовности окружения.
            from app.config.settings import get_settings

            admin_ids = tuple(get_settings().admin_ids)
        return user_id in admin_ids


__all__ = ["AdminFilter"]
