from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select

from app.database import async_session
from app.models.psychologist import Psychologist
from app.models.working_interval import WorkingInterval
from app.models.busy_interval import BusyInterval


def time_to_minutes(value: str) -> int:
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def minutes_to_time(value: int) -> str:
    hours = value // 60
    minutes = value % 60
    return f"{hours:02d}:{minutes:02d}"


def is_valid_time(value: str) -> bool:
    if len(value) != 5 or value[2] != ":":
        return False

    hours, minutes = value.split(":")

    if not hours.isdigit() or not minutes.isdigit():
        return False

    hours_int = int(hours)
    minutes_int = int(minutes)

    return 0 <= hours_int <= 23 and 0 <= minutes_int <= 59


def is_valid_date(value: str) -> bool:
    return len(value) == 10 and value[4] == "-" and value[7] == "-"


def intervals_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return start_a < end_b and start_b < end_a


# The minimum time-grid step used to step through a working interval when
# computing candidate start times for a client-chosen duration (see
# compute_available_start_times below). No such step was previously named
# anywhere in the project, so this is the one place it is now defined -
# 5 minutes is fine-grained enough that it never hides a real gap between
# bookings (the shortest offered duration is 15 minutes) while keeping the
# generated candidate list small. Purely a scheduling-grid default, not a
# business figure - safe to tune here if the customer wants a coarser grid.
SLOT_STEP_MINUTES = 5


def is_future_moscow_slot(date_value: str, time_value: str) -> bool:
    slot_dt = datetime.strptime(f"{date_value} {time_value}", "%Y-%m-%d %H:%M")
    now_moscow = datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None)

    return slot_dt > now_moscow

async def get_psychologist_by_telegram_id(telegram_id: int) -> Psychologist | None:
    async with async_session() as session:
        result = await session.execute(
            select(Psychologist).where(Psychologist.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


async def add_working_interval(
    telegram_id: int,
    date: str,
    start_time: str,
    end_time: str,
    consultation_duration: int,
    break_minutes: int,
) -> WorkingInterval | None:
    async with async_session() as session:
        result = await session.execute(
            select(Psychologist).where(Psychologist.telegram_id == telegram_id)
        )
        psychologist = result.scalar_one_or_none()

        if not psychologist:
            return None

        interval = WorkingInterval(
            psychologist_id=psychologist.id,
            date=date,
            start_time=start_time,
            end_time=end_time,
            consultation_duration=consultation_duration,
            break_minutes=break_minutes,
        )

        session.add(interval)
        await session.commit()
        await session.refresh(interval)

        return interval


async def add_busy_interval(
    telegram_id: int,
    date: str,
    start_time: str,
    end_time: str,
    reason: str | None = None,
) -> BusyInterval | None:
    async with async_session() as session:
        result = await session.execute(
            select(Psychologist).where(Psychologist.telegram_id == telegram_id)
        )
        psychologist = result.scalar_one_or_none()

        if not psychologist:
            return None

        interval = BusyInterval(
            psychologist_id=psychologist.id,
            date=date,
            start_time=start_time,
            end_time=end_time,
            reason=reason,
        )

        session.add(interval)
        await session.commit()
        await session.refresh(interval)

        return interval


async def get_working_intervals_by_telegram_id(telegram_id: int) -> list[WorkingInterval]:
    async with async_session() as session:
        psychologist_result = await session.execute(
            select(Psychologist).where(Psychologist.telegram_id == telegram_id)
        )
        psychologist = psychologist_result.scalar_one_or_none()

        if not psychologist:
            return []

        result = await session.execute(
            select(WorkingInterval)
            .where(WorkingInterval.psychologist_id == psychologist.id)
            .order_by(WorkingInterval.date, WorkingInterval.start_time)
        )

        return list(result.scalars().all())


async def get_busy_intervals_by_telegram_id(telegram_id: int) -> list[BusyInterval]:
    async with async_session() as session:
        psychologist_result = await session.execute(
            select(Psychologist).where(Psychologist.telegram_id == telegram_id)
        )
        psychologist = psychologist_result.scalar_one_or_none()

        if not psychologist:
            return []

        result = await session.execute(
            select(BusyInterval)
            .where(BusyInterval.psychologist_id == psychologist.id)
            .order_by(BusyInterval.date, BusyInterval.start_time)
        )

        return list(result.scalars().all())


async def get_working_intervals_by_psychologist_id(psychologist_id: int) -> list[WorkingInterval]:
    async with async_session() as session:
        result = await session.execute(
            select(WorkingInterval)
            .where(WorkingInterval.psychologist_id == psychologist_id)
            .order_by(WorkingInterval.date, WorkingInterval.start_time)
        )

        return list(result.scalars().all())


async def get_busy_intervals_by_psychologist_id(psychologist_id: int) -> list[BusyInterval]:
    async with async_session() as session:
        result = await session.execute(
            select(BusyInterval)
            .where(BusyInterval.psychologist_id == psychologist_id)
            .order_by(BusyInterval.date, BusyInterval.start_time)
        )

        return list(result.scalars().all())


async def delete_working_interval(telegram_id: int, interval_id: int) -> bool:
    async with async_session() as session:
        psychologist_result = await session.execute(
            select(Psychologist).where(Psychologist.telegram_id == telegram_id)
        )
        psychologist = psychologist_result.scalar_one_or_none()

        if not psychologist:
            return False

        interval = await session.get(WorkingInterval, interval_id)

        if not interval or interval.psychologist_id != psychologist.id:
            return False

        await session.delete(interval)
        await session.commit()

        return True


async def delete_busy_interval(telegram_id: int, interval_id: int) -> bool:
    async with async_session() as session:
        psychologist_result = await session.execute(
            select(Psychologist).where(Psychologist.telegram_id == telegram_id)
        )
        psychologist = psychologist_result.scalar_one_or_none()

        if not psychologist:
            return False

        interval = await session.get(BusyInterval, interval_id)

        if not interval or interval.psychologist_id != psychologist.id:
            return False

        await session.delete(interval)
        await session.commit()

        return True


def generate_available_slots_from_intervals(
    working_intervals: list[WorkingInterval],
    busy_intervals: list[BusyInterval],
) -> list[dict]:
    generated_slots = []

    busy_by_date = {}

    for busy in busy_intervals:
        busy_by_date.setdefault(busy.date, []).append(
            {
                "start": time_to_minutes(busy.start_time),
                "end": time_to_minutes(busy.end_time),
            }
        )

    for interval in working_intervals:
        current = time_to_minutes(interval.start_time)
        end = time_to_minutes(interval.end_time)

        duration = interval.consultation_duration
        break_minutes = interval.break_minutes

        busy_items = busy_by_date.get(interval.date, [])

        while current + duration <= end:
            slot_start = current
            slot_end = current + duration

            has_overlap = False
            nearest_busy_end = None

            for busy in busy_items:
                if intervals_overlap(slot_start, slot_end, busy["start"], busy["end"]):
                    has_overlap = True
                    nearest_busy_end = busy["end"]
                    break

            if has_overlap:
                current = nearest_busy_end or current + 5
                continue

            generated_slots.append(
                {
                    "date": interval.date,
                    "time": minutes_to_time(slot_start),
                    "duration": duration,
                    "break_minutes": break_minutes,
                    "source": "working_interval",
                    "working_interval_id": interval.id,
                }
            )

            current = slot_end + break_minutes

    generated_slots = [
        slot for slot in generated_slots
        if is_future_moscow_slot(
            slot.get("date"),
            slot.get("time") or slot.get("start_time"),
        )
    ]

    return generated_slots


def compute_available_start_times(
    working_intervals: list[WorkingInterval],
    duration: int,
    busy_ranges_by_date: dict[str, list[tuple[int, int]]],
    step_minutes: int = SLOT_STEP_MINUTES,
) -> list[dict]:
    """Real, per-duration availability inside a psychologist's working
    intervals - this is what "client picks a duration, system computes
    valid start times" (see the scheduling requirements) actually means in
    code, and it deliberately differs from generate_available_slots_from_intervals
    above in two ways:

    1. The duration comes from the CLIENT (any value >= 1), not from
       WorkingInterval.consultation_duration - a working interval is just
       an availability window ("I'm free 10:00-15:00"), not a promise of
       one fixed session length. This lets a psychologist who has priced
       30/50/60/90-minute sessions actually offer all of them inside the
       same interval, instead of being locked to whatever duration was
       typed in when the interval was created.
    2. Candidates are stepped through the window at SLOT_STEP_MINUTES and
       checked with real [start, end) overlap math against
       busy_ranges_by_date (every currently-busy range for that date - both
       manual BusyInterval blocks and real active bookings/holds, as
       (start_minutes, end_minutes) pairs the caller has already merged).
       There is no forced break between candidates, so back-to-back
       bookings are correctly allowed (a candidate ending exactly when a
       busy range begins, or starting exactly when one ends, is NOT an
       overlap - see intervals_overlap).

    Two working intervals that overlap or sit on the same day simply both
    contribute candidates - duplicates are de-duplicated by (date, time).
    Past times (per Europe/Moscow "now") are filtered out at the end.
    """
    if duration <= 0:
        return []

    candidates = []

    for interval in working_intervals:
        start = time_to_minutes(interval.start_time)
        end = time_to_minutes(interval.end_time)

        if end <= start:
            # Malformed/overnight interval (end_time <= start_time isn't
            # representable within a single `date` in this schema) - never
            # offered, but never crashes either.
            continue

        busy_ranges = busy_ranges_by_date.get(interval.date, [])

        candidate_start = start
        while candidate_start + duration <= end:
            candidate_end = candidate_start + duration

            overlaps = any(
                intervals_overlap(candidate_start, candidate_end, busy_start, busy_end)
                for busy_start, busy_end in busy_ranges
            )

            if not overlaps:
                candidates.append(
                    {
                        "date": interval.date,
                        "time": minutes_to_time(candidate_start),
                        "duration": duration,
                    }
                )

            candidate_start += step_minutes

    seen = set()
    unique_candidates = []
    for slot in candidates:
        key = (slot["date"], slot["time"])
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(slot)

    unique_candidates = [
        slot for slot in unique_candidates
        if is_future_moscow_slot(slot["date"], slot["time"])
    ]

    unique_candidates.sort(key=lambda slot: (slot["date"], slot["time"]))

    return unique_candidates
