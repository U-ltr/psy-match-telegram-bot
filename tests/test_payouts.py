"""Finance/payout tracking: app/services/payouts.py."""
import pytest

from app.models.booking import Booking
from app.models.psychologist import Psychologist
from app.services.payouts import (
    split_amount,
    create_payout_for_booking,
    mark_payout_ready,
    mark_payout_paid,
)


def test_split_amount_default_commission():
    # settings.platform_commission_percent defaults to 30.
    commission, psychologist_amount = split_amount(4000)
    assert commission == 1200
    assert psychologist_amount == 2800
    assert commission + psychologist_amount == 4000


def test_split_amount_explicit_commission_percent():
    commission, psychologist_amount = split_amount(1000, commission_percent=10)
    assert commission == 100
    assert psychologist_amount == 900


def test_split_amount_rounds_down_commission():
    # 333 * 30% = 99.9 -> rounds down to 99, psychologist gets the rest
    # (234), and the two halves must still sum back to the gross amount.
    commission, psychologist_amount = split_amount(333, commission_percent=30)
    assert commission == 99
    assert psychologist_amount == 234
    assert commission + psychologist_amount == 333


def test_split_amount_zero_commission():
    commission, psychologist_amount = split_amount(1000, commission_percent=0)
    assert commission == 0
    assert psychologist_amount == 1000


async def make_paid_booking(db, price):
    async with db() as session:
        psychologist = Psychologist(
            telegram_id=None,
            name="Тест Психологов",
            education="",
            durations=[{"minutes": 60, "price": price or 1}],
            specializations=[],
            help_topics=[],
            styles=[],
            therapy_experience_fit=[],
            is_active=True,
        )
        session.add(psychologist)
        await session.flush()

        booking = Booking(
            user_id=1,
            psychologist_id=psychologist.id,
            date="2099-01-10",
            start_time="10:00",
            status="paid",
            payment_status="paid",
            price=price,
            duration=60,
        )
        session.add(booking)
        await session.commit()
        await session.refresh(booking)
        return booking.id


@pytest.mark.asyncio
async def test_create_payout_for_booking(db):
    booking_id = await make_paid_booking(db, price=4000)

    payout = await create_payout_for_booking(booking_id)

    assert payout is not None
    assert payout.gross_amount == 4000
    assert payout.commission_amount == 1200
    assert payout.psychologist_amount == 2800
    assert payout.status == "pending"


@pytest.mark.asyncio
async def test_create_payout_for_booking_is_idempotent(db):
    # A retried/duplicated webhook must never create a second payout row
    # for the same booking.
    booking_id = await make_paid_booking(db, price=4000)

    first = await create_payout_for_booking(booking_id)
    second = await create_payout_for_booking(booking_id)

    assert first.id == second.id

    from app.models.payout import Payout
    from sqlalchemy import select

    async with db() as session:
        result = await session.execute(select(Payout).where(Payout.booking_id == booking_id))
        rows = result.scalars().all()

    assert len(rows) == 1


@pytest.mark.asyncio
async def test_free_booking_never_gets_a_payout(db):
    booking_id = await make_paid_booking(db, price=0)

    payout = await create_payout_for_booking(booking_id)

    assert payout is None


@pytest.mark.asyncio
async def test_mark_payout_ready_then_paid(db):
    booking_id = await make_paid_booking(db, price=4000)
    payout = await create_payout_for_booking(booking_id)

    assert await mark_payout_ready(payout.id) is True
    assert await mark_payout_paid(payout.id) is True

    from app.models.payout import Payout

    async with db() as session:
        updated = await session.get(Payout, payout.id)
        assert updated.status == "paid"
        assert updated.paid_at is not None


@pytest.mark.asyncio
async def test_mark_payout_paid_twice_is_a_no_op_second_time(db):
    booking_id = await make_paid_booking(db, price=4000)
    payout = await create_payout_for_booking(booking_id)

    assert await mark_payout_paid(payout.id) is True
    assert await mark_payout_paid(payout.id) is False
