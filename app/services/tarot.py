"""Сервис Таро: загрузка колоды, расклады.

Колода живёт в `assets/tarot/major_arcana.json` — 22 старших аркана. Минорные
арканы (56 карт) добавим позже отдельным датасетом, без правок этого модуля.

Чистый модуль: никаких сетей/БД/aiogram. Случайность инжектится — это
позволяет писать детерминированные тесты.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final, Literal

# Путь до JSON — относительно корня проекта. Корень = два уровня вверх от
# `app/services/`.
_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_DECK_PATH: Final[Path] = _PROJECT_ROOT / "assets" / "tarot" / "major_arcana.json"

#: Позиции в трёхкарточном раскладе (по часовой стрелке: прошлое → настоящее →
#: будущее). Хранится в БД как строка.
Position = Literal["past", "present", "future"]
THREE_CARD_POSITIONS: Final[tuple[Position, ...]] = ("past", "present", "future")


@dataclass(frozen=True, slots=True)
class TarotCard:
    """Описание одной карты колоды.

    `reversed_short_ru` опционален: если у карты нет описания в перевёрнутом
    положении, при выпадении «в перевёрнутую» используем `upright_short_ru`
    с пометкой.
    """

    id: int
    name_ru: str
    name_en: str
    keywords: tuple[str, ...]
    upright_short_ru: str
    reversed_short_ru: str | None = None

    def meaning(self, *, reversed_: bool) -> str:
        if reversed_ and self.reversed_short_ru:
            return self.reversed_short_ru
        return self.upright_short_ru


@dataclass(frozen=True, slots=True)
class DrawnCard:
    """Карта в конкретной позиции расклада."""

    position: Position
    card: TarotCard
    reversed: bool

    def as_dict(self) -> dict[str, object]:
        """Сериализация для JSONB-колонки `tarot_history.cards`."""
        return {
            "position": self.position,
            "card_id": self.card.id,
            "name_en": self.card.name_en,
            "name_ru": self.card.name_ru,
            "reversed": self.reversed,
        }


class DeckError(RuntimeError):
    """Колода не найдена или повреждена."""


@lru_cache(maxsize=1)
def load_major_arcana() -> tuple[TarotCard, ...]:
    """Прочитать колоду старших арканов с диска.

    Кэшируется на процесс: файл небольшой, читается один раз. Если файла
    нет — `DeckError`.
    """
    if not _DECK_PATH.exists():
        raise DeckError(f"deck file not found: {_DECK_PATH}")
    raw = json.loads(_DECK_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise DeckError("deck must be a non-empty JSON array")
    cards: list[TarotCard] = []
    for item in raw:
        if not isinstance(item, dict):
            raise DeckError(f"invalid card entry: {item!r}")
        cards.append(
            TarotCard(
                id=int(item["id"]),
                name_ru=str(item["name_ru"]),
                name_en=str(item["name_en"]),
                keywords=tuple(str(k) for k in item.get("keywords", [])),
                upright_short_ru=str(item["upright_short_ru"]),
                reversed_short_ru=(
                    str(item["reversed_short_ru"])
                    if item.get("reversed_short_ru")
                    else None
                ),
            )
        )
    if len({c.id for c in cards}) != len(cards):
        raise DeckError("card ids must be unique")
    return tuple(cards)


def draw_three_card_spread(
    *,
    rng: random.Random | None = None,
    allow_reversed: bool = True,
) -> tuple[DrawnCard, DrawnCard, DrawnCard]:
    """Случайно тянем 3 неповторяющиеся карты для позиций past/present/future.

    Используется `random.SystemRandom` по умолчанию — для пользователя это
    «настоящая» случайность, не псевдо. В тестах прокидываем seed-овый
    `random.Random`.
    """
    deck = load_major_arcana()
    if len(deck) < len(THREE_CARD_POSITIONS):
        raise DeckError("deck has fewer cards than spread positions")

    generator = rng or random.SystemRandom()
    chosen = generator.sample(deck, k=len(THREE_CARD_POSITIONS))
    drawn: list[DrawnCard] = []
    for pos, card in zip(THREE_CARD_POSITIONS, chosen, strict=True):
        reversed_ = bool(allow_reversed and generator.random() < 0.5)
        drawn.append(DrawnCard(position=pos, card=card, reversed=reversed_))
    return drawn[0], drawn[1], drawn[2]


_POSITION_LABEL_RU: Final[dict[Position, str]] = {
    "past": "Прошлое",
    "present": "Настоящее",
    "future": "Будущее",
}


def position_label_ru(position: Position) -> str:
    return _POSITION_LABEL_RU[position]


__all__ = [
    "DeckError",
    "DrawnCard",
    "Position",
    "THREE_CARD_POSITIONS",
    "TarotCard",
    "draw_three_card_spread",
    "load_major_arcana",
    "position_label_ru",
]
