"""Global aiogram error handler: app/error_handling.py.

The handler only needs a few attributes off the real aiogram ErrorEvent/
Update objects (.exception, .update.update_id, .update.message,
.update.callback_query), so plain SimpleNamespace stand-ins are enough
here and keep these tests independent of aiogram's own type internals.
"""
from types import SimpleNamespace

import pytest

from app import error_handling


def _make_event(exception, message=None, callback_query=None, update_id=1):
    update = SimpleNamespace(
        update_id=update_id,
        message=message,
        callback_query=callback_query,
    )
    return SimpleNamespace(exception=exception, update=update)


@pytest.mark.asyncio
async def test_notifies_admins_with_exception_details(monkeypatch):
    notify_calls = []

    async def fake_notify_admins(text):
        notify_calls.append(text)

    async def fake_send_message_safely(chat_id, text, **kwargs):
        return True

    monkeypatch.setattr(error_handling, "notify_admins", fake_notify_admins)
    monkeypatch.setattr(error_handling, "send_message_safely", fake_send_message_safely)

    event = _make_event(ValueError("boom"), update_id=42)

    result = await error_handling.handle_unexpected_error(event)

    assert result is True
    assert len(notify_calls) == 1
    assert "ValueError" in notify_calls[0]
    assert "boom" in notify_calls[0]
    assert "42" in notify_calls[0]


@pytest.mark.asyncio
async def test_sends_generic_fallback_to_the_message_chat(monkeypatch):
    monkeypatch.setattr(error_handling, "notify_admins", _noop_notify)

    sent = []

    async def fake_send_message_safely(chat_id, text, **kwargs):
        sent.append((chat_id, text))
        return True

    monkeypatch.setattr(error_handling, "send_message_safely", fake_send_message_safely)

    message = SimpleNamespace(chat=SimpleNamespace(id=555))
    event = _make_event(RuntimeError("db down"), message=message)

    await error_handling.handle_unexpected_error(event)

    assert sent == [(555, error_handling.CLIENT_FALLBACK_TEXT)]


@pytest.mark.asyncio
async def test_sends_generic_fallback_to_the_callback_query_chat(monkeypatch):
    monkeypatch.setattr(error_handling, "notify_admins", _noop_notify)

    sent = []

    async def fake_send_message_safely(chat_id, text, **kwargs):
        sent.append((chat_id, text))
        return True

    monkeypatch.setattr(error_handling, "send_message_safely", fake_send_message_safely)

    callback_query = SimpleNamespace(message=SimpleNamespace(chat=SimpleNamespace(id=777)))
    event = _make_event(RuntimeError("db down"), callback_query=callback_query)

    await error_handling.handle_unexpected_error(event)

    assert sent == [(777, error_handling.CLIENT_FALLBACK_TEXT)]


@pytest.mark.asyncio
async def test_never_raises_even_if_notify_admins_fails(monkeypatch):
    async def failing_notify_admins(text):
        raise RuntimeError("telegram API down")

    async def fake_send_message_safely(chat_id, text, **kwargs):
        return True

    monkeypatch.setattr(error_handling, "notify_admins", failing_notify_admins)
    monkeypatch.setattr(error_handling, "send_message_safely", fake_send_message_safely)

    message = SimpleNamespace(chat=SimpleNamespace(id=555))
    event = _make_event(RuntimeError("original error"), message=message)

    # Must not raise - a broken admin notification must not crash the bot
    # on top of the original error it was trying to report.
    result = await error_handling.handle_unexpected_error(event)

    assert result is True


@pytest.mark.asyncio
async def test_never_raises_even_if_client_fallback_send_fails(monkeypatch):
    monkeypatch.setattr(error_handling, "notify_admins", _noop_notify)

    async def failing_send(chat_id, text, **kwargs):
        raise RuntimeError("telegram API down")

    monkeypatch.setattr(error_handling, "send_message_safely", failing_send)

    message = SimpleNamespace(chat=SimpleNamespace(id=555))
    event = _make_event(RuntimeError("original error"), message=message)

    result = await error_handling.handle_unexpected_error(event)

    assert result is True


@pytest.mark.asyncio
async def test_no_chat_available_skips_client_fallback_but_still_notifies_admins(monkeypatch):
    notify_calls = []

    async def fake_notify_admins(text):
        notify_calls.append(text)

    send_calls = []

    async def fake_send_message_safely(chat_id, text, **kwargs):
        send_calls.append((chat_id, text))
        return True

    monkeypatch.setattr(error_handling, "notify_admins", fake_notify_admins)
    monkeypatch.setattr(error_handling, "send_message_safely", fake_send_message_safely)

    # Neither .message nor .callback_query set - e.g. some non-message update type.
    event = _make_event(RuntimeError("oops"))

    await error_handling.handle_unexpected_error(event)

    assert len(notify_calls) == 1
    assert send_calls == []


async def _noop_notify(text):
    pass


@pytest.mark.asyncio
async def test_same_update_reported_twice_only_notifies_once(monkeypatch):
    """Regression: manual testing found the SAME error producing two (or
    more) identical admin notifications and client fallbacks, recurring on
    every subsequent update too. Whatever redelivers an update twice (a
    second bot process left running, aiogram retrying after a hiccup, ...),
    one update_id must only ever produce one admin notification and one
    client fallback."""
    notify_calls = []

    async def fake_notify_admins(text):
        notify_calls.append(text)

    send_calls = []

    async def fake_send_message_safely(chat_id, text, **kwargs):
        send_calls.append((chat_id, text))
        return True

    monkeypatch.setattr(error_handling, "notify_admins", fake_notify_admins)
    monkeypatch.setattr(error_handling, "send_message_safely", fake_send_message_safely)
    # Isolate this test from any update_ids other tests in this run happened
    # to reuse - the dedup set is module-level state.
    monkeypatch.setattr(error_handling, "_recently_reported_update_ids", error_handling.deque(maxlen=500))

    message = SimpleNamespace(chat=SimpleNamespace(id=555))

    await error_handling.handle_unexpected_error(_make_event(ValueError("boom"), message=message, update_id=9001))
    await error_handling.handle_unexpected_error(_make_event(ValueError("boom"), message=message, update_id=9001))
    await error_handling.handle_unexpected_error(_make_event(ValueError("boom"), message=message, update_id=9001))

    assert len(notify_calls) == 1
    assert len(send_calls) == 1


@pytest.mark.asyncio
async def test_two_distinct_updates_each_notify_separately(monkeypatch):
    """The dedup guard must never turn into a debounce that hides a real,
    separate error - two different update_ids must each produce their own
    admin notification and client fallback."""
    notify_calls = []

    async def fake_notify_admins(text):
        notify_calls.append(text)

    send_calls = []

    async def fake_send_message_safely(chat_id, text, **kwargs):
        send_calls.append((chat_id, text))
        return True

    monkeypatch.setattr(error_handling, "notify_admins", fake_notify_admins)
    monkeypatch.setattr(error_handling, "send_message_safely", fake_send_message_safely)
    monkeypatch.setattr(error_handling, "_recently_reported_update_ids", error_handling.deque(maxlen=500))

    message = SimpleNamespace(chat=SimpleNamespace(id=555))

    await error_handling.handle_unexpected_error(_make_event(ValueError("first"), message=message, update_id=9101))
    await error_handling.handle_unexpected_error(_make_event(ValueError("second"), message=message, update_id=9102))

    assert len(notify_calls) == 2
    assert len(send_calls) == 2
