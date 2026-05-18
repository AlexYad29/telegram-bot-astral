"""OpenAI integration (ЭТАП 5).

Пакет состоит из трёх слоёв:

* :mod:`app.services.ai.client` — async OpenAI клиент с ретраями
  (`OpenAIClient`) + протокол `AIClient` для подмены в тестах.
* :mod:`app.services.ai.prompts` — чистые prompt-builder'ы и
  `SYSTEM_PROMPT` мистического ассистента.
* :mod:`app.services.ai.service` — `AIService`, фасад с готовыми
  сценариями (`generate_daily_forecast`, `generate_mystical_message`,
  `generate_esoteric_answer`).
"""

from app.services.ai.client import AIClient, OpenAIClient
from app.services.ai.prompts import (
    SYSTEM_PROMPT,
    UserContext,
    build_daily_forecast_prompt,
    build_esoteric_answer_prompt,
    build_mystical_message_prompt,
)
from app.services.ai.service import AIService

__all__ = [
    "SYSTEM_PROMPT",
    "AIClient",
    "AIService",
    "OpenAIClient",
    "UserContext",
    "build_daily_forecast_prompt",
    "build_esoteric_answer_prompt",
    "build_mystical_message_prompt",
]
