"""Тесты `OpenAIClient` с подменённым `AsyncOpenAI`.

Не делаем реальных сетевых вызовов — собираем фейковый клиент с теми же
сигнатурами, проверяем, что:

* сообщения формируются как `system` + `user`;
* модель/temperature/max_tokens берутся из Settings либо из override'а;
* транзиентные ошибки ретраятся (на третьей попытке отдаётся ответ);
* пустой ответ модели превращается в пустую строку.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from openai import APIConnectionError

from app.services.ai.client import OpenAIClient


class _FakeMessage:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str | None) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str | None) -> None:
        self.choices = [_FakeChoice(content)] if content is not None else []


@pytest.fixture
def settings() -> Any:
    from app.config.settings import Settings

    return Settings(
        bot_token="t",
        openai_api_key="sk-test",
        openai_model="gpt-test",
        openai_temperature=0.7,
        openai_max_tokens=512,
    )


@pytest.fixture
def client(settings: Any, monkeypatch: pytest.MonkeyPatch) -> OpenAIClient:
    c = OpenAIClient(settings)
    # подменяем chat.completions.create на AsyncMock
    fake_create = AsyncMock()
    monkeypatch.setattr(c._client.chat.completions, "create", fake_create)
    return c


@pytest.mark.asyncio
async def test_complete_uses_settings_defaults(client: OpenAIClient) -> None:
    create: AsyncMock = client._client.chat.completions.create  # type: ignore[assignment]
    create.return_value = _FakeResponse("звёздный поток")

    text = await client.complete(system_prompt="sys", user_prompt="usr")

    assert text == "звёздный поток"
    create.assert_awaited_once()
    kwargs = create.await_args.kwargs
    assert kwargs["model"] == "gpt-test"
    assert kwargs["temperature"] == 0.7
    assert kwargs["max_tokens"] == 512
    assert kwargs["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]


@pytest.mark.asyncio
async def test_complete_respects_overrides(client: OpenAIClient) -> None:
    create: AsyncMock = client._client.chat.completions.create  # type: ignore[assignment]
    create.return_value = _FakeResponse("ок")

    await client.complete(
        system_prompt="s",
        user_prompt="u",
        max_tokens=100,
        temperature=0.1,
    )
    kwargs = create.await_args.kwargs
    assert kwargs["temperature"] == 0.1
    assert kwargs["max_tokens"] == 100


@pytest.mark.asyncio
async def test_complete_strips_whitespace(client: OpenAIClient) -> None:
    create: AsyncMock = client._client.chat.completions.create  # type: ignore[assignment]
    create.return_value = _FakeResponse("   ответ с пробелами   \n")

    text = await client.complete(system_prompt="s", user_prompt="u")
    assert text == "ответ с пробелами"


@pytest.mark.asyncio
async def test_complete_returns_empty_string_when_no_choices(
    client: OpenAIClient,
) -> None:
    create: AsyncMock = client._client.chat.completions.create  # type: ignore[assignment]
    create.return_value = _FakeResponse(None)

    text = await client.complete(system_prompt="s", user_prompt="u")
    assert text == ""


@pytest.mark.asyncio
async def test_complete_retries_transient_errors(client: OpenAIClient) -> None:
    create: AsyncMock = client._client.chat.completions.create  # type: ignore[assignment]
    # сперва две APIConnectionError, потом успешный ответ.
    create.side_effect = [
        APIConnectionError(request=None),  # type: ignore[arg-type]
        APIConnectionError(request=None),  # type: ignore[arg-type]
        _FakeResponse("после ретраев"),
    ]

    text = await client.complete(system_prompt="s", user_prompt="u")

    assert text == "после ретраев"
    assert create.await_count == 3
