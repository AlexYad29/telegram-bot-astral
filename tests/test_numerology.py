"""Тесты нумерологии: канонические таблицы и edge-кейсы редукции."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.numerology import (
    EXPRESSION_MEANINGS,
    LIFE_PATH_MEANINGS,
    MASTER_NUMBERS,
    NumerologyReading,
    calculate,
    expression_number,
    life_path_number,
)

# --- life_path ----------------------------------------------------------


@pytest.mark.parametrize(
    "birth, expected",
    [
        # 1985-10-09 → 1+9+8+5+1+0+0+9 = 33 → MASTER 33 (сохраняем).
        (date(1985, 10, 9), 33),
        # 1990-01-01 → 1+9+9+0+0+1+0+1 = 21 → 3.
        (date(1990, 1, 1), 3),
        # 2000-02-29 → 2+0+0+0+0+2+2+9 = 15 → 6.
        (date(2000, 2, 29), 6),
        # 1979-12-31 → 1+9+7+9+1+2+3+1 = 33 → MASTER 33.
        (date(1979, 12, 31), 33),
        # 1988-09-29 → 1+9+8+8+0+9+2+9 = 46 → 4+6 = 10 → 1+0 = 1.
        (date(1988, 9, 29), 1),
        # 2000-01-29 → 2+0+0+0+0+1+2+9 = 14 → 5.
        (date(2000, 1, 29), 5),
    ],
)
def test_life_path_number_canonical(birth: date, expected: int) -> None:
    assert life_path_number(birth) == expected


def test_life_path_preserves_master_numbers() -> None:
    # Берём дату, которая суммируется ровно в 22 (1990-12-19 → 1+9+9+0+1+2+1+9 = 32 → 5, не пойдёт).
    # 1992-08-29 → 1+9+9+2+0+8+2+9 = 40 → 4. Нужен пример master 11:
    # 1981-09-29 → 1+9+8+1+0+9+2+9 = 39 → 3 + 9 = 12 → 3. Нет.
    # 1900-01-01 → 1+9+0+0+0+1+0+1 = 12 → 3. Нет.
    # Возьмём дату для master 22:
    # 1990-09-22 → 1+9+9+0+0+9+2+2 = 32 → 5. Нет.
    # 1969-09-29 → 1+9+6+9+0+9+2+9 = 45 → 9. Нет.
    # 1939-12-31 → 1+9+3+9+1+2+3+1 = 29 → 11 → master 11.
    assert life_path_number(date(1939, 12, 31)) == 11
    # 1988-09-22 → 1+9+8+8+0+9+2+2 = 39 → 3. Нет.
    # 1989-09-22 → 1+9+8+9+0+9+2+2 = 40 → 4. Нет.
    # 1990-12-31 → 1+9+9+0+1+2+3+1 = 26 → 8.
    # 1957-12-31 → 1+9+5+7+1+2+3+1 = 29 → 11.
    assert life_path_number(date(1957, 12, 31)) == 11


# --- expression --------------------------------------------------------


@pytest.mark.parametrize(
    "name, expected",
    [
        # "Анна" → А(1) + Н(6) + Н(6) + А(1) = 14 → 5.
        ("Анна", 5),
        # "Иван" → И(1) + В(3) + А(1) + Н(6) = 11 → master 11.
        ("Иван", 11),
        # "John" → J(1) + O(6) + H(8) + N(5) = 20 → 2.
        ("John", 2),
        # Латинский Pythagorean — "Abc" = 1+2+3 = 6.
        ("Abc", 6),
        # Пробелы, дефисы, цифры, точки — игнор.
        ("Анна-Мария 2", expression_number("АннаМария")),
    ],
)
def test_expression_number_canonical(name: str, expected: int) -> None:
    assert expression_number(name) == expected


def test_expression_number_handles_mixed_case() -> None:
    # Регистр не должен влиять.
    assert expression_number("анна") == expression_number("АННА") == expression_number("Анна")


def test_expression_number_raises_on_empty() -> None:
    with pytest.raises(ValueError):
        expression_number("   ")
    with pytest.raises(ValueError):
        expression_number("123 - !")


# --- calculate (facade) ------------------------------------------------


def test_calculate_returns_reading_with_meanings() -> None:
    reading = calculate("Анна", date(1990, 1, 1))
    assert isinstance(reading, NumerologyReading)
    assert reading.life_path == 3
    assert reading.expression == 5
    assert reading.life_path_meaning == LIFE_PATH_MEANINGS[3]
    assert reading.expression_meaning == EXPRESSION_MEANINGS[5]


def test_calculate_immutable() -> None:
    reading = calculate("Анна", date(1990, 1, 1))
    with pytest.raises((AttributeError, Exception)):
        reading.life_path = 42  # type: ignore[misc]


# --- meaning tables completeness --------------------------------------


def test_meaning_tables_cover_1_to_9_and_masters() -> None:
    for n in (*range(1, 10), *MASTER_NUMBERS):
        assert n in LIFE_PATH_MEANINGS, f"life_path: нет ключа {n}"
        assert n in EXPRESSION_MEANINGS, f"expression: нет ключа {n}"
        assert LIFE_PATH_MEANINGS[n]
        assert EXPRESSION_MEANINGS[n]


def test_master_numbers_set_is_canonical() -> None:
    assert MASTER_NUMBERS == frozenset({11, 22, 33})
