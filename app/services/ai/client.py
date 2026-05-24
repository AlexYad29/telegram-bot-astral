"""Тонкая обёртка над `openai.AsyncOpenAI` с ретраями и единой точкой логирования.

Сервисы (`AIService`) пользуются именно этим клиентом — никаких прямых вызовов
`openai.*` в бизнес-логике. Это позволяет:

* подменять реализацию в тестах через простую заглушку;
* единообразно ретраить транзиентные ошибки;
* собирать счётчики/логи в одном месте.

ETAP 12: добавлен `chat_with_usage(...)` — возвращает `(text, TokenUsage)`,
плюс позволяет указать конкретную модель (для стратификации Nano/Mini).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Protocol

from openai import APIConnectionError, APIError, AsyncOpenAI, RateLimitError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config.settings import Settings
from app.services.ai.tokens import TokenUsage

logger = logging.getLogger(__name__)


class AIClient(Protocol):
    """Минимальный интерфейс AI-клиента, нужный сервисам."""

    async def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        model: str | None = None,
    ) -> str:
        ...

    async def chat_with_usage(
        self,
        *,
        messages: Sequence[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> tuple[str, TokenUsage]:
        ...


class OpenAIClient:
    """Production-реализация поверх `openai.AsyncOpenAI`.

    Ретраит только транзиентные ошибки (`APIConnectionError`, `RateLimitError`,
    `APIError` без HTTP 4xx). Финальная ошибка пробрасывается наверх — задача
    хендлера красиво её обработать.
    """

    _RETRYABLE: tuple[type[Exception], ...] = (
        APIConnectionError,
        RateLimitError,
        APIError,
    )

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
        )

    async def aclose(self) -> None:
        await self._client.close()

    async def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        model: str | None = None,
    ) -> str:
        """Один Chat Completion-запрос с ретраями (legacy API, без usage).

        Возвращает текст ответа или пустую строку, если модель ничего не вернула.
        Использовать только когда usage не нужен (например, summary build).
        """
        text, _ = await self.chat_with_usage(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=model or self._settings.openai_model,
            max_tokens=(
                max_tokens
                if max_tokens is not None
                else self._settings.openai_max_tokens
            ),
            temperature=(
                temperature
                if temperature is not None
                else self._settings.openai_temperature
            ),
        )
        return text

    async def chat_with_usage(
        self,
        *,
        messages: Sequence[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> tuple[str, TokenUsage]:
        """Chat Completion с явной моделью + token usage из ответа.

        Возвращает `(content, TokenUsage)`. Usage может быть нулевой, если
        OpenAI не вернул блок `usage` (редко, но бывает у моков и proxy).
        """
        response = None
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
            retry=retry_if_exception_type(self._RETRYABLE),
            reraise=True,
        ):
            with attempt:
                response = await self._client.chat.completions.create(
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    messages=list(messages),
                )
        if response is None:  # pragma: no cover — tenacity reraise гарантирует
            return "", TokenUsage(0, 0, 0)
        choices = response.choices
        content = (choices[0].message.content or "").strip() if choices else ""
        if not content:
            logger.warning("openai returned no content model=%s", model)
        raw_usage = getattr(response, "usage", None)
        if raw_usage is None:
            usage = TokenUsage(0, 0, 0)
        else:
            usage = TokenUsage(
                prompt_tokens=int(getattr(raw_usage, "prompt_tokens", 0) or 0),
                completion_tokens=int(
                    getattr(raw_usage, "completion_tokens", 0) or 0
                ),
                total_tokens=int(getattr(raw_usage, "total_tokens", 0) or 0),
            )
        return content, usage


__all__ = ["AIClient", "OpenAIClient"]
