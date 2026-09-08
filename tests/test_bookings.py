"""Booking creation, overlap protection, and per-duration pricing:
app/services/bookings.py.
"""
from datetime import datetime, timedelta

import pytest

from app.models.booking import Booking
from app.models.psychologist import Psychologist
from app.models.user import User
from app.services.bookings import (
    parse_booking_start,
    booking_time_range,
    _ranges_overlap,
    create_booking_from_generated_slot,
)


# ---- pure helpers (no DB) ----------------------------------------------

def test_parse_booking_start():
    assert parse_booking_start("2026-09-07", "14:30") == datetime(2026, 9, 7, 14, 30)


def test_booking_time_range():
    booking = Booking(date="2026-09-07", start_time="14:00", duration=90)
    start, end = booking_time_range(booking)
    assert start == datetime(2026, 9, 7, 14, 0)
    assert end == datetime(2026, 9, 7, 15, 30)


def test_ranges_overlap_true_for_partial_overlap():
    # A 90-minute booking at 10:00 (10:00-11:30) and a 30-minute booking
    # starting at 10:30 (10:30-11:00) have different start times but do
    # overlap - this is exactly the case exact-string matching used to miss.
    a_start, a_end = datetime(2026, 1, 1, 10, 0), datetime(2026, 1, 1, 11, 30)
    b_start, b_end = datetime(2026, 1, 1, 10, 30), datetime(2026, 1, 1, 11, 0)
    assert _ranges_overlap(a_start, a_end, b_start, b_end) is True


def test_ranges_overlap_false_for_back_to_back():
    a_start, a_end = datetime(2026, 1, 1, 10, 0), datetime(2026, 1, 1, 11, 0)
    b_start, b_end = datetime(2026, 1, 1, 11, 0), datetime(2026, 1, 1, 12, 0)
    assert _ranges_overlap(a_start, a_end, b_start, b_end) is False


# ---- DB-backed (see conftest.py's `db` fixture: in-memory SQLite) ------

async def make_psychologist(db, durations):
    async with db() as session:
        psychologist = Psychologist(
            telegram_id=None,
            name="Тест Психологов",
            education="",
            durations=durations,
            specializations=[],
            help_topics=[],
            styles=[],
            therapy_experience_fit=[],
            is_active=True,
        )
        session.add(psychologist)
        await session.commit()
        await session.refresh(psychologist)
        return psychologist.id


@pytest.mark.asyncio
async def test_create_booking_resolves_price_from_psychologist_durations(db):
    psychologist_id = await make_psychologist(
        db, [{"minutes": 60, "price": 4000}, {"minutes": 30, "price": 2500}]
    )

    booking = await create_booking_from_generated_slot(
        telegram_id=1001,
        username="client",
        full_name="Client Name",
        phone=None,
        email=None,
        psychologist_id=psychologist_id,
        date="2099-01-10",
        start_time="10:00",
        duration=60,
    )

    assert booking is not None
    assert booking.price == 4000
    assert booking.status == "reserved"
    assert booking.payment_status == "pending"


@pytest.mark.asyncio
async def test_create_booking_fails_when_duration_has_no_price(db):
    psychologist_id = await make_psychologist(db, [{"minutes": 60, "price": 4000}])

    booking = await create_booking_from_generated_slot(
        telegram_id=1002,
        username="client",
        full_name="Client Name",
        phone=None,
        email=None,
        psychologist_id=psychologist_id,
        date="2099-01-10",
        start_time="10:00",
        duration=90,  # not offered
    )

    assert booking is None


@pytest.mark.asyncio
async def test_create_booking_allows_explicit_zero_price_free_booking(db):
    # The free 15-minute "selection" consultation passes price=0 explicitly
    # (see services/selection_15.py) - this must succeed, not be treated as
    # "no price set".
    psychologist_id = await make_psychologist(db, [{"minutes": 15, "price": 0}])

    booking = await create_booking_from_generated_slot(
        telegram_id=1003,
        username="client",
        full_name="Client Name",
        phone=None,
        email=None,
        psychologist_id=psychologist_id,
        date="2099-01-10",
        start_time="10:00",
        duration=15,
        price=0,
    )

    assert booking is not None
    assert booking.price == 0


@pytest.mark.asyncio
async def test_create_booking_rejects_overlapping_different_duration(db):
    # A 90-minute booking at 10:00 (10:00-11:30) must block a 30-minute
    # booking starting at 10:30, even though the start times differ.
    psychologist_id = await make_psychologist(
        db, [{"minutes": 90, "price": 6000}, {"minutes": 30, "price": 2500}]
    )

    first = await create_booking_from_generated_slot(
        telegram_id=2001,
        username="client1",
        full_name="Client One",
        phone=None,
        email=None,
        psychologist_id=psychologist_id,
        date="2099-01-10",
        start_time="10:00",
        duration=90,
    )
    assert first is not None

    second = await create_booking_from_generated_slot(
        telegram_id=2002,
        username="client2",
        full_name="Client Two",
        phone=None,
        email=None,
        psychologist_id=psychologist_id,
        date="2099-01-10",
        start_time="10:30",
        duration=30,
    )

    assert second is None


@pytest.mark.asyncio
async def test_create_booking_allows_back_to_back_non_overlapping(db):
    psychologist_id = await make_psychologist(db, [{"minutes": 60, "price": 4000}])

    first = await create_booking_from_generated_slot(
        telegram_id=3001,
        username="client1",
        full_name="Client One",
        phone=None,
        email=None,
        psychologist_id=psychologist_id,
        date="2099-01-10",
        start_time="10:00",
        duration=60,
    )
    assert first is not None

    second = await create_booking_from_generated_slot(
        telegram_id=3002,
        username="client2",
        full_name="Client Two",
        phone=None,
        email=None,
        psychologist_id=psychologist_id,
        date="2099-01-10",
        start_time="11:00",
        duration=60,
    )
    assert second is not None


@pytest.mark.asyncio
async def test_create_booking_allows_same_time_different_psychologist(db):
    psychologist_a = await make_psychologist(db, [{"minutes": 60, "price": 4000}])
    psychologist_b = await make_psychologist(db, [{"minutes": 60, "price": 4000}])

    first = await create_booking_from_generated_slot(
        telegram_id=4001,
        username="client1",
        full_name="Client One",
        phone=None,
        email=None,
        psychologist_id=psychologist_a,
        date="2099-01-10",
        start_time="10:00",
        duration=60,
    )
    second = await create_booking_from_generated_slot(
        telegram_id=4002,
        username="client2",
        full_name="Client Two",
        phone=None,
        email=None,
        psychologist_id=psychologist_b,
        date="2099-01-10",
        start_time="10:00",
        duration=60,
    )

    assert first is not None
    assert second is not None


@pytest.mark.asyncio
async def test_release_expired_bookings_notifies_client_exactly_once(db, monkeypatch):
    from tests.conftest import stub_send_message_safely, stub_notify_admin_booking_expired
    import app.services.bookings as bookings_module

    psychologist_id = await make_psychologist(db, [{"minutes": 60, "price": 4000}])

    booking = await create_booking_from_generated_slot(
        telegram_id=5001,
        username="client",
        full_name="Client Name",
        phone=None,
        email=None,
        psychologist_id=psychologist_id,
        date="2099-01-10",
        start_time="10:00",
        duration=60,
    )
    assert booking is not None

    # Force the reservation hold to already be in the past.
    async with db() as session:
        db_booking = await session.get(Booking, booking.id)
        db_booking.reserved_until = datetime.utcnow() - timedelta(minutes=1)
        await session.commit()

    sent = stub_send_message_safely(monkeypatch, bookings_module)
    admin_alerts = stub_notify_admin_booking_expired(monkeypatch, bookings_module)

    expired_count_1 = await bookings_module.release_expired_bookings()
    assert expired_count_1 == 1
    assert len(sent) == 1  # notified exactly once

    # A second call must find nothing left to expire (already flipped) and
    # must NOT notify again - this is the bug that was fixed: two different
    # code paths racing to expire the same row, only one of which notified.
    expired_count_2 = await bookings_module.release_expired_bookings()
    assert expired_count_2 == 0
    assert len(sent) == 1
    assert len(admin_alerts) == 1

    async with db() as session:
        db_booking = await session.get(Booking, booking.id)
        assert db_booking.status == "cancelled"
        assert db_booking.payment_status == "expired"


# ---- overlap matrix required by the audit: exact duplicate, contained/
# containing intervals, and a cancelled/expired reservation not blocking --

@pytest.mark.asyncio
async def test_create_booking_rejects_exact_duplicate(db):
    psychologist_id = await make_psychologist(db, [{"minutes": 60, "price": 4000}])

    first = await create_booking_from_generated_slot(
        telegram_id=6001, username="client1", full_name="Client One",
        phone=None, email=None, psychologist_id=psychologist_id,
        date="2099-01-10", start_time="10:00", duration=60,
    )
    assert first is not None

    second = await create_booking_from_generated_slot(
        telegram_id=6002, username="client2", full_name="Client Two",
        phone=None, email=None, psychologist_id=psychologist_id,
        date="2099-01-10", start_time="10:00", duration=60,
    )
    assert second is None


@pytest.mark.asyncio
async def test_create_booking_rejects_contained_interval(db):
    # A short booking fully inside an existing longer one must be rejected.
    psychologist_id = await make_psychologist(
        db, [{"minutes": 90, "price": 6000}, {"minutes": 30, "price": 2500}]
    )

    first = await create_booking_from_generated_slot(
        telegram_id=7001, username="client1", full_name="Client One",
        phone=None, email=None, psychologist_id=psychologist_id,
        date="2099-01-10", start_time="10:00", duration=90,  # 10:00-11:30
    )
    assert first is not None

    second = await create_booking_from_generated_slot(
        telegram_id=7002, username="client2", full_name="Client Two",
        phone=None, email=None, psychologist_id=psychologist_id,
        date="2099-01-10", start_time="10:30", duration=30,  # 10:30-11:00, inside the first
    )
    assert second is None


@pytest.mark.asyncio
async def test_create_booking_rejects_containing_interval(db):
    # A long booking that fully swallows an existing short one must also be
    # rejected - overlap math is symmetric regardless of booking order.
    psychologist_id = await make_psychologist(
        db, [{"minutes": 90, "price": 6000}, {"minutes": 30, "price": 2500}]
    )

    first = await create_booking_from_generated_slot(
        telegram_id=8001, username="client1", full_name="Client One",
        phone=None, email=None, psychologist_id=psychologist_id,
        date="2099-01-10", start_time="10:30", duration=30,  # 10:30-11:00
    )
    assert first is not None

    second = await create_booking_from_generated_slot(
        telegram_id=8002, username="client2", full_name="Client Two",
        phone=None, email=None, psychologist_id=psychologist_id,
        date="2099-01-10", start_time="10:00", duration=90,  # 10:00-11:30, swallows the first
    )
    assert second is None


@pytest.mark.asyncio
async def test_create_booking_ignores_cancelled_expired_reservation(db):
    # An expired, cancelled reservation must not block the time it used to
    # hold - this is exactly what release_expired_bookings exists for.
    psychologist_id = await make_psychologist(db, [{"minutes": 60, "price": 4000}])

    first = await create_booking_from_generated_slot(
        telegram_id=9001, username="client1", full_name="Client One",
        phone=None, email=None, psychologist_id=psychologist_id,
        date="2099-01-10", start_time="10:00", duration=60,
    )
    assert first is not None

    async with db() as session:
        db_booking = await session.get(Booking, first.id)
        db_booking.status = "cancelled"
        db_booking.payment_status = "expired"
        await session.commit()

    second = await create_booking_from_generated_slot(
        telegram_id=9002, username="client2", full_name="Client Two",
        phone=None, email=None, psychologist_id=psychologist_id,
        date="2099-01-10", start_time="10:00", duration=60,
    )
    assert second is not None


@pytest.mark.asyncio
async def test_create_booking_ignores_reservation_whose_hold_has_passed(db, monkeypatch):
    # A "reserved"/"pending" row whose reserved_until has already passed
    # must not block a new booking, even before release_expired_bookings
    # has physically flipped its status (create_booking_from_generated_slot
    # calls release_expired_bookings itself at the top, but this also
    # covers _is_booking_currently_active's own defensive check).
    #
    # The second create_booking_from_generated_slot call below finds the
    # first booking's hold has passed and, via release_expired_bookings,
    # expires it and sends the client a "your reservation expired"
    # notification - so Telegram delivery must be stubbed here exactly
    # like test_release_expired_bookings_notifies_client_exactly_once
    # does, or send_message_safely tries to construct a real aiogram Bot
    # with the test suite's fake BOT_TOKEN and blows up with
    # TokenValidationError. This is a test-infrastructure gap, not a
    # production bug - business logic never skipped stubbing this itself.
    from tests.conftest import stub_send_message_safely, stub_notify_admin_booking_expired
    import app.services.bookings as bookings_module

    sent = stub_send_message_safely(monkeypatch, bookings_module)
    admin_alerts = stub_notify_admin_booking_expired(monkeypatch, bookings_module)

    psychologist_id = await make_psychologist(db, [{"minutes": 60, "price": 4000}])

    first = await create_booking_from_generated_slot(
        telegram_id=10001, username="client1", full_name="Client One",
        phone=None, email=None, psychologist_id=psychologist_id,
        date="2099-01-10", start_time="10:00", duration=60,
    )
    assert first is not None
    assert first.status == "reserved"
    assert first.payment_status == "pending"

    async with db() as session:
        db_booking = await session.get(Booking, first.id)
        db_booking.reserved_until = datetime.utcnow() - timedelta(minutes=1)
        await session.commit()

    second = await create_booking_from_generated_slot(
        telegram_id=10002, username="client2", full_name="Client Two",
        phone=None, email=None, psychologist_id=psychologist_id,
        date="2099-01-10", start_time="10:00", duration=60,
    )
    assert second is not None

    # The expiry notification actually fired for the first booking - this
    # test now also covers the "expire on the way to a new booking" path
    # that test_release_expired_bookings_notifies_client_exactly_once
    # covers via a direct release_expired_bookings() call.
    assert len(sent) == 1
    assert len(admin_alerts) == 1


@pytest.mark.asyncio
async def test_concurrent_booking_attempts_only_one_succeeds(concurrent_db):
    """Two clients racing for the exact same time, fired concurrently via
    asyncio.gather.

    This used to be documented as passing on SQLite "because aiosqlite
    serializes access to the single in-memory connection either way" -
    that turned out to be wrong: SQLite's aiosqlite driver + SQLAlchemy's
    StaticPool for :memory: URLs share a single connection across both
    concurrent AsyncSessions with no isolation between them, and
    .with_for_update() compiles to a plain SELECT on SQLite (see
    sqlite_engine's docstring) - so both sides could independently decide
    "no overlap" before either had committed, and this test used to
    actually create two bookings.

    It passes now because of a real, separate guarantee:
    uq_active_booking_slot, a partial unique index on
    (psychologist_id, date, start_time) added in migrations/versions/
    0002_active_booking_slot_unique.py specifically so the database itself
    - not just the row lock - rejects an exact-duplicate-slot race
    regardless of what the application code's transaction isolation
    happens to look like. See create_booking_from_generated_slot's
    IntegrityError handling around its insert.

    That index only catches an EXACT (date, start_time) match, though - it
    cannot catch a partial overlap at a different start_time (a 90-minute
    10:00 booking vs. a 30-minute 10:30 one), which is exactly the case
    the row lock exists for. SQLite still cannot validate that more
    general guarantee (no equivalent of FOR UPDATE's block-then-refresh
    semantics exists there) - see tests/test_concurrency_postgres.py,
    which exercises it against a real PostgreSQL database.

    Uses concurrent_db (a real file-backed SQLite database with genuinely
    separate connections per session), not the usual db fixture - see
    concurrent_sqlite_engine's docstring in conftest.py for exactly why
    the shared single-connection :memory: database is unsafe for a test
    that actually races two sessions against each other.
    """
    import asyncio

    psychologist_id = await make_psychologist(concurrent_db, [{"minutes": 60, "price": 4000}])

    results = await asyncio.gather(
        create_booking_from_generated_slot(
            telegram_id=11001, username="client1", full_name="Client One",
            phone=None, email=None, psychologist_id=psychologist_id,
            date="2099-01-10", start_time="10:00", duration=60,
        ),
        create_booking_from_generated_slot(
            telegram_id=11002, username="client2", full_name="Client Two",
            phone=None, email=None, psychologist_id=psychologist_id,
            date="2099-01-10", start_time="10:00", duration=60,
        ),
    )

    successes = [r for r in results if r is not None]
    assert len(successes) == 1


@pytest.mark.asyncio
async def test_database_rejects_duplicate_active_slot_even_bypassing_app_logic(db):
    """Direct proof that uq_active_booking_slot (see
    migrations/versions/0002_active_booking_slot_unique.py) is a real,
    independent database-level guarantee - not just a side effect of how
    create_booking_from_generated_slot happens to behave. Two rows are
    inserted directly via the ORM, completely bypassing the row lock and
    overlap recheck that normally guard this, and the second one must
    still fail: the constraint itself is what's being tested here, not
    the application code around it.
    """
    from sqlalchemy.exc import IntegrityError

    psychologist_id = await make_psychologist(db, [{"minutes": 60, "price": 4000}])

    async with db() as session:
        first_user = User(telegram_id=90001, username="u1", full_name="U1")
        session.add(first_user)
        await session.commit()
        await session.refresh(first_user)

        first = Booking(
            user_id=first_user.id,
            psychologist_id=psychologist_id,
            date="2099-02-01",
            start_time="09:00",
            status="reserved",
            payment_status="pending",
            price=4000,
            duration=60,
        )
        session.add(first)
        await session.commit()

    with pytest.raises(IntegrityError):
        async with db() as session:
            second_user = User(telegram_id=90002, username="u2", full_name="U2")
            session.add(second_user)
            await session.commit()
            await session.refresh(second_user)

            second = Booking(
                user_id=second_user.id,
                psychologist_id=psychologist_id,
                date="2099-02-01",
                start_time="09:00",
                status="reserved",
                payment_status="pending",
                price=4000,
                duration=60,
            )
            session.add(second)
            await session.commit()


@pytest.mark.asyncio
async def test_database_allows_duplicate_slot_once_first_booking_is_cancelled(db):
    """The partial index only covers ACTIVE statuses - a cancelled booking
    must not permanently squat a slot at the database level either."""
    psychologist_id = await make_psychologist(db, [{"minutes": 60, "price": 4000}])

    async with db() as session:
        user = User(telegram_id=90003, username="u3", full_name="U3")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        cancelled = Booking(
            user_id=user.id,
            psychologist_id=psychologist_id,
            date="2099-02-02",
            start_time="09:00",
            status="cancelled",
            payment_status="cancelled",
            price=4000,
            duration=60,
        )
        session.add(cancelled)
        await session.commit()

        new_booking = Booking(
            user_id=user.id,
            psychologist_id=psychologist_id,
            date="2099-02-02",
            start_time="09:00",
            status="reserved",
            payment_status="pending",
            price=4000,
            duration=60,
        )
        session.add(new_booking)
        # Must not raise - a cancelled booking at the same slot is not
        # "active" and must not block a fresh one.
        await session.commit()


# ---- optional contact info: email/phone must never block a booking -----

@pytest.mark.asyncio
async def test_create_booking_with_both_phone_and_email(db):
    from app.models.user import User

    psychologist_id = await make_psychologist(db, [{"minutes": 60, "price": 4000}])

    booking = await create_booking_from_generated_slot(
        telegram_id=12001, username="client1", full_name="Client One",
        phone="+79991234567", email="client@example.com",
        psychologist_id=psychologist_id,
        date="2099-01-10", start_time="10:00", duration=60,
    )
    assert booking is not None

    async with db() as session:
        user = await session.get(User, booking.user_id)
        assert user.phone == "+79991234567"
        assert user.email == "client@example.com"


@pytest.mark.asyncio
async def test_create_booking_without_email(db):
    from app.models.user import User

    psychologist_id = await make_psychologist(db, [{"minutes": 60, "price": 4000}])

    booking = await create_booking_from_generated_slot(
        telegram_id=12002, username="client2", full_name="Client Two",
        phone="+79991234567", email=None,
        psychologist_id=psychologist_id,
        date="2099-01-10", start_time="10:00", duration=60,
    )
    assert booking is not None

    async with db() as session:
        user = await session.get(User, booking.user_id)
        assert user.phone == "+79991234567"
        assert user.email is None


@pytest.mark.asyncio
async def test_create_booking_without_phone(db):
    from app.models.user import User

    psychologist_id = await make_psychologist(db, [{"minutes": 60, "price": 4000}])

    booking = await create_booking_from_generated_slot(
        telegram_id=12003, username="client3", full_name="Client Three",
        phone=None, email="client3@example.com",
        psychologist_id=psychologist_id,
        date="2099-01-10", start_time="10:00", duration=60,
    )
    assert booking is not None

    async with db() as session:
        user = await session.get(User, booking.user_id)
        assert user.phone is None
        assert user.email == "client3@example.com"


@pytest.mark.asyncio
async def test_create_booking_without_phone_or_email(db):
    # Neither piece of contact info is required to complete a booking.
    from app.models.user import User

    psychologist_id = await make_psychologist(db, [{"minutes": 60, "price": 4000}])

    booking = await create_booking_from_generated_slot(
        telegram_id=12004, username="client4", full_name="Client Four",
        phone=None, email=None,
        psychologist_id=psychologist_id,
        date="2099-01-10", start_time="10:00", duration=60,
    )
    assert booking is not None
    assert booking.status == "reserved"

    async with db() as session:
        user = await session.get(User, booking.user_id)
        assert user.phone is None
        assert user.email is None
