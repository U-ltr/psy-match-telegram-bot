"""One-off data repair: fix WorkingInterval rows saved with a
consultation_duration that doesn't match any of the psychologist's own
priced durations.

Background: app/handlers/psychologist.py's psych4_add_interval_end_handler
used to hardcode consultation_duration=50 for every new interval,
regardless of what the psychologist actually priced. That field feeds the
preview/existence gate in get_active_psychologists_with_slots() (via
generate_available_slots_from_intervals + get_duration_price, an EXACT
match against psychologist.durations) - so any psychologist whose priced
durations did not include exactly 50 minutes (e.g. only 30/60/90) ended up
with an empty "slots" list and was silently invisible in every
client-facing listing, even with a fully completed, correctly priced
profile. The handler itself is now fixed (see git history) to derive the
duration from the psychologist's own pricing, but that only affects
intervals created from now on - this script repairs rows that were already
saved with the old hardcoded value.

For each WorkingInterval whose consultation_duration has no matching price
on its psychologist, this sets it to the psychologist's shortest priced
duration (mirroring the new handler logic exactly). Intervals belonging to
a psychologist with zero priced durations are left untouched (nothing
sensible to repair them to yet - they will start working the moment the
psychologist prices at least one duration and re-runs this script, or just
edits the interval again through the bot).

Safe to run multiple times - it only touches rows that are actually broken
and is a no-op otherwise.

Run with: python -m app.scripts.fix_working_interval_durations
"""
import asyncio

from sqlalchemy import select

from app.database import async_session, check_db_connection
from app.models.psychologist import Psychologist
from app.models.working_interval import WorkingInterval
from app.services.pricing import get_priced_durations


async def fix_working_interval_durations() -> int:
    """Returns the number of WorkingInterval rows that were corrected."""
    fixed = 0

    async with async_session() as session:
        psychologists_result = await session.execute(select(Psychologist))
        psychologists = psychologists_result.scalars().all()

        for psychologist in psychologists:
            priced = get_priced_durations(psychologist)
            if not priced:
                # Nothing priced yet - no sensible duration to repair to.
                continue

            valid_minutes = {item["minutes"] for item in priced}
            shortest = priced[0]["minutes"]

            intervals_result = await session.execute(
                select(WorkingInterval).where(
                    WorkingInterval.psychologist_id == psychologist.id
                )
            )
            intervals = intervals_result.scalars().all()

            for interval in intervals:
                if interval.consultation_duration not in valid_minutes:
                    print(
                        f"Психолог #{psychologist.id} ({psychologist.name}): "
                        f"интервал {interval.date} {interval.start_time}-{interval.end_time} "
                        f"consultation_duration {interval.consultation_duration} -> {shortest}"
                    )
                    interval.consultation_duration = shortest
                    fixed += 1

        if fixed:
            await session.commit()

    return fixed


async def main() -> None:
    # Schema must already exist - run `alembic upgrade head` first. Raises
    # if the database is unreachable or not migrated, same as bot.py/
    # seed_psychologists.py.
    await check_db_connection()

    fixed = await fix_working_interval_durations()

    if fixed:
        print(f"\nИсправлено интервалов: {fixed}")
    else:
        print("Все интервалы уже согласованы с ценами психологов - исправлять нечего.")


if __name__ == "__main__":
    asyncio.run(main())
