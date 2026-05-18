"""Тесты валидаторов профиля (`app.services.profile`)."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.profile import (
    MAX_AGE_YEARS,
    MIN_AGE_YEARS,
    ProfileValidationError,
    parse_birth_date,
    parse_full_name,
)

# ---------- parse_full_name ----------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Иван", "Иван"),
        ("  Иван  Петров ", "Иван Петров"),
        ("Анна-Мария", "Анна-Мария"),
        ("O'Connor", "O'Connor"),
        ("А.С. Пушкин", "А.С. Пушкин"),
        ("John Doe Jr.", "John Doe Jr."),
    ],
)
def test_parse_full_name_accepts_valid(raw: str, expected: str) -> None:
    assert parse_full_name(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        " ",
        "a",  # слишком короткое
        "x" * 65,  # слишком длинное
        "Иван123",  # цифры запрещены
        "Иван@",  # спец-символы
        "<script>",
        "/start",
    ],
)
def test_parse_full_name_rejects_invalid(raw: str) -> None:
    with pytest.raises(ProfileValidationError):
        parse_full_name(raw)


# ---------- parse_birth_date ----------


_TODAY = date(2026, 5, 18)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1990-05-21", date(1990, 5, 21)),
        ("21.05.1990", date(1990, 5, 21)),
        ("21/05/1990", date(1990, 5, 21)),
        ("21-05-1990", date(1990, 5, 21)),
        ("  1990-05-21  ", date(1990, 5, 21)),
    ],
)
def test_parse_birth_date_accepts_valid(raw: str, expected: date) -> None:
    assert parse_birth_date(raw, today=_TODAY) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "не дата",
        "32.13.1990",
        "1990/05/21",  # неподдерживаемый формат
        "90-05-21",  # 2-значный год
    ],
)
def test_parse_birth_date_rejects_garbage(raw: str) -> None:
    with pytest.raises(ProfileValidationError):
        parse_birth_date(raw, today=_TODAY)


def test_parse_birth_date_rejects_future() -> None:
    future = _TODAY.replace(year=_TODAY.year + 1).isoformat()
    with pytest.raises(ProfileValidationError):
        parse_birth_date(future, today=_TODAY)


def test_parse_birth_date_rejects_too_young() -> None:
    # MIN_AGE_YEARS лет минус 1 день → должно быть отвергнуто.
    too_young = date(_TODAY.year - MIN_AGE_YEARS + 1, _TODAY.month, _TODAY.day)
    with pytest.raises(ProfileValidationError):
        parse_birth_date(too_young.isoformat(), today=_TODAY)


def test_parse_birth_date_rejects_too_old() -> None:
    too_old = date(_TODAY.year - MAX_AGE_YEARS - 1, _TODAY.month, _TODAY.day)
    with pytest.raises(ProfileValidationError):
        parse_birth_date(too_old.isoformat(), today=_TODAY)


def test_parse_birth_date_accepts_edge_min_age() -> None:
    # Ровно MIN_AGE_YEARS лет — валидно.
    boundary = date(_TODAY.year - MIN_AGE_YEARS, _TODAY.month, _TODAY.day)
    assert parse_birth_date(boundary.isoformat(), today=_TODAY) == boundary


def test_parse_birth_date_handles_leap_day_today() -> None:
    """Если сегодня 29 февраля високосного года, `_shift_years` должен схлопнуть
    границу до 28 февраля и не уронить парсер."""
    leap_today = date(2024, 2, 29)
    boundary = date(2024 - MIN_AGE_YEARS, 2, 28)
    assert parse_birth_date(boundary.isoformat(), today=leap_today) == boundary
