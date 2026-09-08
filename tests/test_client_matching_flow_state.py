"""Regression coverage for two real bugs reported after manual Telegram
testing of the "Подобрать психолога" (questionnaire-based get-matched)
flow in app/handlers/client.py:

1. show_match_handler used to keep its OWN state shape
   (`ranked_psychologist_ids` + `current_psychologist_index`) and render
   the card with a second, separate, incomplete renderer
   (show_current_psychologist, since removed) instead of the shared
   show_psychologist_card every other matching flow (nearest slot, name
   search) already used - so this flow's card never showed a photo and
   never showed the help_topics/styles lines show_psychologist_card
   already has (see test_client_psychologist_card.py for that half of the
   regression). Every downstream handler bound to the card's own keyboard
   ("Выбрать время" -> choose_slot_handler, "Следующий"/"Предыдущий" ->
   switch_psychologist_handler) only ever understood
   `matched_psychologists`, so tapping "Выбрать время" on a card from THIS
   flow found no matching state, silently refetched from scratch, and
   showed duration/price options for the FIRST active psychologist in the
   whole database - a completely different, wrong psychologist from the
   one on screen. show_match_handler now writes the same
   matched_psychologists/current_psychologist_index state and uses the
   same renderer, so it works like every other matching flow.

2. "Назад" on the duration-choice screen (client:back_to_slot_menu) used
   to call straight back into the function that renders that very same
   duration-choice screen - so tapping it looked like nothing happened,
   and the only way out was "Начать заново". It now returns to the
   psychologist's own card instead.
"""
import pytest


def make_psychologist_dict(**overrides) -> dict:
    defaults = dict(
        id=1,
        name="Анна Смирнова",
        gender="female",
        photo_file_id=None,
        specializations=[],
        help_topics=[],
        styles=[],
        therapy_experience_fit=[],
        experience_years=6,
        education="МГУ",
        min_price=3000,
        durations=[{"minutes": 50, "price": 3000}],
        description="Работает с тревогой.",
        slots=[{"date": "2026-10-01", "time": "10:00", "duration": 50}],
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


class FakeCallback:
    def __init__(self, data: str, message=None):
        self.data = data
        self.message = message or FakeMessage()

    async def answer(self, *args, **kwargs):
        pass


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
async def test_choose_slot_after_show_match_uses_the_ranked_psychologist_not_the_first_in_db(monkeypatch):
    import app.handlers.client as client_module

    anna = make_psychologist_dict(
        id=1, name="Анна Смирнова",
        durations=[{"minutes": 50, "price": 3000}],
        slots=[{"date": "2026-10-01", "time": "10:00", "duration": 50}],
    )
    petrov = make_psychologist_dict(
        id=2, name="Петров Николай Дмитриевич",
        durations=[{"minutes": 30, "price": 900}, {"minutes": 60, "price": 2000}],
        slots=[{"date": "2026-10-02", "time": "11:00", "duration": 30}],
    )

    async def fake_get_active_psychologists_with_slots():
        # Insertion/DB order deliberately puts Anna first - the exact
        # shape of the old bug (falling back to "the first active
        # psychologist in the database").
        return [anna, petrov]

    def fake_get_ranked_psychologists(answers, psychologists):
        # The questionnaire ranked Petrov on top - the point of this test
        # is what happens to that ranking afterwards, not the ranking
        # algorithm itself (covered separately in matching.py's own
        # tests).
        by_id = {p["id"]: p for p in psychologists}
        return [by_id[petrov["id"]], by_id[anna["id"]]]

    monkeypatch.setattr(client_module, "get_active_psychologists_with_slots", fake_get_active_psychologists_with_slots)
    monkeypatch.setattr(client_module, "get_ranked_psychologists", fake_get_ranked_psychologists)

    state = FakeState()

    show_match_callback = FakeCallback(data="client:show_match")
    await client_module.show_match_handler(show_match_callback, state)

    # The card shown is the top-ranked match, Petrov - not Anna.
    assert any("Петров" in text for text in show_match_callback.message.answered)

    data = await state.get_data()
    assert data["matched_psychologists"][data["current_psychologist_index"]]["name"] == "Петров Николай Дмитриевич"

    # Tap "Выбрать время". Before the fix, this flow never wrote
    # matched_psychologists, so this handler found nothing, refetched from
    # scratch and landed on Anna (first in the fake DB order) instead of
    # the psychologist actually on screen.
    choose_slot_callback = FakeCallback(data="client:choose_slot")
    await client_module.choose_slot_handler(choose_slot_callback, state)

    shown = "\n".join(choose_slot_callback.message.answered)
    assert "Петров" in shown
    assert "Смирнова" not in shown


@pytest.mark.asyncio
async def test_back_from_duration_choices_returns_to_the_psychologist_card(monkeypatch):
    import app.handlers.client as client_module

    petrov = make_psychologist_dict(
        id=2, name="Петров Николай Дмитриевич",
        durations=[{"minutes": 30, "price": 900}, {"minutes": 60, "price": 2000}],
        slots=[{"date": "2026-10-02", "time": "11:00", "duration": 30}],
    )

    state = FakeState(data={
        "matched_psychologists": [petrov],
        "current_psychologist_index": 0,
    })

    # Arrive at the duration-choice screen the normal way.
    choose_slot_callback = FakeCallback(data="client:choose_slot")
    await client_module.choose_slot_handler(choose_slot_callback, state)
    assert any("Выберите длительность" in text for text in choose_slot_callback.message.answered)

    # Tap "Назад". Before the fix this re-rendered the exact same duration
    # list (calling straight back into the function above), so it looked
    # like the button did nothing.
    back_callback = FakeCallback(data="client:back_to_slot_menu")
    await client_module.back_to_slot_menu_handler(back_callback, state)

    shown = "\n".join(back_callback.message.answered)
    assert "Петров" in shown
    assert "Выберите длительность" not in shown
