"""Psychologist cabinet profile card ("Анкета"): app/handlers/psychologist.py.

Regression coverage for two real bugs found in manual Telegram testing:

1. Opening "Анкета" crashed with NameError: name 'format_list' is not
   defined - psych4_format_profile_text called a function that was never
   defined or imported anywhere in the codebase. This made the whole
   profile view/edit flow (which was otherwise already fully built - see
   psych4_edit_profile_keyboard and the psych4_edit_* handlers below it)
   look completely broken from the outside, even though only the text
   formatting call was wrong.

2. Multiple psychologist-card renderers (this file's
   psych4_format_profile_text, and separately app/handlers/client.py's
   card renderers) each had their own, sometimes wrong or incomplete,
   copy of the code -> Russian label mapping, so a real specialization
   like "family_therapist" rendered as the raw code instead of "Семейный
   психолог / системный терапевт". The fix routes every one of these
   through the single centralized app.services.answer_formatting.
   format_code_list, using the same option dicts
   (app.keyboards.psychologist.SPECIALIZATION_OPTIONS / HELP_TOPIC_OPTIONS
   / STYLE_OPTIONS) the psychologist's own edit UI already used - see that
   module's docstring.
"""
from types import SimpleNamespace

import pytest

from app.handlers.psychologist import (
    psych4_format_profile_text,
    psych4_profile_handler,
    psych4_edit_profile_keyboard,
)
from app.models.psychologist import Psychologist


def make_full_psychologist(**overrides) -> Psychologist:
    defaults = dict(
        telegram_id=555000111,
        name="Мария Орлова",
        gender="female",
        photo_file_id=None,
        description="Работаю с семейными парами и подростками.",
        education="МГУ, факультет психологии",
        experience_years=7,
        durations=[{"minutes": 60, "price": 4000}],
        specializations=["family_therapist"],
        help_topics=["family", "relationships", "crisis"],
        styles=["supportive"],
        therapy_experience_fit=["none", "positive"],
        is_active=True,
    )
    defaults.update(overrides)
    return Psychologist(**defaults)


# ---- the exact function that used to raise NameError -------------------

def test_format_profile_text_does_not_raise_nameerror():
    # Before the fix, this line alone raised:
    # NameError: name 'format_list' is not defined
    psychologist = make_full_psychologist()
    text = psych4_format_profile_text(psychologist)
    assert isinstance(text, str)


def test_format_profile_text_shows_human_readable_specialization_not_raw_code():
    psychologist = make_full_psychologist(specializations=["family_therapist"])
    text = psych4_format_profile_text(psychologist)

    assert "family_therapist" not in text
    assert "Семейный психолог / системный терапевт" in text


def test_format_profile_text_shows_human_readable_help_topics_and_styles():
    psychologist = make_full_psychologist(
        help_topics=["family", "relationships", "crisis"],
        styles=["supportive"],
    )
    text = psych4_format_profile_text(psychologist)

    for raw_code in ("family", "relationships", "crisis", "supportive"):
        assert raw_code not in text

    assert "Семейные вопросы" in text
    assert "Отношения" in text
    assert "Кризисы" in text
    assert "Поддерживающий" in text


def test_format_profile_text_handles_empty_lists_without_crashing():
    psychologist = make_full_psychologist(
        specializations=[], help_topics=[], styles=[],
    )
    text = psych4_format_profile_text(psychologist)
    assert "не указано" in text


# ---- the actual handler that crashed in production ----------------------

class FakeMessage:
    def __init__(self):
        self.sent = []

    async def answer(self, text, reply_markup=None):
        self.sent.append(text)

    async def answer_photo(self, photo, caption=None):
        self.sent.append(caption or "")


class FakeCallback:
    def __init__(self, telegram_id: int):
        self.from_user = SimpleNamespace(id=telegram_id)
        self.message = FakeMessage()

    async def answer(self):
        pass


class FakeState:
    async def clear(self):
        pass


@pytest.mark.asyncio
async def test_profile_handler_renders_card_without_crashing_and_hides_raw_codes(db):
    async with db() as session:
        psychologist = make_full_psychologist(telegram_id=777000111)
        session.add(psychologist)
        await session.commit()

    callback = FakeCallback(telegram_id=777000111)
    state = FakeState()

    # This is the exact call path that raised NameError in production
    # (Telegram button "Анкета" -> psych4:profile callback).
    await psych4_profile_handler(callback, state)

    full_text = "\n".join(callback.message.sent)
    assert "family_therapist" not in full_text
    assert "Семейный психолог" in full_text


def test_edit_profile_keyboard_never_offers_system_fields():
    # id / telegram_id / created_at / is_active are never editable by the
    # psychologist themselves - only the public-card fields are.
    markup = psych4_edit_profile_keyboard()
    all_callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]

    forbidden_fragments = ("edit_field:id", "telegram_id", "created_at", "is_active")
    for callback_data in all_callbacks:
        for forbidden in forbidden_fragments:
            assert forbidden not in callback_data
