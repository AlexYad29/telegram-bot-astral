"""Entrypoint stub.

На ЭТАПЕ 1 здесь только конфиг и логирование — это позволяет проверить, что
переменные окружения подхватываются и приложение собирается.

На ЭТАПЕ 3 этот модуль будет заменён полноценным запуском aiogram dispatcher.
"""

from __future__ import annotations

import asyncio
import logging

from app.config.settings import get_settings
from app.utils.logging import setup_logging


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    logger.info(
        "astro-bot scaffolding ok",
        extra={
            "env": settings.env,
            "timezone": settings.timezone,
            "model": settings.openai_model,
        },
    )
    logger.info(
        "ЭТАП 1 готов. Подключение к Telegram/БД/OpenAI появится на следующих этапах."
    )


if __name__ == "__main__":
    asyncio.run(main())
