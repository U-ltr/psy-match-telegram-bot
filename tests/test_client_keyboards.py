"""Client-facing keyboard shape: app/keyboards/client.py.

Mostly a shape/regression check - the actual "works from any state"
behavior for the persistent restart button is a router-registration-order
property (see app/handlers/client.py: every free-text FSM state handler
now excludes F.text == "Начать заново" so the message falls through to
the global restart handler instead of being swallowed as raw input),
which isn't something a keyboard-shape test can exercise on its own.
"""
from app.keyboards.client import restart_reply_keyboard


def test_restart_reply_keyboard_has_exactly_one_button():
    # The bottom reply keyboard must be minimal: only "Начать заново".
    # Psychologists/admins have their own entry points (/psychologist,
    # /admin) and must not see anything added here.
    markup = restart_reply_keyboard()

    all_buttons = [button for row in markup.keyboard for button in row]

    assert len(all_buttons) == 1
    assert all_buttons[0].text == "Начать заново"
