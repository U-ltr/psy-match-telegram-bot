"""Single source of truth for per-duration pricing.

A psychologist's ``durations`` column is a JSON list of
``{"minutes": int, "price": int}`` objects. Nothing outside this module
should read or write that shape directly - go through these helpers so the
format only has to be understood in one place.
"""
from __future__ import annotations

from app.services.answer_formatting import minutes_declension, pluralize


def normalize_durations(raw: list | None) -> list[dict]:
    """Coerce whatever is in the DB into a clean, sorted list of pairs.

    Defensively handles the old shape (a bare list of ints with no price,
    e.g. ``[50, 60]``) by treating it as "price not set yet" (0) so old
    dev/seed rows don't crash the bot - they just show up as needing a
    price, which profile_validation.py already checks for.
    """
    if not raw:
        return []

    result = []
    for item in raw:
        if isinstance(item, dict):
            minutes = item.get("minutes")
            price = item.get("price")
            if minutes is None:
                continue
            result.append({"minutes": int(minutes), "price": int(price or 0)})
        else:
            # legacy bare-int shape
            result.append({"minutes": int(item), "price": 0})

    result.sort(key=lambda d: d["minutes"])
    return result


def get_duration_price(psychologist, duration_minutes: int) -> int | None:
    """Return the price for one specific duration, or None if not offered."""
    for item in normalize_durations(getattr(psychologist, "durations", None)):
        if item["minutes"] == duration_minutes and item["price"] > 0:
            return item["price"]
    return None


def get_priced_durations(psychologist) -> list[dict]:
    """Durations that actually have a price set (ready to be booked)."""
    return [d for d in normalize_durations(getattr(psychologist, "durations", None)) if d["price"] > 0]


def min_price(psychologist) -> int | None:
    priced = get_priced_durations(psychologist)
    if not priced:
        return None
    return min(item["price"] for item in priced)


def upsert_duration(durations: list | None, minutes: int, price: int) -> list[dict]:
    """Return a new durations list with `minutes` set to `price` (added or updated)."""
    current = normalize_durations(durations)
    found = False
    for item in current:
        if item["minutes"] == minutes:
            item["price"] = price
            found = True
            break
    if not found:
        current.append({"minutes": minutes, "price": price})
    current.sort(key=lambda d: d["minutes"])
    return current


def remove_duration(durations: list | None, minutes: int) -> list[dict]:
    current = normalize_durations(durations)
    return [item for item in current if item["minutes"] != minutes]


def format_priced_minutes_list(durations: list | None) -> str:
    """Compact one-line list of a psychologist's priced durations for a
    summary card, e.g. "30, 60 и 90 минут" - the trailing word is declined
    against the LAST number (the natural Russian convention when several
    numbers share one following noun), not hardcoded to "минут"."""
    priced = [d for d in normalize_durations(durations) if d["price"] > 0]
    if not priced:
        return "не указано"

    numbers = [d["minutes"] for d in priced]

    if len(numbers) == 1:
        return minutes_declension(numbers[0])

    joined = ", ".join(str(n) for n in numbers[:-1]) + f" и {numbers[-1]}"
    word = pluralize(numbers[-1], "минута", "минуты", "минут")
    return f"{joined} {word}"


def format_durations_text(durations: list | None) -> str:
    """Human-readable price list, e.g. "30 минут — 2500 руб." / "1 час —
    4000 руб." per line - properly declined per length, not a hardcoded
    word."""
    priced = [d for d in normalize_durations(durations) if d["price"] > 0]
    if not priced:
        return "не указано"
    return "\n".join(f"{minutes_declension(d['minutes'])} — {d['price']} ₽" for d in priced)
