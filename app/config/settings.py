"""Application settings loaded from environment variables.

Используется `pydantic-settings`. Все секреты оборачиваются в `SecretStr`,
чтобы случайно не залогировать их.

Источники в порядке приоритета:
1. Реальные переменные окружения.
2. Файл `.env` в корне проекта (для локальной разработки).
3. Значения по умолчанию, объявленные в модели.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Полная конфигурация приложения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- Telegram bot ----------
    bot_token: SecretStr
    bot_username: str | None = None

    # Канал для авто-постинга: @username или числовой -100... id.
    channel_id: str | None = None

    # Список Telegram user_id с правами админа.
    # NoDecode выключает попытку pydantic-settings распарсить значение как JSON —
    # формат в .env: ADMIN_IDS=123,456.
    admin_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    # ---------- OpenAI ----------
    openai_api_key: SecretStr
    openai_model: str = "gpt-4o-mini"
    openai_temperature: float = 0.9
    openai_max_tokens: int = 600

    # ---------- PostgreSQL ----------
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "astrobot"
    postgres_user: str = "astrobot"
    postgres_password: SecretStr = SecretStr("astrobot")

    # ---------- Redis ----------
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    # ---------- Application ----------
    env: str = "production"
    log_level: str = "INFO"
    timezone: str = "Europe/Moscow"

    # ---------- Anti-spam / rate-limit ----------
    rate_limit_messages_per_minute: int = 20
    throttle_default_rate: float = 0.5  # секунд между событиями одного пользователя

    # ---------- Computed URLs ----------
    @property
    def postgres_dsn(self) -> str:
        """Async DSN для SQLAlchemy / asyncpg."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:"
            f"{self.postgres_password.get_secret_value()}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_sync_dsn(self) -> str:
        """Sync DSN для Alembic (использует psycopg2/asyncpg в зависимости от env)."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:"
            f"{self.postgres_password.get_secret_value()}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ---------- Validators ----------
    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v: Any) -> Any:
        """`ADMIN_IDS=123,456` → `[123, 456]`. Пустая строка → `[]`."""
        if v is None or v == "":
            return []
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.upper()
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton — Settings читается из окружения ровно один раз."""
    return Settings()  # type: ignore[call-arg]
