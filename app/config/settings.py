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
    # Историческое значение, используется как fallback для старого кода.
    # Новые вызовы должны проходить через AITask → task_config_for() (см. ai/tasks.py).
    openai_model: str = "gpt-4.1-mini"
    openai_temperature: float = 0.9
    openai_max_tokens: int = 600

    # ---------- OpenAI: cost optimization (ETAP 12) ----------
    # Стратификация моделей. Nano — самая дешёвая, для массового/фонового
    # контента. Mini — для пользовательских запросов и сложных задач.
    openai_model_nano: str = "gpt-4.1-nano"
    openai_model_mini: str = "gpt-4.1-mini"

    # Per-task max_tokens — режут размер ответа (а значит и стоимость) на корню.
    # Каналу хватает 3-5 предложений (~250 токенов), tarot/compat побольше.
    openai_max_tokens_channel: int = 220
    openai_max_tokens_forecast: int = 220
    openai_max_tokens_esoteric: int = 280
    openai_max_tokens_tarot: int = 500
    openai_max_tokens_compatibility: int = 500
    openai_max_tokens_summary: int = 160
    # Temperature по задачам — каналу нужна вариативность чуть выше.
    openai_temperature_channel: float = 0.95
    openai_temperature_personal: float = 0.85

    # Pricing per 1M tokens, USD. По умолчанию — публичные OpenAI 4.1-rates
    # (на момент конфигурации). Считаем cents-in-DB, но pricing задаём в долларах.
    openai_price_nano_in_per_1m_usd: float = 0.10
    openai_price_nano_out_per_1m_usd: float = 0.40
    openai_price_mini_in_per_1m_usd: float = 0.40
    openai_price_mini_out_per_1m_usd: float = 1.60

    # Каноничный кодек для подсчёта токенов tiktoken'ом (gpt-4.1* идут через o200k_base).
    openai_tiktoken_encoding: str = "o200k_base"

    # ---------- Кэш AI-генераций ----------
    # Глобальный rubber-stamp: можно вырубить весь кэш в проде «одной кнопкой».
    ai_cache_enabled: bool = True
    # ~25 часов — суточные посты переживают полночь без regen.
    ai_cache_ttl_channel_seconds: int = 25 * 3600
    # Личный дневной прогноз — тоже до конца суток + запас.
    ai_cache_ttl_daily_forecast_seconds: int = 25 * 3600
    # Общие эзотерические ответы (вопросы пользователей) — храним неделю.
    ai_cache_ttl_esoteric_seconds: int = 7 * 24 * 3600
    # Кэш интерпретаций совместимости — стабильный контент, 30 дней.
    ai_cache_ttl_compatibility_seconds: int = 30 * 24 * 3600

    # ---------- Sliding window / summary memory ----------
    # Сколько последних реплик пихаем в prompt (sliding window).
    ai_history_window_size: int = 4
    # При каком количестве сообщений запускаем суммаризацию.
    ai_summary_trigger_messages: int = 20
    # Целевой объём хранимого summary (в символах, ~> токенах).
    ai_summary_max_chars: int = 600

    # ---------- AI request throttling ----------
    # Отдельный лимит на дорогие AI-команды (на пользователя).
    ai_throttle_seconds: float = 2.0
    ai_throttle_max_per_minute: int = 6
    # Для Premium-юзеров лимиты можно ослабить.
    ai_throttle_seconds_premium: float = 0.5
    ai_throttle_max_per_minute_premium: int = 20

    # ---------- Subscriptions / monetization (ETAP 13) ----------
    # Цены в Telegram Stars (XTR) — встроенный платёжный шлюз Telegram, без KYC.
    # 1 ⭐ ≈ $0.013 (Telegram payout курс), курс плавающий.
    subscription_stars_premium_1m: int = 199
    subscription_stars_premium_3m: int = 499
    subscription_stars_premium_12m: int = 1499
    subscription_stars_vip_1m: int = 499
    # Длительности подписок (в днях).
    subscription_days_1m: int = 30
    subscription_days_3m: int = 90
    subscription_days_12m: int = 365
    # Grace-period после истечения — фичи ещё доступны, бот напоминает продлить.
    subscription_grace_days: int = 2
    # Free-tier daily limits — после превышения отдаём «купи Premium».
    free_daily_forecasts: int = 1
    free_daily_tarot: int = 1
    free_daily_compatibility: int = 1
    free_daily_numerology: int = 3
    # Реферальная программа: за каждого приглашённого, который зарегистрировал
    # профиль (или купил Premium) — обоим выдаём бонусные дни Premium.
    referral_bonus_days_referrer: int = 7
    referral_bonus_days_referred: int = 3
    # Лимит на источник трафика — нельзя приглашать самого себя или
    # реферить одного юзера дважды (гарантируется FK + unique).

    # ---------- PostgreSQL ----------
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "astrobot"
    postgres_user: str = "astrobot"
    postgres_password: SecretStr = SecretStr("astrobot")
    sqlalchemy_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10

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
