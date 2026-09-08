from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import async_session
from app.models.booking import Booking
from app.models.psychologist import Psychologist
from app.models.user import User
from app.services.pricing import get_duration_price
from app.services.schedule import time_to_minutes
from app.services.jitsi import get_or_create_meeting_link
from app.services.telegram_sender import send_message_safely
from app.services.admin_notifications import notify_admin_booking_expired


RESERVATION_MINUTES = 20

ACTIVE_BOOKING_STATUSES = ["reserved", "confirmed", "paid"]
ACTIVE_PAYMENT_STATUSES = ["pending", "paid"]


def utcnow() -> datetime:
    return datetime.utcnow()


def parse_booking_start(date_value: str, start_time: str) -> datetime:
    return datetime.strptime(f"{date_value} {start_time}", "%Y-%m-%d %H:%M")


def booking_time_range(booking: Booking) -> tuple[datetime, datetime]:
    start = parse_booking_start(booking.date, booking.start_time)
    return start, start + timedelta(minutes=booking.duration or 0)


def _ranges_overlap(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    return start_a < end_b and start_b < end_a


async def get_or_create_user(
    telegram_id: int,
    username: str | None,
    full_name: str | None,
    age_group: str | None = None,
    phone: str | None = None,
    email: str | None = None,
) -> User:
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()

        if user:
            user.username = username
            user.full_name = full_name

            if age_group:
                user.age_group = age_group

            if phone:
                user.phone = phone

            if email is not None:
                user.email = email

            await session.commit()
            await session.refresh(user)
            return user

        user = User(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            age_group=age_group,
            phone=phone,
            email=email,
        )

        session.add(user)
        await session.commit()
        await session.refresh(user)

        return user


async def _notify_booking_expired(booking_id: int, user_id: int, date: str, start_time: str) -> None:
    async with async_session() as session:
        user = await session.get(User, user_id)

    if not user:
        return

    await send_message_safely(
        user.telegram_id,
        (
            "Время резерва истекло ⚠️\n\n"
            f"Запись №{booking_id} отменена, потому что оплата не была завершена.\n"
            "Вы можете выбрать другое время и записаться снова."
        ),
    )

    await notify_admin_booking_expired(
        booking_id=booking_id,
        client_name=user.full_name or "не указано",
        date=date,
        start_time=start_time,
    )


async def release_expired_bookings() -> int:
    """Expires unpaid reservations whose hold has passed.

    This is called opportunistically from many read paths (so slot
    availability and booking lists never show a stale reservation), and
    also from the background unpaid_bookings_loop. Whichever caller happens
    to be first to see a given expired row is the one that flips it - the
    query only ever matches still-pending rows, so a row is expired and
    notified about exactly once no matter how many places call this.
    Previously the background loop had its own separate copy of this
    "expire + notify" logic (setting a different status value, "expired",
    that nothing else recognized) which raced against this function and,
    since this function runs far more often, almost always lost - so the
    "your reservation expired" notification to the client essentially never
    fired in practice. Unifying it here fixes that.
    """
    now = utcnow()

    async with async_session() as session:
        result = await session.execute(
            select(Booking).where(
                Booking.status == "reserved",
                Booking.payment_status == "pending",
                Booking.reserved_until.is_not(None),
                Booking.reserved_until < now,
            )
        )

        bookings = result.scalars().all()

        expired_info = []

        for booking in bookings:
            booking.status = "cancelled"
            booking.payment_status = "expired"
            booking.cancelled_at = now
            expired_info.append((booking.id, booking.user_id, booking.date, booking.start_time))

        await session.commit()

    for booking_id, user_id, date, start_time in expired_info:
        await _notify_booking_expired(booking_id, user_id, date, start_time)

    return len(expired_info)


def _is_booking_currently_active(booking: Booking, now: datetime) -> bool:
    """An active-status row still counts as busy, except an unpaid reservation
    whose hold has already expired (release_expired_bookings just hasn't run yet)."""
    if booking.status == "reserved" and booking.payment_status == "pending":
        if booking.reserved_until and booking.reserved_until < now:
            return False
    return True


async def get_active_booking_ranges_for_psychologist(psychologist_id: int) -> list[tuple[str, int, int]]:
    """Real busy time ranges - (date, start_minutes, end_minutes) - for every
    currently-active booking on this psychologist: paid/confirmed bookings,
    plus an unpaid reservation whose hold hasn't expired yet. Unlike
    get_reserved_slots_for_psychologist below (which only flags an EXACT
    (date, start_time) match, historically used to greyscale a fixed slot
    grid), this returns each booking's actual [start, start+duration) window
    so a caller can do real overlap math against a candidate of any
    duration - see schedule.compute_available_start_times, which is what
    the client-facing duration-first booking flow uses."""
    await release_expired_bookings()

    now = utcnow()

    async with async_session() as session:
        result = await session.execute(
            select(Booking).where(
                Booking.psychologist_id == psychologist_id,
                Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                Booking.payment_status.in_(ACTIVE_PAYMENT_STATUSES),
            )
        )

        bookings = result.scalars().all()

        ranges = []

        for booking in bookings:
            if not _is_booking_currently_active(booking, now):
                continue
            start_minutes = time_to_minutes(booking.start_time)
            ranges.append((booking.date, start_minutes, start_minutes + (booking.duration or 0)))

        return ranges


async def get_reserved_slots_for_psychologist(psychologist_id: int) -> set[tuple[str, str]]:
    """Exact (date, start_time) pairs currently occupied - used to grey out
    generated candidate start times that match an existing booking exactly.
    Real overlap protection (different start times whose duration windows
    still collide) happens in create_booking_from_generated_slot via
    _find_overlapping_booking, which is what actually guards the DB."""
    await release_expired_bookings()

    now = utcnow()

    async with async_session() as session:
        result = await session.execute(
            select(Booking).where(
                Booking.psychologist_id == psychologist_id,
                Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                Booking.payment_status.in_(ACTIVE_PAYMENT_STATUSES),
            )
        )

        bookings = result.scalars().all()

        reserved_slots = set()

        for booking in bookings:
            if not _is_booking_currently_active(booking, now):
                continue
            reserved_slots.add((booking.date, booking.start_time))

        return reserved_slots


async def _find_overlapping_booking(
    session,
    psychologist_id: int,
    candidate_start: datetime,
    candidate_end: datetime,
) -> Booking | None:
    now = utcnow()

    result = await session.execute(
        select(Booking).where(
            Booking.psychologist_id == psychologist_id,
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            Booking.payment_status.in_(ACTIVE_PAYMENT_STATUSES),
        )
    )

    for existing in result.scalars().all():
        if not _is_booking_currently_active(existing, now):
            continue

        try:
            existing_start, existing_end = booking_time_range(existing)
        except ValueError:
            continue

        if _ranges_overlap(candidate_start, candidate_end, existing_start, existing_end):
            return existing

    return None


async def create_booking_from_generated_slot(
    telegram_id: int,
    username: str | None,
    full_name: str | None,
    phone: str | None,
    email: str | None,
    psychologist_id: int,
    slot_data: dict | None = None,
    price: int | None = None,
    age_group: str | None = None,
    client_answers: dict | None = None,
    client_comment: str | None = None,
    date: str | None = None,
    start_time: str | None = None,
    duration: int | None = None,
) -> Booking | None:
    """
    Универсальное создание записи.

    Concurrency/overlap safety: the whole check-then-insert happens inside
    one transaction that takes a row lock on the psychologist (SELECT ...
    FOR UPDATE), so two simultaneous requests for the same psychologist are
    fully serialized - the second one always sees the first one's booking
    before it decides whether the time is free. The overlap check compares
    actual [start, end) time ranges (not just exact start_time equality),
    so a 90-minute booking at 10:00 correctly blocks a 30-minute booking
    starting at 10:30, even though their start_time strings differ.

    Поддерживает два формата:
    1. Новый:
       slot_data={"date": "...", "time": "...", "duration": ...}

    2. Старый:
       date="...", start_time="...", duration=...
    """

    await release_expired_bookings()

    # do this before opening the locking transaction - user upsert doesn't
    # need to be serialized per-psychologist
    user = await get_or_create_user(
        telegram_id=telegram_id,
        username=username,
        full_name=full_name,
        age_group=age_group,
        phone=phone,
        email=email,
    )

    slot_data = slot_data or {}

    final_date = date or slot_data.get("date")
    final_start_time = (
        start_time
        or slot_data.get("time")
        or slot_data.get("start_time")
    )
    final_duration = int(
        duration
        or slot_data.get("duration")
        or slot_data.get("consultation_duration")
        or 60
    )

    if not final_date or not final_start_time:
        print("Booking create failed: date or start_time is empty")
        return None

    try:
        candidate_start = parse_booking_start(final_date, final_start_time)
    except ValueError:
        print(f"Booking create failed: invalid date/time {final_date} {final_start_time}")
        return None

    candidate_end = candidate_start + timedelta(minutes=final_duration)

    if not age_group and client_answers:
        age_group = client_answers.get("age_group")

    reserved_until = utcnow() + timedelta(minutes=RESERVATION_MINUTES)

    async with async_session() as session:
        # SELECT ... FOR UPDATE on the psychologist row serializes concurrent
        # booking attempts for the SAME psychologist. Two clients racing for
        # different psychologists don't block each other.
        psychologist = (
            await session.execute(
                select(Psychologist).where(Psychologist.id == psychologist_id).with_for_update()
            )
        ).scalar_one_or_none()

        if not psychologist:
            print("Booking create failed: psychologist not found")
            return None

        final_price = price if price is not None else get_duration_price(psychologist, final_duration)

        if final_price is None or final_price < 0:
            print(f"Booking create failed: no price set for duration {final_duration}")
            return None

        overlapping = await _find_overlapping_booking(session, psychologist_id, candidate_start, candidate_end)

        if overlapping is not None:
            print(
                f"Booking create failed: overlaps existing booking #{overlapping.id} "
                f"({overlapping.date} {overlapping.start_time}, {overlapping.duration} min)"
            )
            return None

        booking = Booking(
            user_id=user.id,
            psychologist_id=psychologist_id,
            date=final_date,
            start_time=final_start_time,
            status="reserved",
            payment_status="pending",
            price=int(final_price),
            duration=final_duration,
            meeting_link=None,
            reserved_until=reserved_until,
            client_answers=client_answers,
            client_comment=client_comment,
        )

        session.add(booking)

        try:
            await session.commit()
        except IntegrityError as error:
            # Defense-in-depth backstop: uq_active_booking_slot (see
            # migrations/versions/0002_active_booking_slot_unique.py) - the
            # row lock above + the overlap recheck already prevent this in
            # the normal case, so reaching here means either a genuinely
            # exotic race slipped past both, or the DB constraint alone
            # caught something the in-process check missed. Either way,
            # this is exactly the same outcome as the ordinary "overlap
            # found" rejection above - not a crash.
            await session.rollback()
            print(
                f"Booking create failed: rejected by uq_active_booking_slot "
                f"(psychologist {psychologist_id}, {final_date} {final_start_time}): {error}"
            )
            return None

        await session.refresh(booking)

        return booking


async def try_auto_create_meeting_link(booking_id: int) -> None:
    """Called once a booking is actually confirmed - a real payment
    succeeded, or the free 15-minute slot was granted - to make sure a
    meeting link exists without the psychologist having to add one
    manually. Uses services/jitsi.py: a free meet.jit.si link that needs
    no API call, no auth, and no signup (this replaces the earlier Yandex
    Telemost integration, which depended on an OAuth token that never
    materialized and could fail the way any real API call can - Jitsi
    link generation is local and can't fail). Never overwrites a link the
    psychologist already set manually - that manual link always wins.
    Still wrapped defensively: never raises and never blocks the caller's
    own flow."""
    try:
        async with async_session() as session:
            booking = await session.get(Booking, booking_id)

            if not booking:
                return

            link = await get_or_create_meeting_link(booking.meeting_link, booking_id)

            if link and link != booking.meeting_link:
                booking.meeting_link = link
                await session.commit()
    except Exception as error:
        print(f"Auto meeting link creation failed for booking {booking_id}: {error}")


async def cancel_user_booking(telegram_id: int, booking_id: int) -> bool:
    async with async_session() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            return False

        booking = await session.get(Booking, booking_id)

        if not booking:
            return False

        if booking.user_id != user.id:
            return False

        if booking.status in ["paid", "confirmed"]:
            return False

        booking.status = "cancelled"
        booking.payment_status = "cancelled"
        booking.cancelled_at = utcnow()

        await session.commit()

        return True


async def get_user_bookings(telegram_id: int) -> list[Booking]:
    await release_expired_bookings()

    async with async_session() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            return []

        result = await session.execute(
            select(Booking)
            .where(Booking.user_id == user.id)
            .order_by(Booking.created_at.desc())
        )

        return list(result.scalars().all())


async def get_psychologist_bookings(telegram_id: int) -> list[Booking]:
    await release_expired_bookings()

    async with async_session() as session:
        psychologist_result = await session.execute(
            select(Psychologist).where(Psychologist.telegram_id == telegram_id)
        )
        psychologist = psychologist_result.scalar_one_or_none()

        if not psychologist:
            return []

        result = await session.execute(
            select(Booking)
            .where(Booking.psychologist_id == psychologist.id)
            .order_by(Booking.date, Booking.start_time)
        )

        return list(result.scalars().all())
