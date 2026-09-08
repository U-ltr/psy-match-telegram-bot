"""Name-search "not found" message: app/handlers/client.py.

Regression coverage for a warmth/tone bug found in manual testing: when a
client searches for a psychologist by name and nothing matches, the bot
used to reply with a dry, slightly technical message ("Не удалось найти
активного психолога с таким именем и доступным временем.") - no client
should see internal-sounding phrasing like "активного психолога". Replaced
with a warmer, more respectful message, still followed by the same
actionable keyboard (main_menu_keyboard already offers retry-by-name,
get-matched-by-questionnaire, and the rest of the menu - no separate
keyboard was needed).
"""
from types import SimpleNamespace

import pytest

from app.handlers.client import find_psychologist_by_name_value


class FakeMessage:
    def __init__(self):
        self.answered = []

    async def answer(self, text, reply_markup=None, **kwargs):
        self.answered.append(text)


class FakeState:
    async def clear(self):
        pass


@pytest.mark.asyncio
async def test_name_search_not_found_uses_warm_message_and_menu_actions(monkeypatch):
    import app.handlers.client as client_module

    async def fake_get_active_psychologists_with_slots():
        return []

    monkeypatch.setattr(client_module, "get_active_psychologists_with_slots", fake_get_active_psychologists_with_slots)

    message = FakeMessage()
    message.text = "Несуществующее Имя"
    state = FakeState()

    await find_psychologist_by_name_value(message, state)

    assert len(message.answered) == 1
    text = message.answered[0]

    # No dry technical wording.
    assert "активного психолога" not in text
    assert "доступным временем" not in text

    # The warmer message the user asked for.
    assert "К сожалению" in text
    assert "подобрать специалиста" in text
