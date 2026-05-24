"""Тонкая обёртка над `openai.AsyncOpenAI` с ретраями и единой точкой логирования.

Сервисы (`AIService`) пользуются именно этим клиентом — никаких прямых вызовов
`openai.*` в бизнес-логике. Это позволяет:

* подменять реализацию в тестах через простую заглушку;
* единообразно ретраить транзиентные ошибки;
* собирать счётчики/логи в одном месте.
"""

from __future__ import annotations

import logging
from typing import Protocol

from openai import APIConnectionError, APIError, AsyncOpenAI, RateLimitError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config.settings import Settings

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
    ) -> str:
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
    ) -> str:
        """Один Chat Completion-запрос с ретраями.

        Возвращает текст ответа или пустую строку, если модель ничего не вернула.
        """
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
            retry=retry_if_exception_type(self._RETRYABLE),
            reraise=True,
        ):
            with attempt:
                response = await self._client.chat.completions.create(
                    model=self._settings.openai_model,
                    temperature=(
                        temperature
                        if temperature is not None
                        else self._settings.openai_temperature
                    ),
                    max_tokens=(
                        max_tokens
                        if max_tokens is not None
                        else self._settings.openai_max_tokens
                    ),
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
        choices = response.choices
        if not choices:
            logger.warning("openai returned no choices")
            return ""
        content = choices[0].message.content or ""
        return content.strip()


__all__ = ["AIClient", "OpenAIClient"]
