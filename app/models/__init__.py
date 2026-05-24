"""ORM-модели проекта.

Импорт всех моделей в одном месте гарантирует, что они зарегистрированы
в `Base.metadata` ДО того, как Alembic читает `target_metadata`.
"""

from app.models.chat_message import ChatMessage, ChatRole
from app.models.chat_summary import ChatSummary
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
from app.models.openai_usage import OpenAIUsage
from app.models.subscription import Subscription
from app.models.tarot_history import TarotHistory
from app.models.user import User

__all__ = [
    "ChatMessage",
    "ChatRole",
    "ChatSummary",
    "CompatibilityCheck",
    "Gender",
    "GeneratedPost",
    "OpenAIUsage",
    "PostKind",
    "PostStatus",
    "Subscription",
    "SubscriptionPlan",
    "SubscriptionStatus",
    "TarotHistory",
    "TarotSpreadKind",
    "User",
]
