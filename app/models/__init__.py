"""ORM-модели проекта.

Импорт всех моделей в одном месте гарантирует, что они зарегистрированы
в `Base.metadata` ДО того, как Alembic читает `target_metadata`.
"""

from app.models.compatibility_check import CompatibilityCheck
from app.models.enums import (
    Gender,
    PostKind,
    PostStatus,
    SubscriptionPlan,
    SubscriptionStatus,
    TarotSpreadKind,
)
from app.models.generated_post import GeneratedPost
from app.models.subscription import Subscription
from app.models.tarot_history import TarotHistory
from app.models.user import User

__all__ = [
    "CompatibilityCheck",
    "Gender",
    "GeneratedPost",
    "PostKind",
    "PostStatus",
    "Subscription",
    "SubscriptionPlan",
    "SubscriptionStatus",
    "TarotHistory",
    "TarotSpreadKind",
    "User",
]
