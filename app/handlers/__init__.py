"""aiogram routers.

`build_main_router()` собирает все пользовательские роутеры в одно дерево —
именно его и подключают к `Dispatcher`. Admin-роутер подключается отдельно
через `build_admin_router()` и имеет собственные middlewares.
"""

from aiogram import Router

from app.handlers import (
    admin,
    common,
    compatibility,
    errors,
    forecast,
    numerology,
    profile,
    tarot,
)


def build_main_router() -> Router:
    root = Router(name="main")
    # `errors` подключаем первым — ErrorEvent ловится на любом уровне.
    root.include_router(errors.router)
    # Admin-роутер раньше фичей: его фильтр `AdminFilter` пропускает только
    # известных админов, остальные провалятся в публичные хендлеры.
    root.include_router(admin.router)
    # Фича-хендлеры подключаем раньше `common`, чтобы кнопки главного меню
    # подхватывались ими, а не fallback'ом «coming soon».
    root.include_router(forecast.router)
    root.include_router(numerology.router)
    root.include_router(compatibility.router)
    root.include_router(tarot.router)
    root.include_router(common.router)
    root.include_router(profile.router)
    return root


__all__ = ["build_main_router"]
