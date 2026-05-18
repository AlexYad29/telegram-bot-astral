"""Расчёт совместимости двух людей по датам рождения.

Метод — нумерологический: на основе чисел жизненного пути двух партнёров
вычисляем четыре субскора (0..100):

* `emotional_score` — эмоциональная совместимость;
* `conflict_score` — потенциал конфликтов (чем выше — тем больше столкновений);
* `romance_score` — романтический потенциал;
* `karmic_score` — кармическая связь.

Формулы — детерминированные и тестируемые. AI-интерпретация (мистический
рассказ) живёт отдельно в `app.services.ai`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.services.numerology import (
    LIFE_PATH_MEANINGS,
    MASTER_NUMBERS,
    life_path_number,
)

_MASTER_PRIMARY: tuple[int, ...] = (11, 22, 33)


@dataclass(frozen=True, slots=True)
class CompatibilityScores:
    """Четыре нормализованных балла + life path обоих партнёров."""

    user_life_path: int
    partner_life_path: int
    emotional_score: int
    conflict_score: int
    romance_score: int
    karmic_score: int

    @property
    def overall(self) -> int:
        """Свести четыре субскора в общий «индекс совместимости»."""
        positives = self.emotional_score + self.romance_score + self.karmic_score
        # Конфликт работает как штраф; (100 - conflict) — это «гармония».
        harmony = 100 - self.conflict_score
        total = (positives + harmony) // 4
        return _clamp(total, 0, 100)


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _is_master(n: int) -> bool:
    return n in MASTER_NUMBERS


def _emotional(a: int, b: int) -> int:
    """Чем ближе числа, тем выше эмоциональная совместимость.

    Точное совпадение — 95 (а не 100: одинаковость тоже создаёт трение).
    Каждая единица разрыва — минус 9. Мастер-числа дают +5 «эзотерический бонус».
    """
    base = 95 - abs(a - b) * 9
    if _is_master(a) or _is_master(b):
        base += 5
    return _clamp(base, 20, 100)


def _conflict(a: int, b: int) -> int:
    """Конфликтность.

    Логика:

    * одинаковые «огневые» числа (1, 5, 8) → выраженный конфликт доминант;
    * близкие пути (разрыв 1..2) → лёгкое трение;
    * средний разрыв (3..5) → умеренный конфликт;
    * большой разрыв (6+) — разные орбиты, прямого конфликта меньше
      (а вот эмоциональное непонимание — это уже к emotional_score).
    """
    diff = abs(a - b)
    fiery = {1, 5, 8}
    if diff == 0:
        base = 30
        if a in fiery:
            base += 30
    elif diff <= 2:
        base = 25 + diff * 5
    elif diff <= 5:
        base = 40
    else:
        base = 25
    return _clamp(base, 5, 95)


def _romance(a: int, b: int) -> int:
    """Романтический потенциал.

    Дополняющие пары (сумма 10 или 7) — выше; «зеркальные» (a == b) —
    средне; пары с мастер-числом — приподнимаем.
    """
    s = a + b
    if s in (7, 10, 11):
        base = 90
    elif s in (5, 6, 8, 9, 12, 13):
        base = 75
    else:
        base = 60
    if a == b:
        base -= 10
    if _is_master(a) or _is_master(b):
        base += 5
    return _clamp(base, 20, 100)


def _karmic(a: int, b: int) -> int:
    """Кармическая связь.

    Сильнее всего, когда:

    * одно из чисел — мастер (11/22/33);
    * сумма редуцируется в мастер-число;
    * произведение даёт «9» — символ завершения цикла.
    """
    base = 50
    if _is_master(a) or _is_master(b):
        base += 25
    reduced_sum = _reduce_for_karma(a + b)
    if reduced_sum in MASTER_NUMBERS:
        base += 15
    product = (a * b) % 9 or 9
    if product == 9:
        base += 10
    if a == b:
        base += 10
    return _clamp(base, 10, 100)


def _reduce_for_karma(n: int) -> int:
    """Свёртка с сохранением мастер-чисел — копия `_reduce` из numerology,
    но без публичного API."""
    while n > 9 and n not in MASTER_NUMBERS:
        n = sum(int(d) for d in str(n))
    return n


def calculate_scores(user_birth: date, partner_birth: date) -> CompatibilityScores:
    """Точка входа: считаем все четыре скора по двум датам рождения."""
    a = life_path_number(user_birth)
    b = life_path_number(partner_birth)
    return CompatibilityScores(
        user_life_path=a,
        partner_life_path=b,
        emotional_score=_emotional(a, b),
        conflict_score=_conflict(a, b),
        romance_score=_romance(a, b),
        karmic_score=_karmic(a, b),
    )


def life_path_label(n: int) -> str:
    """Короткое имя life path — используется в подсказке AI и в карточке."""
    if n in _MASTER_PRIMARY:
        return f"мастер-число {n}"
    meaning = LIFE_PATH_MEANINGS.get(n, "")
    if meaning:
        first_sentence = meaning.split(".", 1)[0]
        return f"{n} ({first_sentence.lower()})"
    return str(n)


__all__ = [
    "CompatibilityScores",
    "calculate_scores",
    "life_path_label",
]
