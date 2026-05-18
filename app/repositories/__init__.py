"""Repository pattern для всех ORM-моделей.

Каждый репозиторий принимает `AsyncSession` и инкапсулирует SQL-запросы
к своей таблице. Сервисный слой работает только с репозиториями, не зная
о SQL/SQLAlchemy.
"""

from app.repositories.base import BaseRepository
from app.repositories.compatibility_check import CompatibilityCheckRepository
from app.repositories.generated_post import GeneratedPostRepository
from app.repositories.subscription import SubscriptionRepository
from app.repositories.tarot_history import TarotHistoryRepository
from app.repositories.user import UserRepository

__all__ = [
    "BaseRepository",
    "CompatibilityCheckRepository",
    "GeneratedPostRepository",
    "SubscriptionRepository",
    "TarotHistoryRepository",
    "UserRepository",
]
