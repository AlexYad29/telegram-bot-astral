"""Чистые валидаторы профильных полей.

Без зависимостей от aiogram/SQLAlchemy — поэтому покрываются обычными
unit-тестами и переиспользуются в админских флоу.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Final

# Имя: 2..64 символа, буквы (кириллица/латиница), пробелы, дефисы, апострофы, точки.
_NAME_MIN_LEN: Final[int] = 2
_NAME_MAX_LEN: Final[int] = 64
_NAME_RE: Final = re.compile(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё \-'.]*$")

# Реалистичный диапазон возраста — фильтр опечаток.
MIN_AGE_YEARS: Final[int] = 5
MAX_AGE_YEARS: Final[int] = 120

_DATE_FORMATS: Final[tuple[str, ...]] = (
    "%Y-%m-%d",
    "%d.%m.%Y",
    "%d/%m/%Y",
    "%d-%m-%Y",
)


class ProfileValidationError(ValueError):
    """Ошибка пользовательского ввода — текст уже оформлен «мистично», можно
    показать как есть в Telegram."""


def parse_full_name(raw: str) -> str:
    """Очистить и валидировать имя пользователя.

    - Триммим края, схлопываем повторные пробелы.
    - Проверяем длину и допустимые символы.
    """
    cleaned = " ".join(raw.split())
    if len(cleaned) < _NAME_MIN_LEN:
        raise ProfileValidationError(
            "✨ Имя слишком короткое. Звёзды не различают такие шёпоты — "
            "нужно минимум 2 символа."
        )
    if len(cleaned) > _NAME_MAX_LEN:
        raise ProfileValidationError(
            f"✨ Имя длиннее, чем нужно ({len(cleaned)} > {_NAME_MAX_LEN}). "
            "Оставь только то, как тебя зовут."
        )
    if not _NAME_RE.match(cleaned):
        raise ProfileValidationError(
            "✨ В этом имени есть символы, которые звёзды не читают. "
            "Используй буквы, пробел, дефис или апостроф."
        )
    return cleaned


def parse_birth_date(raw: str, *, today: date | None = None) -> date:
    """Распарсить дату рождения. Поддерживаем несколько форматов и
    валидируем реалистичный диапазон."""
    today = today or date.today()
    cleaned = raw.strip()
    parsed: date | None = None
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
        else:
            break
    if parsed is None:
        raise ProfileValidationError(
            "✨ Звёзды не узнают такой формат. Напиши дату так:\n"
            "<code>1990-05-21</code> или <code>21.05.1990</code>."
        )

    if parsed > today:
        raise ProfileValidationError(
            "✨ Эта дата ещё не настала. Линии будущего нельзя нанести "
            "на карту прошлого."
        )

    max_birth = _shift_years(today, -MIN_AGE_YEARS)
    min_birth = _shift_years(today, -MAX_AGE_YEARS)
    if parsed > max_birth:
        raise ProfileValidationError(
            f"✨ Ты ещё слишком юн для этого пути. Минимум — {MIN_AGE_YEARS} лет."
        )
    if parsed < min_birth:
        raise ProfileValidationError(
            "✨ Эта дата слишком далеко в прошлом. Проверь, не ошибся ли веком."
        )
    return parsed


def _shift_years(d: date, years: int) -> date:
    """`d` со сдвигом на N лет. Корректно обрабатывает 29 февраля."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        # 29 февраля → 28 февраля.
        return d.replace(year=d.year + years, day=28)


__all__ = [
    "MAX_AGE_YEARS",
    "MIN_AGE_YEARS",
    "ProfileValidationError",
    "parse_birth_date",
    "parse_full_name",
]
