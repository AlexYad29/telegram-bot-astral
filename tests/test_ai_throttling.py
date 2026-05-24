"""Тесты `AIRequestThrottle` middleware.

Используем минимальный фейк Redis с реализованной частью pipeline-API,
которую middleware действительно дёргает (zremrangebyscore / zrange /
zcard / zadd / expire).
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from app.middlewares.ai_throttling import AIRequestThrottle


class _FakePipeline:
    def __init__(self, redis: _FakeRedis) -> None:
        self._redis = redis
        self._ops: list[tuple[str, tuple[Any, ...]]] = []

    def zremrangebyscore(self, key: str, lo: float, hi: float) -> _FakePipeline:
        self._ops.append(("zremrangebyscore", (key, lo, hi)))
        return self

    def zrange(self, key: str, start: int, stop: int, *, withscores: bool = False):
        self._ops.append(("zrange", (key, start, stop, withscores)))
        return self

    def zcard(self, key: str) -> _FakePipeline:
        self._ops.append(("zcard", (key,)))
        return self

    def zadd(self, key: str, mapping: dict[str, float]) -> _FakePipeline:
        self._ops.append(("zadd", (key, mapping)))
        return self

    def expire(self, key: str, seconds: int) -> _FakePipeline:
        self._ops.append(("expire", (key, seconds)))
        return self

    async def execute(self) -> list[Any]:
        results: list[Any] = []
        for name, args in self._ops:
            if name == "zremrangebyscore":
                key, lo, hi = args
                self._redis._remrangebyscore(key, lo, hi)
                results.append(0)
            elif name == "zrange":
                key, start, stop, withscores = args
                results.append(self._redis._zrange(key, start, stop, withscores))
            elif name == "zcard":
                (key,) = args
                results.append(self._redis._zcard(key))
            elif name == "zadd":
                key, mapping = args
                for member, score in mapping.items():
                    self._redis._zadd(key, member, float(score))
                results.append(len(mapping))
            elif name == "expire":
                results.append(True)
        self._ops.clear()
        return results


class _FakeRedis:
    def __init__(self) -> None:
        # key -> list of (score, member)
        self._zsets: dict[str, list[tuple[float, str]]] = {}

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self)

    def _remrangebyscore(self, key: str, lo: float, hi: float) -> None:
        items = self._zsets.get(key, [])
        self._zsets[key] = [(s, m) for s, m in items if not (lo <= s <= hi)]

    def _zrange(
        self, key: str, start: int, stop: int, withscores: bool
    ) -> list[Any]:
        items = sorted(self._zsets.get(key, []), key=lambda sm: sm[0])
        if stop == -1:
            sliced = items[start:]
        else:
            sliced = items[start : stop + 1]
        if not withscores:
            return [m for _, m in sliced]
        return [(m, s) for s, m in sliced]

    def _zcard(self, key: str) -> int:
        return len(self._zsets.get(key, []))

    def _zadd(self, key: str, member: str, score: float) -> None:
        items = self._zsets.setdefault(key, [])
        items[:] = [(s, m) for s, m in items if m != member]
        items.append((score, member))


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _FakeMessage:
    """Минимальный duck-type под `aiogram.types.Message`."""

    def __init__(self, *, text: str, user_id: int) -> None:
        self.text = text
        self.from_user = _FakeUser(user_id)
        self.answers: list[str] = []

    async def answer(self, text: str, **_: Any) -> None:
        self.answers.append(text)


async def _noop_handler(event: Any, data: dict[str, Any]) -> str:
    return "handled"


@pytest.mark.asyncio
async def test_throttle_lets_non_ai_messages_through() -> None:
    redis = _FakeRedis()
    mw = AIRequestThrottle(
        redis,  # type: ignore[arg-type]
        max_per_minute=2,
        min_interval_seconds=0,
    )
    msg = _FakeMessage(text="hi", user_id=1)
    out = await mw(_noop_handler, msg, {})
    assert out == "handled"
    assert msg.answers == []


@pytest.mark.asyncio
async def test_throttle_lets_ai_command_through_under_limit() -> None:
    redis = _FakeRedis()
    mw = AIRequestThrottle(
        redis,  # type: ignore[arg-type]
        max_per_minute=2,
        min_interval_seconds=0,
    )
    msg = _FakeMessage(text="/forecast", user_id=1)
    out = await mw(_noop_handler, msg, {})
    assert out == "handled"


@pytest.mark.asyncio
async def test_throttle_blocks_after_max_per_minute() -> None:
    redis = _FakeRedis()
    mw = AIRequestThrottle(
        redis,  # type: ignore[arg-type]
        max_per_minute=2,
        min_interval_seconds=0,
    )
    user_id = 1
    for _ in range(2):
        ok_msg = _FakeMessage(text="/forecast", user_id=user_id)
        await mw(_noop_handler, ok_msg, {})
    blocked = _FakeMessage(text="/forecast", user_id=user_id)
    out = await mw(_noop_handler, blocked, {})
    assert out is None
    assert blocked.answers, "Пользователь должен получить notice"


@pytest.mark.asyncio
async def test_throttle_per_user_isolation() -> None:
    redis = _FakeRedis()
    mw = AIRequestThrottle(
        redis,  # type: ignore[arg-type]
        max_per_minute=1,
        min_interval_seconds=0,
    )
    a = _FakeMessage(text="/forecast", user_id=1)
    b = _FakeMessage(text="/forecast", user_id=2)
    await mw(_noop_handler, a, {})
    # Юзер 2 не должен страдать от лимита юзера 1.
    out_b = await mw(_noop_handler, b, {})
    assert out_b == "handled"


@pytest.mark.asyncio
async def test_throttle_min_interval_blocks_dup_press() -> None:
    redis = _FakeRedis()
    mw = AIRequestThrottle(
        redis,  # type: ignore[arg-type]
        max_per_minute=10,
        min_interval_seconds=5.0,
    )
    a = _FakeMessage(text="/forecast", user_id=1)
    b = _FakeMessage(text="/forecast", user_id=1)
    await mw(_noop_handler, a, {})
    started = time.monotonic()
    out = await mw(_noop_handler, b, {})
    # Не должно быть реального sleep'а — middleware просто отбрасывает.
    assert time.monotonic() - started < 1.0
    assert out is None
    assert b.answers
