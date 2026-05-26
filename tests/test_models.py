"""Smoke-тесты для ORM-моделей и репозиториев.

Не используем реальную БД — только проверяем, что:
- все модели зарегистрированы в `Base.metadata`,
- у `User` есть нужные relationship'ы,
- репозитории строятся и привязаны к правильным моделям.
"""

from __future__ import annotations

import pytest

from app.database.base import Base
from app.models import (
    CompatibilityCheck,
    GeneratedPost,
    Payment,
    Referral,
    Subscription,
    TarotHistory,
    User,
)
from app.repositories import (
    CompatibilityCheckRepository,
    GeneratedPostRepository,
    SubscriptionRepository,
    TarotHistoryRepository,
    UserRepository,
)


def test_metadata_contains_all_tables() -> None:
    tables = set(Base.metadata.tables.keys())
    assert tables == {
        "users",
        "subscriptions",
        "generated_posts",
        "tarot_history",
        "compatibility_checks",
        # ETAP 12 — таблицы cost-optimization слоя:
        "chat_messages",
        "chat_summaries",
        "openai_usage",
        # ETAP 13 — таблицы монетизации:
        "payments",
        "referrals",
    }


def test_user_relationships_are_wired() -> None:
    rels = {r.key: r for r in User.__mapper__.relationships}
    assert set(rels.keys()) == {
        "subscriptions",
        "tarot_history",
        "compatibility_checks",
        "payments",
        "referrals_made",
        "referral_source",
    }
    assert rels["subscriptions"].mapper.class_ is Subscription
    assert rels["tarot_history"].mapper.class_ is TarotHistory
    assert rels["compatibility_checks"].mapper.class_ is CompatibilityCheck
    assert rels["payments"].mapper.class_ is Payment
    assert rels["referrals_made"].mapper.class_ is Referral
    assert rels["referral_source"].mapper.class_ is Referral


def test_user_primary_key_is_bigint() -> None:
    pk = User.__table__.primary_key.columns["id"]
    # SQLAlchemy BigInteger -> Python int, тип в Postgres — bigint.
    assert pk.type.python_type is int
    assert not pk.autoincrement  # Telegram id мы вставляем сами.


@pytest.mark.parametrize(
    ("repo_cls", "model_cls"),
    [
        (UserRepository, User),
        (SubscriptionRepository, Subscription),
        (GeneratedPostRepository, GeneratedPost),
        (TarotHistoryRepository, TarotHistory),
        (CompatibilityCheckRepository, CompatibilityCheck),
    ],
)
def test_repository_bound_to_correct_model(repo_cls: type, model_cls: type) -> None:
    assert repo_cls.model is model_cls
