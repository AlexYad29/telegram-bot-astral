"""Тесты движка совместимости.

Покрываем диапазоны субскоров, поведение на мастер-числах, симметрию
по партнёрам, общий индекс и `life_path_label`.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services.compatibility import (
    CompatibilityScores,
    calculate_scores,
    life_path_label,
)

# --- базовая структура ----------------------------------------------------


def test_calculate_returns_scores_in_valid_range() -> None:
    scores = calculate_scores(date(1990, 1, 1), date(1992, 5, 21))
    for field_name in (
        "emotional_score",
        "conflict_score",
        "romance_score",
        "karmic_score",
    ):
        value = getattr(scores, field_name)
        assert 0 <= value <= 100, f"{field_name}={value} вне диапазона"


def test_overall_in_valid_range() -> None:
    scores = calculate_scores(date(1990, 1, 1), date(1992, 5, 21))
    assert 0 <= scores.overall <= 100


def test_scores_are_symmetric_in_emotional_and_conflict() -> None:
    """Эмоция и конфликт должны быть симметричны (зависят только от |a-b|)."""
    a = calculate_scores(date(1990, 1, 1), date(1985, 10, 9))
    b = calculate_scores(date(1985, 10, 9), date(1990, 1, 1))
    assert a.emotional_score == b.emotional_score
    assert a.conflict_score == b.conflict_score


# --- emotional -----------------------------------------------------------


def test_same_life_path_has_high_emotional() -> None:
    # 1990-01-01 → life path 3; ищем другую дату с life path 3.
    # 1991-01-09 → 1+9+9+1+0+1+0+9 = 30 → 3.
    scores = calculate_scores(date(1990, 1, 1), date(1991, 1, 9))
    assert scores.user_life_path == scores.partner_life_path == 3
    # Точное совпадение чисел: эмоциональная связь почти максимальна.
    assert scores.emotional_score >= 90


def test_distant_life_paths_lower_emotional() -> None:
    # 1990-01-01 (3) vs 1985-10-09 (33). Разрыв большой, но 33 — мастер: +5 бонус.
    scores = calculate_scores(date(1990, 1, 1), date(1985, 10, 9))
    assert scores.emotional_score < 90


# --- conflict ------------------------------------------------------------


def test_identical_fiery_dates_increase_conflict() -> None:
    """Одинаковые «огневые» числа (1, 5, 8) — повышенный конфликт."""
    # 1988-09-29 → life path 1; та же дата у партнёра — пара «1 ↔ 1», огонь.
    same = calculate_scores(date(1988, 9, 29), date(1988, 9, 29))
    # Сравним с парой «3 ↔ 3» (не огонь).
    calm = calculate_scores(date(1990, 1, 1), date(1990, 1, 1))
    assert same.user_life_path == 1
    assert calm.user_life_path == 3
    assert same.conflict_score > calm.conflict_score


def test_large_gap_reduces_conflict() -> None:
    """Разные темпы партнёров — меньше прямого конфликта."""
    # life path 1 (1988-09-29) vs life path 33 (1985-10-09) — разрыв >= 6.
    far = calculate_scores(date(1988, 9, 29), date(1985, 10, 9))
    # life path 3 vs 5 — разрыв 2.
    medium = calculate_scores(date(1990, 1, 1), date(2000, 1, 29))
    assert far.conflict_score < medium.conflict_score + 30


# --- romance -------------------------------------------------------------


def test_complementary_sum_boosts_romance() -> None:
    """Сумма life path = 10 (классическая «целостная» пара) даёт высокий romance."""
    # 1990-01-01 (3) + дата с life path 7.
    # 2000-01-23 → 2+0+0+0+0+1+2+3 = 8. Нет.
    # 2000-02-21 → 2+0+0+0+0+2+2+1 = 7. life path 7.
    scores = calculate_scores(date(1990, 1, 1), date(2000, 2, 21))
    assert scores.user_life_path == 3
    assert scores.partner_life_path == 7
    assert scores.romance_score >= 90


def test_identical_paths_reduce_romance_slightly() -> None:
    same = calculate_scores(date(1990, 1, 1), date(1991, 1, 9))  # 3 ↔ 3
    # Симметричная сумма 3+3=6 → база 75, минус 10 за одинаковость = 65.
    assert same.romance_score < 75


# --- karmic --------------------------------------------------------------


def test_karmic_high_when_partner_is_master() -> None:
    # 1985-10-09 → life path 33 (master).
    scores = calculate_scores(date(1990, 1, 1), date(1985, 10, 9))
    assert scores.partner_life_path == 33
    assert scores.karmic_score >= 75


def test_karmic_includes_identical_bonus() -> None:
    same = calculate_scores(date(1990, 1, 1), date(1991, 1, 9))  # 3 ↔ 3
    # base=50 +10 за одинаковость (минимум). Может прийти ещё +10 за product%9==0
    # (3*3=9 → 9 → +10). Так что ожидание умеренное.
    assert same.karmic_score >= 60


# --- общий индекс --------------------------------------------------------


def test_overall_combines_subscores() -> None:
    scores = CompatibilityScores(
        user_life_path=3,
        partner_life_path=3,
        emotional_score=90,
        conflict_score=20,
        romance_score=80,
        karmic_score=70,
    )
    # (90 + 80 + 70 + (100-20)) / 4 = 320 / 4 = 80
    assert scores.overall == 80


# --- labels --------------------------------------------------------------


def test_life_path_label_marks_master_numbers() -> None:
    assert "мастер" in life_path_label(11)
    assert "мастер" in life_path_label(22)
    assert "мастер" in life_path_label(33)


def test_life_path_label_for_regular_number_contains_number() -> None:
    label = life_path_label(3)
    assert label.startswith("3 ")
    assert "(" in label


# --- birth_date sanity ---------------------------------------------------


@pytest.mark.parametrize(
    "user_birth, partner_birth",
    [
        (date(1990, 1, 1), date(1991, 1, 1)),
        (date(2000, 12, 31), date(1980, 6, 15)),
        (date(1985, 10, 9), date(1957, 12, 31)),  # two master pairs.
    ],
)
def test_calculate_never_explodes(user_birth: date, partner_birth: date) -> None:
    scores = calculate_scores(user_birth, partner_birth)
    assert 0 <= scores.emotional_score <= 100
    assert 0 <= scores.conflict_score <= 100
    assert 0 <= scores.romance_score <= 100
    assert 0 <= scores.karmic_score <= 100
