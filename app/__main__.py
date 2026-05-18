"""Entrypoint: запуск Telegram-бота через long-polling.

Порядок:
1. Подгружаем Settings и настраиваем logging.
2. Создаём Bot/Dispatcher/Redis.
3. Регистрируем middlewares в правильном порядке (logging → throttling →
   db_session → user_upsert) на уровне `dp.update.middleware()`.
4. Подключаем главный роутер.
5. Регистрируем on_startup/on_shutdown.
6. Уходим в `start_polling`.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.bot import build_bot, build_dispatcher, build_redis, set_bot_commands
from app.config.settings import get_settings
from app.database.session import dispose_engine, get_sessionmaker
from app.handlers import build_main_router
from app.middlewares import (
    AIServiceMiddleware,
    DbSessionMiddleware,
    LoggingMiddleware,
    ThrottlingMiddleware,
    UserUpsertMiddleware,
)
from app.services.ai.client import OpenAIClient
from app.services.ai.service import AIService
from app.utils.logging import setup_logging

logger = logging.getLogger(__name__)


def register_middlewares(
    dp: Dispatcher,
    *,
    redis,
    settings,
    ai_service: AIService,
) -> None:
    """Зарегистрировать middlewares в правильном порядке."""
    sessionmaker = get_sessionmaker()
    dp.update.middleware(LoggingMiddleware())
    dp.update.middleware(
        ThrottlingMiddleware(
            redis,
            default_rate=settings.throttle_default_rate,
            max_per_minute=settings.rate_limit_messages_per_minute,
        )
    )
    dp.update.middleware(DbSessionMiddleware(sessionmaker))
    dp.update.middleware(UserUpsertMiddleware())
    # AIServiceMiddleware подключаем последним — на момент его выполнения уже
    # есть user/session в data, и хендлеры спокойно получают `ai_service` kwarg.
    dp.update.middleware(AIServiceMiddleware(ai_service))


async def on_startup(bot: Bot) -> None:
    await set_bot_commands(bot)
    me = await bot.get_me()
    logger.info("bot started as @%s (id=%s)", me.username, me.id)


async def on_shutdown(bot: Bot) -> None:
    logger.info("bot shutting down…")
    await dispose_engine()
    await bot.session.close()


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("astro-bot starting env=%s tz=%s", settings.env, settings.timezone)

    bot = build_bot(settings)
    redis = build_redis(settings)
    dp = build_dispatcher(redis)

    openai_client = OpenAIClient(settings)
    ai_service = AIService(openai_client)

    register_middlewares(dp, redis=redis, settings=settings, ai_service=ai_service)
    dp.include_router(build_main_router())

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    try:
        await dp.start_polling(bot)
    finally:
        await openai_client.aclose()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
