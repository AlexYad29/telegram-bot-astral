"""Repository pattern для всех ORM-моделей.

Каждый репозиторий принимает `AsyncSession` и инкапсулирует SQL-запросы
к своей таблице. Сервисный слой работает только с репозиториями, не зная
о SQL/SQLAlchemy.
"""

from app.repositories.base import BaseRepository
from app.repositories.chat_message import ChatMessageRepository
from app.repositories.chat_summary import ChatSummaryRepository
from app.repositories.compatibility_check import CompatibilityCheckRepository
from app.repositories.generated_post import GeneratedPostRepository
from app.repositories.openai_usage import (
    OpenAIUsageRepository,
    TaskBreakdownRow,
    UsageAggregate,
)
from app.repositories.payment import PaymentRepository
from app.repositories.referral import ReferralRepository
from app.repositories.subscription import SubscriptionRepository
from app.repositories.tarot_history import TarotHistoryRepository
from app.repositories.user import UserRepository

__all__ = [
    "BaseRepository",
    "ChatMessageRepository",
    "ChatSummaryRepository",
    "CompatibilityCheckRepository",
    "GeneratedPostRepository",
    "OpenAIUsageRepository",
    "PaymentRepository",
    "ReferralRepository",
    "SubscriptionRepository",
    "TarotHistoryRepository",
    "TaskBreakdownRow",
    "UsageAggregate",
    "UserRepository",
]
