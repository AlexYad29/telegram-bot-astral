"""Sliding-window + summary-based память для AI-диалога.

В prompt уходит:

* короткое summary из БД (если есть);
* последние N реплик (sliding window — `ai_history_window_size`);
* текущий user input.

Когда количество сохранённых сообщений переваливает за
`ai_summary_trigger_messages` — поверх «хвоста» строится новый summary
дешёвой моделью (`AITask.SUMMARY_BUILD`) и старые сообщения чистятся.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.config.settings import Settings
from app.models.chat_message import ChatMessage, ChatRole
from app.repositories.chat_message import ChatMessageRepository
from app.repositories.chat_summary import ChatSummaryRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.ai.client import AIClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MemorySnapshot:
    """То, что отдаём слоям выше для сборки промпта."""

    summary_text: str  # «» если нет
    window: tuple[ChatMessage, ...]  # хронологически, последние N
    total_messages: int


_SUMMARY_SYSTEM_PROMPT = (
    "Ты — компрессирующий редактор. Сжимай диалог в короткие заметки про "
    "интересы пользователя, его стиль общения и важные факты. Никакой воды, "
    "никакого markdown, не более 5-6 коротких предложений."
)


def _trim_summary(text: str, *, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


class SummaryMemoryService:
    """Доступ к sliding-window и summary-памяти пользователя."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def get_snapshot(
        self,
        session: AsyncSession,
        *,
        user_id: int,
    ) -> MemorySnapshot:
        """Достать memory snapshot для построения промпта."""
        msg_repo = ChatMessageRepository(session)
        sum_repo = ChatSummaryRepository(session)

        window = await msg_repo.last_n(
            user_id, self._settings.ai_history_window_size
        )
        total = await msg_repo.count_for_user(user_id)
        summary = await sum_repo.get_for_user(user_id)
        summary_text = (summary.summary_text or "") if summary else ""
        return MemorySnapshot(
            summary_text=summary_text,
            window=tuple(window),
            total_messages=total,
        )

    async def append_user(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        content: str,
        tokens: int = 0,
    ) -> None:
        await ChatMessageRepository(session).add_message(
            user_id=user_id,
            role=ChatRole.USER,
            content=content,
            tokens=tokens,
        )

    async def append_assistant(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        content: str,
        tokens: int = 0,
    ) -> None:
        await ChatMessageRepository(session).add_message(
            user_id=user_id,
            role=ChatRole.ASSISTANT,
            content=content,
            tokens=tokens,
        )

    async def maybe_rebuild_summary(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        ai_client: AIClient,
    ) -> bool:
        """Если сообщений > порога — пересобрать summary и обрезать старые.

        Возвращает True, если суммаризация была выполнена.
        """
        msg_repo = ChatMessageRepository(session)
        total = await msg_repo.count_for_user(user_id)
        if total < self._settings.ai_summary_trigger_messages:
            return False

        # Сообщения, попавшие в окно — оставляем; всё, что старше — сжимаем.
        window = await msg_repo.last_n(
            user_id, self._settings.ai_history_window_size
        )
        if not window:
            return False
        cutoff = window[0].created_at

        old_messages = await msg_repo.older_than(
            user_id, cutoff=cutoff, limit=500
        )
        if not old_messages:
            return False

        sum_repo = ChatSummaryRepository(session)
        existing = await sum_repo.get_for_user(user_id)
        existing_text = (existing.summary_text or "") if existing else ""

        new_summary = await self._build_summary(
            ai_client=ai_client,
            existing_summary=existing_text,
            old_messages=old_messages,
        )
        if not new_summary:
            return False

        covered = (existing.messages_covered if existing else 0) + len(
            old_messages
        )
        await sum_repo.upsert(
            user_id=user_id,
            summary_text=_trim_summary(
                new_summary, max_chars=self._settings.ai_summary_max_chars
            ),
            messages_covered=covered,
        )
        deleted = await msg_repo.delete_older_than(user_id, cutoff=cutoff)
        logger.info(
            "summary rebuilt user_id=%s covered=%d deleted=%d",
            user_id,
            covered,
            deleted,
        )
        # Зачем `now=...`: subreport timestamp; пока не используется.
        _ = datetime.now(tz=UTC)
        return True

    async def _build_summary(
        self,
        *,
        ai_client: AIClient,
        existing_summary: str,
        old_messages: list[ChatMessage] | object,
    ) -> str:
        """Собрать новый summary дешёвой моделью."""
        # Готовим компактный текст диалога.
        lines: list[str] = []
        for m in old_messages:  # type: ignore[union-attr]
            role = "User" if m.role is ChatRole.USER else "Assistant"
            content = (m.content or "").strip().replace("\n", " ")
            lines.append(f"{role}: {content}")
        history_text = "\n".join(lines)

        intro = (
            "Ниже — старый кусок диалога мистического ассистента с пользователем.\n"
        )
        existing_part = (
            f"Текущий summary, который надо обновить:\n{existing_summary}\n\n"
            if existing_summary
            else ""
        )
        user_prompt = (
            f"{intro}"
            f"{existing_part}"
            f"Старый диалог:\n{history_text}\n\n"
            "Обнови summary: интересы пользователя, стиль общения, важные факты. "
            f"До {self._settings.ai_summary_max_chars} символов. Без markdown."
        )
        try:
            return await ai_client.complete(
                system_prompt=_SUMMARY_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=self._settings.openai_max_tokens_summary,
                temperature=0.3,
            )
        except Exception:
            logger.exception("summary build failed user_history_len=%d", len(lines))
            return ""


__all__ = ["MemorySnapshot", "SummaryMemoryService"]
