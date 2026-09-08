"""app.services.psychologists.get_active_psychologists_with_slots -
regression coverage for a real bug found in manual testing: a
psychologist who priced several durations (e.g. 30/50/60/90 minutes) only
ever showed 50-minute slots in "Ближайшие слоты" / the client-facing
preview, even though a client could actually book any of the four.

Root cause: every WorkingInterval carries exactly one
consultation_duration value (whatever was picked when the interval was
created - see app/handlers/psychologist.py), and the preview used to be
generated purely from that one fixed duration per interval
(generate_available_slots_from_intervals). get_active_psychologists_with_slots
now generates preview slots per PRICED duration (via
compute_available_start_times, the same real per-duration engine used
once a client has actually picked a duration), so every duration the
psychologist actually offers can show up in the preview - not just
whichever one happened to be on the interval row.
"""
import pytest

from app.models.psychologist import Psychologist
from app.models.working_interval import WorkingInterval
from app.models.busy_interval import BusyInterval
from app.services.psychologists import get_active_psychologists_with_slots


def make_psychologist(**overrides) -> Psychologist:
    defaults = dict(
        telegram_id=903000111,
        name="Петров Николай Дмитриевич",
        gender="male",
        photo_file_id=None,
        description="",
        education="PhD",
        experience_years=15,
        durations=[],
        specializations=[],
        help_topics=[],
        styles=[],
        therapy_experience_fit=[],
        is_active=True,
    )
    defaults.update(overrides)
    return Psychologist(**defaults)


@pytest.mark.asyncio
async def test_preview_includes_every_priced_duration_not_just_one(db):
    async with db() as session:
        psychologist = make_psychologist(
            durations=[
                {"minutes": 30, "price": 900},
                {"minutes": 50, "price": 2500},
                {"minutes": 60, "price": 2000},
                {"minutes": 90, "price": 5000},
            ],
        )
        session.add(psychologist)
        await session.commit()
        await session.refresh(psychologist)

        session.add(WorkingInterval(
            psychologist_id=psychologist.id, date="2026-10-01",
            start_time="10:00", end_time="16:00",
            consultation_duration=50, break_minutes=10,
        ))
        await session.commit()

    listing = await get_active_psychologists_with_slots()
    entry = next(p for p in listing if p["name"] == "Петров Николай Дмитриевич")

    durations_shown = {slot["duration"] for slot in entry["slots"]}

    # Before the fix this was always {50} - the interval's own hardcoded
    # consultation_duration - regardless of what was actually priced.
    assert durations_shown == {30, 50, 60, 90}


@pytest.mark.asyncio
async def test_preview_works_even_when_priced_durations_never_include_the_intervals_stored_value(db):
    """The exact shape of the originally reported bug: priced 30/60/90,
    nothing at all matches the interval's stored consultation_duration
    (50, left over from before the interval-creation fix, or just any
    mismatched legacy row)."""
    async with db() as session:
        psychologist = make_psychologist(
            telegram_id=903000222,
            durations=[
                {"minutes": 30, "price": 900},
                {"minutes": 60, "price": 2000},
                {"minutes": 90, "price": 5000},
            ],
        )
        session.add(psychologist)
        await session.commit()
        await session.refresh(psychologist)

        session.add(WorkingInterval(
            psychologist_id=psychologist.id, date="2026-10-01",
            start_time="10:00", end_time="16:00",
            consultation_duration=50, break_minutes=10,
        ))
        await session.commit()

    listing = await get_active_psychologists_with_slots()
    entry = next(p for p in listing if p["id"] == psychologist.id)

    assert entry["slots"], "psychologist has priced, available durations but no visible slots"
    assert {slot["duration"] for slot in entry["slots"]} == {30, 60, 90}


@pytest.mark.asyncio
async def test_busy_interval_still_excludes_overlapping_slots(db):
    async with db() as session:
        psychologist = make_psychologist(
            telegram_id=903000333,
            durations=[{"minutes": 60, "price": 3000}],
        )
        session.add(psychologist)
        await session.commit()
        await session.refresh(psychologist)

        session.add(WorkingInterval(
            psychologist_id=psychologist.id, date="2026-10-01",
            start_time="10:00", end_time="12:00",
            consultation_duration=60, break_minutes=0,
        ))
        # Busy for the whole window - no 60-minute slot should fit.
        session.add(BusyInterval(
            psychologist_id=psychologist.id, date="2026-10-01",
            start_time="10:00", end_time="12:00",
        ))
        await session.commit()

    listing = await get_active_psychologists_with_slots()
    entry = next(p for p in listing if p["id"] == psychologist.id)

    assert entry["slots"] == []
