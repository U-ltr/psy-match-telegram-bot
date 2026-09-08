from sqlalchemy import select

from app.database import async_session
from app.models.psychologist import Psychologist
from app.services.bookings import get_active_booking_ranges_for_psychologist
from app.services.profile_validation import is_psychologist_profile_ready
from app.services.pricing import normalize_durations, get_priced_durations, min_price, get_duration_price
from app.services.schedule import (
    get_working_intervals_by_psychologist_id,
    get_busy_intervals_by_psychologist_id,
    compute_available_start_times,
    time_to_minutes,
)


async def get_active_psychologists_with_slots() -> list[dict]:
    """The client-facing psychologist listing/card data - "slots" here is
    used both to decide whether a psychologist shows up at all (any active
    psychologist with zero future slots for ANY priced duration is filtered
    out downstream by every caller) and to render the "nearest slots"
    preview on the card.

    slots are computed per-duration with compute_available_start_times -
    the same real overlap-aware engine used once a client has actually
    picked a duration (see get_available_start_times_for_duration below) -
    across EVERY duration the psychologist has priced, not just one. This
    used to generate slots for a single fixed duration taken from each
    WorkingInterval's own consultation_duration column, which meant a
    psychologist's preview (and their very visibility in every listing)
    silently depended on whichever one duration happened to be stored on
    their intervals - e.g. a psychologist priced at 30/60/90 minutes but
    with consultation_duration=50 on their intervals showed zero slots and
    was invisible, and a psychologist priced at 30/50/60/90 only ever
    showed 50-minute slots in previews even though clients could book any
    of the four. consultation_duration is no longer read here at all.
    """
    async with async_session() as session:
        result = await session.execute(
            select(Psychologist).where(Psychologist.is_active == True)
        )
        psychologists = result.scalars().all()

        data = []

        for psychologist in psychologists:
            working_intervals = await get_working_intervals_by_psychologist_id(psychologist.id)
            busy_intervals = await get_busy_intervals_by_psychologist_id(psychologist.id)
            active_ranges = await get_active_booking_ranges_for_psychologist(psychologist.id)

            busy_ranges_by_date: dict[str, list[tuple[int, int]]] = {}

            for busy in busy_intervals:
                busy_ranges_by_date.setdefault(busy.date, []).append(
                    (time_to_minutes(busy.start_time), time_to_minutes(busy.end_time))
                )

            for date, start_minutes, end_minutes in active_ranges:
                busy_ranges_by_date.setdefault(date, []).append((start_minutes, end_minutes))

            slots = []
            for item in get_priced_durations(psychologist):
                duration = item["minutes"]
                price = item["price"]

                for candidate in compute_available_start_times(working_intervals, duration, busy_ranges_by_date):
                    candidate = dict(candidate)
                    candidate["price"] = price
                    slots.append(candidate)

            slots.sort(key=lambda slot: (slot["date"], slot["time"]))

            data.append(
                {
                    "id": psychologist.id,
                "photo_file_id": psychologist.photo_file_id,
                    "name": psychologist.name,
                    "gender": psychologist.gender,
                    "photo": psychologist.photo_file_id,
                    "specializations": psychologist.specializations or [],
                    "help_topics": psychologist.help_topics or [],
                    "styles": psychologist.styles or [],
                    "therapy_experience_fit": psychologist.therapy_experience_fit or [],
                    "experience_years": psychologist.experience_years,
                    "education": psychologist.education,
                    "description": psychologist.description,
                    "durations": normalize_durations(psychologist.durations),
                    "min_price": min_price(psychologist),
                    "slots": slots,
                }
            )

        return data


async def get_psychologist_by_id_from_db(psychologist_id: int) -> dict | None:
    psychologists = await get_active_psychologists_with_slots()

    for psychologist in psychologists:
        if psychologist["id"] == psychologist_id:
            return psychologist

    return None


async def get_priced_durations_for_psychologist(psychologist_id: int) -> list[dict]:
    """Every duration this psychologist has actually priced (price > 0),
    normalized and sorted by minutes - the exact list the client should be
    offered to choose from before picking a time. See
    get_available_start_times_for_duration for the next step."""
    async with async_session() as session:
        psychologist = await session.get(Psychologist, psychologist_id)

        if not psychologist:
            return []

        return get_priced_durations(psychologist)


async def get_available_start_times_for_duration(psychologist_id: int, duration: int) -> list[dict]:
    """Real per-duration availability: called once the client has picked a
    specific duration, so every offered start time is guaranteed bookable
    for that exact length (accounts for the working interval's own
    boundaries, manual busy blocks, and every currently-active booking or
    unexpired reservation for this psychologist - see
    compute_available_start_times and get_active_booking_ranges_for_psychologist
    for how each piece is computed). This is deliberately separate from the
    `slots` list on get_active_psychologists_with_slots(), which stays a
    fixed-duration preview grid for the psychologist card only."""
    async with async_session() as session:
        psychologist = await session.get(Psychologist, psychologist_id)

        if not psychologist:
            return []

        price = get_duration_price(psychologist, duration)

        if price is None:
            # This psychologist never priced this duration - never offer it.
            return []

    working_intervals = await get_working_intervals_by_psychologist_id(psychologist_id)
    busy_intervals = await get_busy_intervals_by_psychologist_id(psychologist_id)
    active_ranges = await get_active_booking_ranges_for_psychologist(psychologist_id)

    busy_ranges_by_date: dict[str, list[tuple[int, int]]] = {}

    for busy in busy_intervals:
        busy_ranges_by_date.setdefault(busy.date, []).append(
            (time_to_minutes(busy.start_time), time_to_minutes(busy.end_time))
        )

    for date, start_minutes, end_minutes in active_ranges:
        busy_ranges_by_date.setdefault(date, []).append((start_minutes, end_minutes))

    candidates = compute_available_start_times(working_intervals, duration, busy_ranges_by_date)

    slots = []
    for slot in candidates:
        slot = dict(slot)
        slot["price"] = price
        slots.append(slot)

    return slots
