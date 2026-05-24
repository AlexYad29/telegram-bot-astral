"""Базовый smoke-тест для Settings, чтобы убедиться, что окружение читается."""

from __future__ import annotations

import os
from unittest import mock

import pytest

from app.config.settings import Settings


@pytest.fixture
def env() -> dict[str, str]:
    return {
        "BOT_TOKEN": "123:test",
        "OPENAI_API_KEY": "sk-test",
        "POSTGRES_PASSWORD": "secret",
        "ADMIN_IDS": "1, 2,3",
        "LOG_LEVEL": "debug",
    }


def test_settings_load(env: dict[str, str]) -> None:
    with mock.patch.dict(os.environ, env, clear=True):
        s = Settings(_env_file=None)  # type: ignore[call-arg]

    assert s.bot_token.get_secret_value() == "123:test"
    assert s.openai_api_key.get_secret_value() == "sk-test"
    assert s.admin_ids == [1, 2, 3]
    assert s.log_level == "DEBUG"
    assert s.postgres_dsn.startswith("postgresql+asyncpg://")
    assert s.redis_url == "redis://redis:6379/0"
