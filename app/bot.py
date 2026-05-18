"""Сборка aiogram-объектов: Bot, Dispatcher, Redis-клиент, FSM-storage.

Здесь только фабрики — без побочных эффектов (никаких `setup_logging`,
никаких `start_polling`). Запуск живёт в `app.__main__`.
"""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand
from redis.asyncio import Redis

from app.config.settings import Settings


def build_bot(settings: Settings) -> Bot:
    """Сконструировать aiogram Bot с HTML parse_mode по умолчанию."""
    return Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def build_redis(settings: Settings) -> Redis:
    """Один Redis-клиент на всё приложение (FSM-storage + throttling).

    `decode_responses=False` — байты для FSM, для throttling нам тоже не нужны
    декодированные строки (мы сравниваем напрямую).
    """
    return Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        decode_responses=False,
    )


def build_dispatcher(redis: Redis) -> Dispatcher:
    """Dispatcher с RedisStorage для FSM."""
    storage = RedisStorage(redis=redis)
    return Dispatcher(storage=storage)


BOT_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="Начать заново и открыть главное меню"),
    BotCommand(command="profile", description="Профиль и дата рождения"),
    BotCommand(command="forecast", description="Прогноз дня"),
    BotCommand(command="numerology", description="Числа судьбы и личности"),
    BotCommand(command="compatibility", description="Совместимость с партнёром"),
    BotCommand(command="tarot", description="Расклад на трёх картах Таро"),
    BotCommand(command="help", description="Список команд"),
]


async def set_bot_commands(bot: Bot) -> None:
    """Выставить команды в меню Telegram (синие подсказки слева от поля ввода)."""
    await bot.set_my_commands(BOT_COMMANDS)


__all__ = [
    "BOT_COMMANDS",
    "build_bot",
    "build_dispatcher",
    "build_redis",
    "set_bot_commands",
]
