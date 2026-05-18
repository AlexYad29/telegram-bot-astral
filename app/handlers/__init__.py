"""aiogram routers.

`build_main_router()` собирает все пользовательские роутеры в одно дерево —
именно его и подключают к `Dispatcher`. Admin-роутеры (ЭТАП 10) подключатся
отдельно, чтобы не смешивать публичный и админский трафик.
"""

from aiogram import Router

from app.handlers import common, errors, forecast, profile


def build_main_router() -> Router:
    root = Router(name="main")
    # `errors` подключаем первым — ErrorEvent ловится на любом уровне.
    root.include_router(errors.router)
    # `forecast` — раньше `common`, чтобы кнопка «Прогноз» подхватывалась
    # AI-хендлером, а не fallback'ом «coming soon».
    root.include_router(forecast.router)
    root.include_router(common.router)
    root.include_router(profile.router)
    return root


__all__ = ["build_main_router"]
