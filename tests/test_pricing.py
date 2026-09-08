"""Per-duration pricing: app/services/pricing.py.

Every psychologist sets their own price per session length - there is no
single flat price. These tests cover the shape-normalization, lookup, and
formatting helpers that are the only sanctioned way to read/write that
data (see the module docstring in pricing.py).
"""
from types import SimpleNamespace

from app.services.pricing import (
    normalize_durations,
    get_duration_price,
    get_priced_durations,
    min_price,
    upsert_duration,
    remove_duration,
    format_durations_text,
    format_priced_minutes_list,
)


def psychologist(durations):
    return SimpleNamespace(durations=durations)


def test_normalize_durations_sorts_by_minutes():
    raw = [{"minutes": 60, "price": 4000}, {"minutes": 30, "price": 2500}]
    assert normalize_durations(raw) == [
        {"minutes": 30, "price": 2500},
        {"minutes": 60, "price": 4000},
    ]


def test_normalize_durations_empty_or_none():
    assert normalize_durations(None) == []
    assert normalize_durations([]) == []


def test_normalize_durations_handles_legacy_bare_int_shape():
    # Old dev/seed rows stored durations as a bare list of ints with no
    # price at all - must not crash, shows up as price=0 (unpriced).
    assert normalize_durations([50, 60]) == [
        {"minutes": 50, "price": 0},
        {"minutes": 60, "price": 0},
    ]


def test_normalize_durations_skips_items_without_minutes():
    raw = [{"price": 1000}, {"minutes": 30, "price": 2000}]
    assert normalize_durations(raw) == [{"minutes": 30, "price": 2000}]


def test_normalize_durations_missing_price_defaults_to_zero():
    raw = [{"minutes": 30}]
    assert normalize_durations(raw) == [{"minutes": 30, "price": 0}]


def test_get_duration_price_found():
    p = psychologist([{"minutes": 30, "price": 2500}, {"minutes": 60, "price": 4000}])
    assert get_duration_price(p, 60) == 4000


def test_get_duration_price_not_offered_returns_none():
    p = psychologist([{"minutes": 60, "price": 4000}])
    assert get_duration_price(p, 90) is None


def test_get_duration_price_zero_price_treated_as_unset():
    # A duration entered with no price yet must not be bookable at 0 ₽.
    p = psychologist([{"minutes": 60, "price": 0}])
    assert get_duration_price(p, 60) is None


def test_get_priced_durations_filters_out_zero_price():
    p = psychologist([
        {"minutes": 30, "price": 0},
        {"minutes": 60, "price": 4000},
    ])
    assert get_priced_durations(p) == [{"minutes": 60, "price": 4000}]


def test_min_price_picks_cheapest_priced_duration():
    p = psychologist([
        {"minutes": 30, "price": 3000},
        {"minutes": 60, "price": 2000},
        {"minutes": 90, "price": 0},  # unpriced, must be ignored
    ])
    assert min_price(p) == 2000


def test_min_price_none_when_nothing_priced():
    p = psychologist([{"minutes": 60, "price": 0}])
    assert min_price(p) is None


def test_upsert_duration_adds_new():
    result = upsert_duration([{"minutes": 60, "price": 4000}], 30, 2500)
    assert result == [
        {"minutes": 30, "price": 2500},
        {"minutes": 60, "price": 4000},
    ]


def test_upsert_duration_updates_existing():
    result = upsert_duration([{"minutes": 60, "price": 4000}], 60, 5000)
    assert result == [{"minutes": 60, "price": 5000}]


def test_remove_duration():
    result = remove_duration(
        [{"minutes": 30, "price": 2500}, {"minutes": 60, "price": 4000}], 30
    )
    assert result == [{"minutes": 60, "price": 4000}]


def test_format_durations_text_lists_priced_only():
    text = format_durations_text([
        {"minutes": 30, "price": 0},
        {"minutes": 60, "price": 4000},
        {"minutes": 90, "price": 6000},
    ])
    assert text == "60 минут — 4000 ₽\n90 минут — 6000 ₽"


def test_format_durations_text_empty_shows_not_specified():
    assert format_durations_text([]) == "не указано"
    assert format_durations_text(None) == "не указано"


def test_format_durations_text_declines_each_line_by_its_own_number():
    text = format_durations_text([
        {"minutes": 1, "price": 1000},
        {"minutes": 11, "price": 1500},
        {"minutes": 21, "price": 2000},
    ])
    assert text == "1 минута — 1000 ₽\n11 минут — 1500 ₽\n21 минута — 2000 ₽"


def test_format_priced_minutes_list_single_duration():
    p = psychologist([{"minutes": 50, "price": 3500}])
    assert format_priced_minutes_list(p.durations) == "50 минут"


def test_format_priced_minutes_list_joins_multiple_with_and_declined_by_last_number():
    p = psychologist([
        {"minutes": 30, "price": 2500},
        {"minutes": 60, "price": 4000},
        {"minutes": 90, "price": 6000},
    ])
    assert format_priced_minutes_list(p.durations) == "30, 60 и 90 минут"


def test_format_priced_minutes_list_ignores_unpriced_durations():
    p = psychologist([
        {"minutes": 30, "price": 0},
        {"minutes": 60, "price": 4000},
    ])
    assert format_priced_minutes_list(p.durations) == "60 минут"


def test_format_priced_minutes_list_empty_shows_not_specified():
    assert format_priced_minutes_list([]) == "не указано"
    assert format_priced_minutes_list(None) == "не указано"


def test_format_priced_minutes_list_declines_last_number_correctly_when_it_ends_in_one():
    # "21" ends in 1 -> "минута", even though it's the tail of a joined list.
    p = psychologist([
        {"minutes": 20, "price": 1500},
        {"minutes": 21, "price": 1600},
    ])
    assert format_priced_minutes_list(p.durations) == "20 и 21 минута"
