"""Тесты сервиса Таро: загрузка колоды и трёхкарточный расклад."""

from __future__ import annotations

import random
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import app.services.tarot as tarot_mod
from app.services.tarot import (
    DeckError,
    DrawnCard,
    TarotCard,
    draw_three_card_spread,
    load_major_arcana,
    position_label_ru,
)


def test_deck_has_22_unique_cards() -> None:
    """Старшие арканы — ровно 22 карты, id уникальны."""
    deck = load_major_arcana()
    assert len(deck) == 22
    assert len({c.id for c in deck}) == 22
    # все карты — id 0..21 (классическая нумерация).
    assert sorted(c.id for c in deck) == list(range(22))


def test_deck_cards_are_well_formed() -> None:
    deck = load_major_arcana()
    for card in deck:
        assert isinstance(card, TarotCard)
        assert card.name_ru and card.name_en
        assert card.keywords  # минимум одно ключевое слово
        assert card.upright_short_ru
        # reversed_short_ru обязателен в нашем датасете.
        assert card.reversed_short_ru


def test_draw_three_card_spread_is_deterministic_with_seeded_rng() -> None:
    rng_a = random.Random(42)
    rng_b = random.Random(42)
    spread_a = draw_three_card_spread(rng=rng_a)
    spread_b = draw_three_card_spread(rng=rng_b)
    assert spread_a == spread_b
    assert len(spread_a) == 3
    positions = [d.position for d in spread_a]
    assert positions == ["past", "present", "future"]


def test_draw_three_cards_are_unique() -> None:
    rng = random.Random(123)
    spread = draw_three_card_spread(rng=rng)
    ids = {d.card.id for d in spread}
    assert len(ids) == 3, "карты в одном раскладе не должны повторяться"


def test_allow_reversed_false_never_reverses() -> None:
    rng = random.Random(7)
    spread = draw_three_card_spread(rng=rng, allow_reversed=False)
    assert all(d.reversed is False for d in spread)


def test_meaning_uses_reversed_text_when_reversed() -> None:
    deck = load_major_arcana()
    fool = next(c for c in deck if c.id == 0)
    assert fool.meaning(reversed_=False) == fool.upright_short_ru
    assert fool.meaning(reversed_=True) == fool.reversed_short_ru


def test_meaning_falls_back_to_upright_when_no_reversed_text() -> None:
    card = TarotCard(
        id=99,
        name_ru="Тест",
        name_en="Test",
        keywords=("a",),
        upright_short_ru="прямо",
        reversed_short_ru=None,
    )
    assert card.meaning(reversed_=True) == "прямо"


def test_drawn_card_as_dict_round_trip_shape() -> None:
    rng = random.Random(1)
    spread = draw_three_card_spread(rng=rng)
    payload = [d.as_dict() for d in spread]
    assert {item["position"] for item in payload} == {"past", "present", "future"}
    for item in payload:
        assert set(item.keys()) == {
            "position",
            "card_id",
            "name_en",
            "name_ru",
            "reversed",
        }
        assert isinstance(item["card_id"], int)
        assert isinstance(item["reversed"], bool)


def test_position_label_ru() -> None:
    assert position_label_ru("past") == "Прошлое"
    assert position_label_ru("present") == "Настоящее"
    assert position_label_ru("future") == "Будущее"


def test_load_major_arcana_raises_on_missing_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Если файла колоды нет — кидаем DeckError, а не падаем с FileNotFoundError."""
    load_major_arcana.cache_clear()
    monkeypatch.setattr(tarot_mod, "_DECK_PATH", Path("/no/such/file.json"))
    try:
        with pytest.raises(DeckError):
            load_major_arcana()
    finally:
        load_major_arcana.cache_clear()


def test_drawn_card_is_immutable() -> None:
    """`DrawnCard` — frozen dataclass, неизменяем по контракту."""
    rng = random.Random(0)
    spread = draw_three_card_spread(rng=rng)
    drawn: DrawnCard = spread[0]
    with pytest.raises(FrozenInstanceError):
        drawn.reversed = not drawn.reversed  # type: ignore[misc]
