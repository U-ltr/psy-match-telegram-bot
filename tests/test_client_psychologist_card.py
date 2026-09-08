"""Client-facing psychologist card rendering: app/handlers/client.py.

Regression coverage for a real bug found in manual Telegram testing: a
psychologist's raw internal specialization code (e.g. "family_therapist")
showed up as-is on the card instead of its Russian label. Root cause was
duplicated, drifted label mappings - show_psychologist_card had its own
local dict (mostly right, but a maintenance hazard), and a second,
separate card renderer used by the "Подобрать психолога" / get-matched
flow (show_current_psychologist, since removed) used a module constant
called SPECIALIZATION_LABELS that was actually a copy of the HELP_TOPIC
codes, not specialization codes at all - so every real specialization key
missed it and leaked to the client unchanged.

That second renderer is gone now: the get-matched flow (show_match_handler)
was unified onto this same show_psychologist_card, the same
matched_psychologists/current_psychologist_index state the nearest-slot
and name-search flows already used, and the same format_code_list +
app.keyboards.psychologist option dicts the psychologist's own cabinet
uses to edit these fields - one renderer, one card shape, no more risk of
a second copy drifting (which is also what used to leave that flow's card
without a photo and without the help_topics/styles lines - see
tests/test_client_matching_flow_state.py for that regression).
"""
from types import SimpleNamespace

import pytest

from app.handlers.client import show_psychologist_card


def make_psychologist_dict(**overrides) -> dict:
    defaults = dict(
        id=1,
        name="Мария Орлова",
        specializations=["family_therapist"],
        help_topics=["family", "relationships", "crisis"],
        experience_years=7,
        education="МГУ",
        min_price=4000,
        durations=[{"minutes": 60, "price": 4000}],
        description="Работаю с семейными парами.",
        photo_file_id=None,
        slots=[],
    )
    defaults.update(overrides)
    return defaults


class FakeMessage:
    def __init__(self):
        self.answered = []
        self.edited = []
        self.deleted = False

    async def answer(self, text, reply_markup=None, **kwargs):
        self.answered.append(text)

    async def answer_photo(self, photo, caption=None, reply_markup=None, **kwargs):
        self.answered.append(caption or "")

    async def edit_text(self, text, reply_markup=None, **kwargs):
        self.edited.append(text)

    async def delete(self):
        self.deleted = True


class FakeState:
    def __init__(self, data=None):
        self._data = data or {}

    async def get_data(self):
        return self._data

    async def update_data(self, **kwargs):
        self._data.update(kwargs)

    async def clear(self):
        self._data = {}

    async def set_state(self, state):
        pass


@pytest.mark.asyncio
async def test_show_psychologist_card_renders_human_readable_specialization():
    message = FakeMessage()
    state = FakeState()
    psychologist = make_psychologist_dict(specializations=["family_therapist"])

    await show_psychologist_card(message, state, psychologist, index=0, total=1)

    full_text = "\n".join(message.answered)
    assert "family_therapist" not in full_text
    assert "Семейный психолог / системный терапевт" in full_text


@pytest.mark.asyncio
async def test_show_psychologist_card_renders_human_readable_help_topics():
    message = FakeMessage()
    state = FakeState()
    psychologist = make_psychologist_dict(help_topics=["family", "relationships", "crisis"])

    await show_psychologist_card(message, state, psychologist, index=0, total=1)

    full_text = "\n".join(message.answered)
    for raw_code in ("family", "relationships", "crisis"):
        assert raw_code not in full_text
    assert "Семейные вопросы" in full_text
    assert "Кризисы" in full_text


