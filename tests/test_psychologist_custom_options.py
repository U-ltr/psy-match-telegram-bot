"""Psychologist-authored "add your own option" for specializations /
help_topics / styles: app/handlers/psychologist.py.

A psychologist is not limited to the fixed catalog (SPECIALIZATION_OPTIONS
/ HELP_TOPIC_OPTIONS / STYLE_OPTIONS) - each multi-select screen also has
an "➕ Свой вариант" button that lets them type free text. It's stored
inline in the same JSON list, marked with
app.services.answer_formatting.CUSTOM_OPTION_PREFIX, so every existing
display path (the psychologist's own "Анкета", the client-facing card, the
admin card - all of them already route through format_code_list) shows it
automatically without any extra wiring.
"""
from types import SimpleNamespace

import pytest

from app.handlers.psychologist import (
    PsychologistCabinetV4States,
    psych4_options_keyboard,
    psych4_add_custom_option_start_handler,
    psych4_custom_option_value_handler,
    psych4_remove_custom_option_handler,
    psych4_format_profile_text,
)
from app.keyboards.psychologist import SPECIALIZATION_OPTIONS
from app.models.psychologist import Psychologist
from app.services.answer_formatting import CUSTOM_OPTION_PREFIX


def make_psychologist(**overrides) -> Psychologist:
    defaults = dict(
        telegram_id=901000111,
        name="Тестовый Психолог",
        gender=None,
        photo_file_id=None,
        description="",
        education="",
        experience_years=0,
        durations=[{"minutes": 60, "price": 4000}],
        specializations=[],
        help_topics=[],
        styles=[],
        therapy_experience_fit=[],
        is_active=True,
    )
    defaults.update(overrides)
    return Psychologist(**defaults)


# ---- pure keyboard-shape checks (no DB) ---------------------------------

def test_options_keyboard_always_offers_an_add_your_own_button():
    markup = psych4_options_keyboard("specialization", SPECIALIZATION_OPTIONS, [])
    all_callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "psych4:add_custom_specialization" in all_callbacks


def test_options_keyboard_renders_a_saved_custom_value_as_its_own_row():
    selected = ["family_therapist", f"{CUSTOM_OPTION_PREFIX}Работа с фобиями"]
    markup = psych4_options_keyboard("specialization", SPECIALIZATION_OPTIONS, selected)

    all_texts = [button.text for row in markup.inline_keyboard for button in row]
    all_callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]

    assert any("Работа с фобиями" in text for text in all_texts)
    assert "psych4:remove_custom_specialization:0" in all_callbacks
    # The raw internal prefix itself must never reach the UI text.
    assert not any(CUSTOM_OPTION_PREFIX in text for text in all_texts)


# ---- the actual add/remove handlers, end to end via the db fixture ------

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
    def __init__(self):
        self._data = {}
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


@pytest.mark.asyncio
async def test_adding_a_custom_specialization_persists_and_displays_it(db):
    async with db() as session:
        psychologist = make_psychologist(telegram_id=901000111)
        session.add(psychologist)
        await session.commit()

    # Step 1: tap "➕ Свой вариант" under specializations.
    start_callback = FakeCallback(901000111, "psych4:add_custom_specialization")
    state = FakeState()
    await psych4_add_custom_option_start_handler(start_callback, state)

    assert state.state == PsychologistCabinetV4States.waiting_custom_option_value
    assert (await state.get_data())["custom_option_prefix"] == "specialization"

    # Step 2: type the free-text value.
    value_message = FakeMessage(text="Работа с фобиями")
    await psych4_custom_option_value_handler(value_message, state)

    # State is cleared after saving, and the confirmation shows the new
    # value already formatted (no raw "custom:" prefix anywhere).
    assert state.state is None
    assert any("Добавлено" in text for text in value_message.sent)

    # The change is immediately visible on the psychologist's own card too
    # (format_code_list is the single formatter every card goes through).
    from app.services.psychologist_profile import get_psychologist_by_telegram_id
    updated = await get_psychologist_by_telegram_id(901000111)
    assert f"{CUSTOM_OPTION_PREFIX}Работа с фобиями" in updated.specializations

    profile_text = psych4_format_profile_text(updated)
    assert "Работа с фобиями" in profile_text
    assert CUSTOM_OPTION_PREFIX not in profile_text


@pytest.mark.asyncio
async def test_removing_a_custom_specialization(db):
    async with db() as session:
        psychologist = make_psychologist(
            telegram_id=901000222,
            specializations=[f"{CUSTOM_OPTION_PREFIX}Работа с фобиями"],
        )
        session.add(psychologist)
        await session.commit()

    remove_callback = FakeCallback(901000222, "psych4:remove_custom_specialization:0")
    await psych4_remove_custom_option_handler(remove_callback)

    from app.services.psychologist_profile import get_psychologist_by_telegram_id
    updated = await get_psychologist_by_telegram_id(901000222)
    assert updated.specializations == []


@pytest.mark.asyncio
async def test_empty_custom_value_is_rejected_without_crashing(db):
    async with db() as session:
        psychologist = make_psychologist(telegram_id=901000333)
        session.add(psychologist)
        await session.commit()

    state = FakeState()
    await state.update_data(custom_option_prefix="specialization")

    message = FakeMessage(text="   ")
    await psych4_custom_option_value_handler(message, state)

    assert any("пуст" in text for text in message.sent)


@pytest.mark.asyncio
async def test_too_long_custom_value_is_rejected_without_crashing(db):
    async with db() as session:
        psychologist = make_psychologist(telegram_id=901000444)
        session.add(psychologist)
        await session.commit()

    state = FakeState()
    await state.update_data(custom_option_prefix="specialization")

    message = FakeMessage(text="x" * 101)
    await psych4_custom_option_value_handler(message, state)

    assert any("Слишком длинно" in text for text in message.sent)

    from app.services.psychologist_profile import get_psychologist_by_telegram_id
    updated = await get_psychologist_by_telegram_id(901000444)
    assert updated.specializations == []
