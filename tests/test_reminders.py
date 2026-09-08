"""Reminder windows and the meeting-link fallback: app/services/reminders.py."""
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.services.reminders import (
    is_within_reminder_window,
    send_booking_reminder_10m,
    send_booking_reminder_1h,
)


# ---- window predicate (pure) -------------------------------------------

def test_within_window_true_in_range():
    assert is_within_reminder_window(timedelta(minutes=60), 55, 65, already_sent=False) is True


def test_within_window_false_outside_range():
    assert is_within_reminder_window(timedelta(minutes=14), 7, 12, already_sent=False) is False
    assert is_within_reminder_window(timedelta(minutes=6), 7, 12, already_sent=False) is False


def test_within_window_false_when_already_sent():
    assert is_within_reminder_window(timedelta(minutes=60), 55, 65, already_sent=True) is False


def test_within_window_edges_are_inclusive():
    assert is_within_reminder_window(timedelta(minutes=55), 55, 65, already_sent=False) is True
    assert is_within_reminder_window(timedelta(minutes=65), 55, 65, already_sent=False) is True


def test_within_window_naive_le_60_would_have_wrongly_matched_at_14_minutes():
    # Regression guard for the exact bug the spec called out: a naive
    # `<= 60` check for the "1 hour" reminder would still be true at
    # minute 14, firing a wildly wrong "in 1 hour" message. The window
    # form must reject it.
    assert is_within_reminder_window(timedelta(minutes=14), 55, 65, already_sent=False) is False


# ---- meeting-link fallback (DB-free: plain objects + stubbed sender) ---

def booking(**kwargs):
    defaults = dict(
        id=42,
        date="2099-01-10",
        start_time="15:00",
        duration=60,
        meeting_link=None,
        booking_type="consultation",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def user(**kwargs):
    defaults = dict(telegram_id=555, full_name="Клиент Клиентов", phone="+7 900 000-00-00")
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def psychologist(**kwargs):
    defaults = dict(telegram_id=777, name="Психолог Психологов")
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_10m_reminder_with_link_sends_it_to_client(monkeypatch):
    from tests.conftest import stub_send_message_safely, stub_notify_admins
    import app.services.reminders as reminders_module

    sent = stub_send_message_safely(monkeypatch, reminders_module)
    admin_alerts = stub_notify_admins(monkeypatch, reminders_module)

    b = booking(meeting_link="https://meet.jit.si/abc123")
    delivered = await send_booking_reminder_10m(b, user(), psychologist())

    assert delivered is True
    client_messages = [text for chat_id, text in sent if chat_id == 555]
    assert len(client_messages) == 1
    assert "https://meet.jit.si/abc123" in client_messages[0]
    assert admin_alerts == []  # no alert needed, link was present


@pytest.mark.asyncio
async def test_10m_reminder_without_link_never_fabricates_one(monkeypatch):
    from tests.conftest import stub_send_message_safely, stub_notify_admins
    import app.services.reminders as reminders_module

    sent = stub_send_message_safely(monkeypatch, reminders_module)
    stub_notify_admins(monkeypatch, reminders_module)

    b = booking(meeting_link=None)
    await send_booking_reminder_10m(b, user(), psychologist())

    client_messages = [text for chat_id, text in sent if chat_id == 555]
    assert len(client_messages) == 1
    # Must not contain a bare/placeholder URL - only an honest "we'll send
    # it shortly" message.
    assert "http" not in client_messages[0]


@pytest.mark.asyncio
async def test_10m_reminder_without_link_alerts_psychologist_and_admins(monkeypatch):
    from tests.conftest import stub_send_message_safely, stub_notify_admins
    import app.services.reminders as reminders_module

    sent = stub_send_message_safely(monkeypatch, reminders_module)
    admin_alerts = stub_notify_admins(monkeypatch, reminders_module)

    b = booking(meeting_link=None)
    await send_booking_reminder_10m(b, user(), psychologist())

    psychologist_messages = [text for chat_id, text in sent if chat_id == 777]
    assert len(psychologist_messages) == 1
    assert "СРОЧНО" in psychologist_messages[0]

    assert len(admin_alerts) == 1


@pytest.mark.asyncio
async def test_10m_reminder_delivery_failure_returns_false(monkeypatch):
    from tests.conftest import stub_send_message_safely, stub_notify_admins
    import app.services.reminders as reminders_module

    stub_send_message_safely(monkeypatch, reminders_module, result=False)
    stub_notify_admins(monkeypatch, reminders_module)

    b = booking(meeting_link="https://meet.jit.si/abc123")
    delivered = await send_booking_reminder_10m(b, user(), psychologist())

    # Caller (process_booking_reminders_once) relies on this to decide
    # whether reminder_10m_sent may be set to True.
    assert delivered is False


@pytest.mark.asyncio
async def test_1h_reminder_client_delivery_failure_does_not_block_psychologist_send(monkeypatch):
    from tests.conftest import stub_send_message_safely
    import app.services.reminders as reminders_module

    calls = []

    async def flaky_send(chat_id, text, **kwargs):
        calls.append(chat_id)
        return chat_id != 555  # client fails, psychologist succeeds

    monkeypatch.setattr(reminders_module, "send_message_safely", flaky_send)

    b = booking()
    delivered = await send_booking_reminder_1h(b, user(), psychologist())

    assert delivered is False  # client not reached
    assert 555 in calls
    assert 777 in calls  # psychologist side still attempted independently
