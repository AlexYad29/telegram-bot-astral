"""Тесты `AdminFilter` — пропускает только известных админов."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.filters.admin import AdminFilter


@dataclass
class _FakeUser:
    id: int


@dataclass
class _FakeMessage:
    """Минимальный mock `aiogram.types.Message` для фильтра."""

    from_user: _FakeUser | None

    # AdminFilter использует isinstance(event, Message). Мы туда передадим
    # объект напрямую, минуя ветку `isinstance(event, Message)` —  это даст
    # `False`, поэтому используем monkeypatch на функцию `_extract_user_id`.


@pytest.mark.asyncio
async def test_admin_filter_passes_explicit_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    filt = AdminFilter(admin_ids=[111, 222])
    from app.filters import admin as admin_module

    def fake_extract(event: Any) -> int | None:
        return getattr(event.from_user, "id", None)

    monkeypatch.setattr(admin_module, "_extract_user_id", fake_extract)
    event = _FakeMessage(from_user=_FakeUser(id=111))
    assert await filt(event) is True


@pytest.mark.asyncio
async def test_admin_filter_rejects_non_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    filt = AdminFilter(admin_ids=[111, 222])
    from app.filters import admin as admin_module

    monkeypatch.setattr(
        admin_module,
        "_extract_user_id",
        lambda event: getattr(event.from_user, "id", None),
    )
    event = _FakeMessage(from_user=_FakeUser(id=333))
    assert await filt(event) is False


@pytest.mark.asyncio
async def test_admin_filter_rejects_no_user(monkeypatch: pytest.MonkeyPatch) -> None:
    filt = AdminFilter(admin_ids=[111])
    from app.filters import admin as admin_module

    monkeypatch.setattr(admin_module, "_extract_user_id", lambda event: None)
    event = _FakeMessage(from_user=None)
    assert await filt(event) is False


@pytest.mark.asyncio
async def test_admin_filter_reads_settings_when_no_explicit_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Если `admin_ids` не передан, фильтр читает их из Settings во время вызова."""
    filt = AdminFilter()

    from app.filters import admin as admin_module

    monkeypatch.setattr(
        admin_module,
        "_extract_user_id",
        lambda event: getattr(event.from_user, "id", None),
    )

    @dataclass
    class _FakeSettings:
        admin_ids: list[int]

    monkeypatch.setattr(
        "app.config.settings.get_settings",
        lambda: _FakeSettings(admin_ids=[42]),
    )

    assert await filt(_FakeMessage(from_user=_FakeUser(id=42))) is True
    assert await filt(_FakeMessage(from_user=_FakeUser(id=43))) is False
