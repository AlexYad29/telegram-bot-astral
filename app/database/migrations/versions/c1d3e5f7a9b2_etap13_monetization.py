"""etap13: payments, referrals + vip in subscription_plan

Revision ID: c1d3e5f7a9b2
Revises: a8f1c2e9b3d0
Create Date: 2026-05-25 12:00:00.000000

ЭТАП 13 — таблицы и поля для монетизации:

* ``payments`` — журнал платежей (Telegram Stars / YooKassa / Stripe / manual),
  связан с user_id и опционально с subscription_id (одна подписка может
  получить несколько продлений → несколько Payment-записей).
* ``referrals`` — реферальная программа: «X пригласил Y» с гарантией
  ровно одного источника на одного приглашённого (UNIQUE на referred_user_id).

Enum-колонки хранятся как VARCHAR (native_enum=False), чтобы будущие
добавления тарифов/провайдеров не требовали ALTER TYPE.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1d3e5f7a9b2"
down_revision: str | None = "a8f1c2e9b3d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------- payments ----------
    op.create_table(
        "payments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("subscription_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "provider",
            sa.String(length=24),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "plan",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("provider_payment_id", sa.String(length=128), nullable=True),
        sa.Column("invoice_payload", sa.String(length=128), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_payments_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscriptions.id"],
            name=op.f("fk_payments_subscription_id_subscriptions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
    )
    op.create_index(
        "ix_payments_user_status",
        "payments",
        ["user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_payments_provider_payment_id",
        "payments",
        ["provider", "provider_payment_id"],
        unique=False,
    )

    # ---------- referrals ----------
    op.create_table(
        "referrals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("referrer_user_id", sa.BigInteger(), nullable=False),
        sa.Column("referred_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "reward_granted_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["referrer_user_id"],
            ["users.id"],
            name=op.f("fk_referrals_referrer_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["referred_user_id"],
            ["users.id"],
            name=op.f("fk_referrals_referred_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_referrals")),
        sa.UniqueConstraint(
            "referred_user_id", name="uq_referrals_referred_user_id"
        ),
    )
    op.create_index(
        "ix_referrals_referrer_user_id",
        "referrals",
        ["referrer_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_referrals_referrer_user_id", table_name="referrals")
    op.drop_table("referrals")
    op.drop_index("ix_payments_provider_payment_id", table_name="payments")
    op.drop_index("ix_payments_user_status", table_name="payments")
    op.drop_table("payments")
