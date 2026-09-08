"""Regression tests for a real production bug reported after manual
testing: a psychologist with a fully completed, correctly priced profile
(e.g. 30/60/90 minutes) was still completely invisible to clients - not in
"Ближайший психолог", nowhere.

Root cause (app/handlers/psychologist.py, psych4_add_interval_end_handler):
every new WorkingInterval was saved with a hardcoded
consultation_duration=50. That field feeds the preview/existence gate in
app.services.psychologists.get_active_psychologists_with_slots(), via
generate_available_slots_from_intervals() + get_duration_price() (an EXACT
minutes match against the psychologist's own priced durations - see
app/services/pricing.py). A psychologist who never priced exactly 50
minutes therefore had every generated preview slot silently dropped,
leaving an empty "slots" list - and get_active_psychologists_with_slots
only ever includes a psychologist in client-facing listings when that list
is non-empty. This had nothing to do with the database itself (the
psychologist row, and its pricing, were saved correctly) - it was a pure
duration-matching bug.

The fix makes new intervals use the psychologist's own shortest priced
duration instead of a hardcoded value, and blocks creating an interval at
all before any duration has been priced (so the same trap can never be hit
again). app/scripts/fix_working_interval_durations.py separately repairs
rows that were already saved with the old hardcoded value.
"""
from types import SimpleNamespace

import pytest

from app.handlers.psychologist import (
    PsychologistCabinetV4States,
    psych4_add_interval_start_handler,
    psych4_add_interval_end_handler,
)
from app.models.psychologist import Psychologist
from app.models.working_interval import WorkingInterval
from app.services.psychologists import get_active_psychologists_with_slots
from app.scripts.fix_working_interval_durations import fix_working_interval_durations


def make_psychologist(**overrides) -> Psychologist:
    defaults = dict(
        telegram_id=902000111,
        name="Пётр Тестовый",
        gender="male",
        photo_file_id=None,
        description="",
        education="",
        experience_years=5,
        durations=[],
        specializations=[],
        help_topics=[],
        styles=[],
        therapy_experience_fit=[],
        is_active=True,
    )
    defaults.update(overrides)
    return Psychologist(**defaults)


class FakeMessage:
    def __init__(self, text: str | None = None):
        self.text = text
        self.sent = []

    async def answer(self, text, reply_markup=None, **kwargs):
        self.sent.append(text)


class FakeCallback:
    def __init__(self, telegram_id: int, data: str):
        self.from_user = SimpleNamespace(id=telegram_id)
        self.data = data
        self.message = FakeMessage()

    async def answer(self):
        pass


class FakeState:
    def __init__(self, data=None):
        self._data = data or {}
        self.state = None

    async def get_data(self):
        return self._data

    async def update_data(self, **kwargs):
        self._data.update(kwargs)

    async def set_state(self, state):
        self.state = state

    async def clear(self):
        self._data = {}
        self.state = None


# ---- guard: can't start adding an interval before any duration is priced

@pytest.mark.asyncio
async def test_add_interval_blocked_when_nothing_priced_yet(db):
    async with db() as session:
        session.add(make_psychologist(telegram_id=902000111, durations=[]))
        await session.commit()

    callback = FakeCallback(902000111, "psych4:add_interval")
    state = FakeState()
    await psych4_add_interval_start_handler(callback, state)

    assert state.state is None
    assert any("длительност" in text.lower() for text in callback.message.sent)


@pytest.mark.asyncio
async def test_add_interval_allowed_once_a_duration_is_priced(db):
    async with db() as session:
        session.add(make_psychologist(
            telegram_id=902000222,
            durations=[{"minutes": 60, "price": 4000}],
        ))
        await session.commit()

    callback = FakeCallback(902000222, "psych4:add_interval")
    state = FakeState()
    await psych4_add_interval_start_handler(callback, state)

    assert state.state == PsychologistCabinetV4States.waiting_schedule_date


# ---- the actual hardcoded-50 bug -----------------------------------------

@pytest.mark.asyncio
async def test_new_interval_uses_psychologists_own_shortest_priced_duration_not_50(db):
    """Пётр's exact real-world shape: 30/60/90 priced, none of them 50."""
    async with db() as session:
        session.add(make_psychologist(
            telegram_id=902000333,
            durations=[
                {"minutes": 30, "price": 900},
                {"minutes": 60, "price": 2000},
                {"minutes": 90, "price": 5000},
            ],
        ))
        await session.commit()

    state = FakeState(data={"schedule_date": "2026-10-01", "schedule_start": "11:00"})
    message = FakeMessage(text="16:00")
    await psych4_add_interval_end_handler(message, state)

    assert state.state is None
    assert any("добавлен" in text.lower() for text in message.sent)

    async with db() as session:
        from sqlalchemy import select
        result = await session.execute(select(WorkingInterval))
        interval = result.scalars().one()

    # Before the fix this was unconditionally 50 - a value this
    # psychologist never priced, which silently hid every slot.
    assert interval.consultation_duration == 30


@pytest.mark.asyncio
async def test_newly_added_interval_makes_the_psychologist_visible_to_clients(db):
    """End-to-end regression for the exact reported symptom: a fully
    priced psychologist not showing up anywhere in the client-facing
    listing after adding a free interval."""
    async with db() as session:
        session.add(make_psychologist(
            telegram_id=902000444,
            name="Николай Петров",
            durations=[
                {"minutes": 30, "price": 900},
                {"minutes": 60, "price": 2000},
                {"minutes": 90, "price": 5000},
            ],
        ))
        await session.commit()

    state = FakeState(data={"schedule_date": "2026-10-01", "schedule_start": "11:00"})
    message = FakeMessage(text="16:00")
    await psych4_add_interval_end_handler(message, state)

    listing = await get_active_psychologists_with_slots()
    entry = next(p for p in listing if p["name"] == "Николай Петров")

    # Before the fix, `slots` was always empty here because the hardcoded
    # 50-minute preview duration never matched any of this psychologist's
    # real prices - which is exactly why he never appeared in "Ближайший
    # психолог" despite a complete, correctly priced profile.
    assert entry["slots"], "psychologist has a priced interval but no visible slots"


# ---- data repair for rows already saved with the old hardcoded value ----

@pytest.mark.asyncio
async def test_repair_script_fixes_mismatched_intervals_and_leaves_good_ones(db):
    async with db() as session:
        broken = make_psychologist(
            telegram_id=902000555,
            name="Психолог С Плохим Интервалом",
            durations=[
                {"minutes": 30, "price": 900},
                {"minutes": 90, "price": 5000},
            ],
        )
        fine = make_psychologist(
            telegram_id=902000666,
            name="Психолог С Хорошим Интервалом",
            durations=[{"minutes": 50, "price": 3000}],
        )
        unpriced = make_psychologist(
            telegram_id=902000777,
            name="Психолог Без Цены",
            durations=[],
        )
        session.add_all([broken, fine, unpriced])
        await session.commit()
        await session.refresh(broken)
        await session.refresh(fine)
        await session.refresh(unpriced)

        session.add_all([
            WorkingInterval(
                psychologist_id=broken.id, date="2026-10-01",
                start_time="11:00", end_time="16:00",
                consultation_duration=50, break_minutes=10,
            ),
            WorkingInterval(
                psychologist_id=fine.id, date="2026-10-01",
                start_time="11:00", end_time="16:00",
                consultation_duration=50, break_minutes=10,
            ),
            WorkingInterval(
                psychologist_id=unpriced.id, date="2026-10-01",
                start_time="11:00", end_time="16:00",
                consultation_duration=50, break_minutes=10,
            ),
        ])
        await session.commit()

    fixed_count = await fix_working_interval_durations()
    assert fixed_count == 1

    async with db() as session:
        from sqlalchemy import select
        intervals = {
            row.psychologist_id: row.consultation_duration
            for row in (await session.execute(select(WorkingInterval))).scalars().all()
        }

    assert intervals[broken.id] == 30  # repaired to the shortest priced duration
    assert intervals[fine.id] == 50    # already matched a real price - untouched
    assert intervals[unpriced.id] == 50  # nothing priced yet - left alone

    # Running it again is a no-op.
    assert await fix_working_interval_durations() == 0
