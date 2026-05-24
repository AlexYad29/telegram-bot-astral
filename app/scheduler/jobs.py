"""Тело job'а авто-постинга: AI → запись в БД → отправка в канал → разметка статуса.

Чистая asyncio-функция без побочных зависимостей на aiogram — bot пробрасывается
аргументом, чтобы её легко мокать в тестах.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Protocol

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.enums import PostKind
from app.repositories.generated_post import GeneratedPostRepository
from app.services.numerology import life_path_number

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.ai.service import AIService

logger = logging.getLogger(__name__)


class BotProtocol(Protocol):
    """Минимальный контракт `aiogram.Bot.send_message` — для тестируемости."""

    async def send_message(self, chat_id: str | int, text: str) -> SentMessage: ...


class SentMessage(Protocol):
    """Объект-результат `send_message` — нам нужен только `message_id`."""

    message_id: int


def _day_number_for(today: date) -> int:
    """Число дня = сумма цифр даты `YYYYMMDD`, свёрнутая по правилам нумерологии."""
    return life_path_number(today)


async def run_channel_post_job(
    *,
    kind: PostKind,
    sessionmaker: async_sessionmaker[AsyncSession],
    ai_service: AIService,
    bot: BotProtocol,
    channel_id: str,
    today: date | None = None,
) -> None:
    """Сгенерировать пост, сохранить в БД и отправить в канал.

    Ошибка генерации → ничего не пишем в БД, только лог.
    Ошибка отправки → строка существует со статусом `failed` и текстом ошибки.
    """
    if not channel_id:
        logger.warning("autopost skipped: channel_id is empty, kind=%s", kind)
        return

    post_date = today or datetime.now(tz=UTC).date()
    logger.info("autopost generate kind=%s date=%s", kind, post_date.isoformat())

    day_number: int | None = None
    if kind is PostKind.DAY_NUMBER:
        day_number = _day_number_for(post_date)

    try:
        body = await ai_service.generate_channel_post(
            kind=kind, today=post_date, day_number=day_number
        )
    except Exception:
        logger.exception("autopost ai-generation failed kind=%s", kind)
        return

    body = body.strip()
    if not body:
        logger.warning("autopost ai returned empty body, skipping kind=%s", kind)
        return

    async with sessionmaker() as session:
        repo = GeneratedPostRepository(session)
        scheduled_for = datetime.now(tz=UTC)
        post = await repo.create(
            kind=kind,
            body=body,
            channel_id=channel_id,
            scheduled_for=scheduled_for,
        )
        await session.commit()

        try:
            sent = await bot.send_message(channel_id, body)
        except Exception as exc:
            logger.exception("autopost send failed kind=%s post_id=%s", kind, post.id)
            await repo.mark_failed(post.id, error=f"{type(exc).__name__}: {exc}")
            await session.commit()
            return

        await repo.mark_sent(
            post.id,
            telegram_message_id=sent.message_id,
            sent_at=datetime.now(tz=UTC),
        )
        await session.commit()
        logger.info(
            "autopost sent kind=%s post_id=%s tg_message_id=%s",
            kind,
            post.id,
            sent.message_id,
        )


__all__ = ["BotProtocol", "SentMessage", "run_channel_post_job"]
