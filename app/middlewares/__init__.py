"""aiogram middlewares: DB session, throttling, logging, user upsert, AI service."""

from app.middlewares.ai_service import AIServiceMiddleware
from app.middlewares.db_session import DbSessionMiddleware
from app.middlewares.logging import LoggingMiddleware
from app.middlewares.throttling import THROTTLE_NOTICE, ThrottlingMiddleware
from app.middlewares.user_upsert import UserUpsertMiddleware

__all__ = [
    "THROTTLE_NOTICE",
    "AIServiceMiddleware",
    "DbSessionMiddleware",
    "LoggingMiddleware",
    "ThrottlingMiddleware",
    "UserUpsertMiddleware",
]
