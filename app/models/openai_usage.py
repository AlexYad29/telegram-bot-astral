"""Лог OpenAI-вызовов: токены и стоимость на каждый запрос.

Строим из него аналитику в `/admin_usage` (24h/7d/30d), а в perspective —
дашборды и алерты.

Стоимость храним в `cost_micro_cents` (BIGINT, 1e-8 USD) — точно, без float'а.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.models.mixins import TimestampMixin


class OpenAIUsage(TimestampMixin, Base):
    __tablename__ = "openai_usage"
    __table_args__ = (
        # Главные запросы — «суммарно за период» и «по задаче за период».
        Index("ix_openai_usage_created", "created_at"),
        Index("ix_openai_usage_task_created", "task", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # user_id может быть NULL — фоновые задачи (автопостинг канала) запускаются
    # без привязки к конкретному пользователю.
    user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # AITask.value — короткий идентификатор задачи (см. ai/tasks.py).
    task: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)

    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # USD * 1e8 — храним точно, считаем int'ами.
    cost_micro_cents: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )

    # HIT/MISS — для статистики кэша.
    cache_hit: Mapped[bool] = mapped_column(
        # bool здесь живой, не str: дешевле и нагляднее.
        # SQLAlchemy сам отобразит на BOOLEAN.
        # default=False, чтобы Alembic-миграция знала, что подставлять.
        __import__("sqlalchemy").Boolean,
        nullable=False,
        default=False,
    )

    def __repr__(self) -> str:
        return (
            f"<OpenAIUsage id={self.id} task={self.task} model={self.model} "
            f"in={self.prompt_tokens} out={self.completion_tokens} "
            f"cost_mc={self.cost_micro_cents} hit={self.cache_hit}>"
        )


__all__ = ["OpenAIUsage"]
