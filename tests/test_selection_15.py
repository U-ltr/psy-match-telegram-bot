"""The free 15-minute "selection" consultation: app/services/selection_15.py.

Must never be a real paid product - price is always 0 and it must never
reach the YooKassa payment flow.
"""
import pytest
from sqlalchemy import select

from app.models.psychologist import Psychologist
from app.services.selection_15 import (
    get_or_create_selection_specialist,
    get_selection_available_slots,
    SELECTION_SPECIALIST_NAME,
)
from app.services.bookings import create_booking_from_generated_slot
from app.services.payouts import create_payout_for_booking


@pytest.mark.asyncio
async def test_get_or_create_selection_specialist_is_idempotent(db):
    first = await get_or_create_selection_specialist()
    second = await get_or_create_selection_specialist()

    assert first.id == second.id

    async with db() as session:
        rows = (
            await session.execute(
                select(Psychologist).where(Psychologist.name == SELECTION_SPECIALIST_NAME)
            )
        ).scalars().all()

    assert len(rows) == 1


@pytest.mark.asyncio
async def test_selection_specialist_duration_price_is_always_zero(db):
    specialist = await get_or_create_selection_specialist()
    assert specialist.durations == [{"minutes": 15, "price": 0}]


@pytest.mark.asyncio
async def test_selection_available_slots_are_all_free(db):
    slots = await get_selection_available_slots(limit=4)

    assert len(slots) > 0
    assert all(slot["price"] == 0 for slot in slots)
    assert all(slot["duration"] == 15 for slot in slots)


@pytest.mark.asyncio
async def test_free_booking_end_to_end_never_creates_a_payout(db):
    specialist = await get_or_create_selection_specialist()
    slots = await get_selection_available_slots(limit=1)
    slot = slots[0]

    booking = await create_booking_from_generated_slot(
        telegram_id=9001,
        username="client",
        full_name="Client Name",
        phone=None,
        email=None,
        psychologist_id=specialist.id,
        slot_data={"date": slot["date"], "time": slot["time"], "duration": slot["duration"]},
        price=slot["price"],
    )

    assert booking is not None
    assert booking.price == 0

    payout = await create_payout_for_booking(booking.id)
    assert payout is None
