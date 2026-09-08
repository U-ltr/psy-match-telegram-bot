"""Webhook-driven payment status updates are idempotent:
app/services/yookassa_payments.py's apply_yookassa_webhook.

Notifications and payout creation are stubbed at the yookassa_payments
module boundary (it imports each by name, e.g.
`from app.services.payouts import create_payout_for_booking`) so these
tests isolate the state-transition logic itself: a retried/duplicated
"payment.succeeded" webhook (a real thing YooKassa's own docs say to
expect) must not double-charge side effects.
"""
import pytest

from app.models.booking import Booking
from app.models.psychologist import Psychologist
from app.services.yookassa_payments import apply_yookassa_webhook


async def make_reserved_booking(db, price=4000):
    async with db() as session:
        psychologist = Psychologist(
            telegram_id=None,
            name="Тест Психологов",
            education="",
            durations=[{"minutes": 60, "price": price}],
            specializations=[],
            help_topics=[],
            styles=[],
            therapy_experience_fit=[],
            is_active=True,
        )
        session.add(psychologist)
        await session.flush()

        booking = Booking(
            user_id=1,
            psychologist_id=psychologist.id,
            date="2099-01-10",
            start_time="10:00",
            status="reserved",
            payment_status="pending",
            price=price,
            duration=60,
        )
        session.add(booking)
        await session.commit()
        await session.refresh(booking)
        return booking.id


def stub_side_effects(monkeypatch):
    import app.services.yookassa_payments as module

    payout_calls = []
    cancel_calls = []
    success_notify_calls = []
    cancel_notify_calls = []
    meeting_link_calls = []

    async def fake_create_payout(booking_id):
        payout_calls.append(booking_id)

    async def fake_cancel_payout(booking_id):
        cancel_calls.append(booking_id)
        return True

    async def fake_success_notify(booking_id):
        success_notify_calls.append(booking_id)

    async def fake_cancel_notify(booking_id):
        cancel_notify_calls.append(booking_id)

    async def fake_meeting_link(booking_id):
        meeting_link_calls.append(booking_id)

    monkeypatch.setattr(module, "create_payout_for_booking", fake_create_payout)
    monkeypatch.setattr(module, "cancel_payout_for_booking", fake_cancel_payout)
    monkeypatch.setattr(module, "send_payment_success_notifications", fake_success_notify)
    monkeypatch.setattr(module, "send_payment_cancelled_notification", fake_cancel_notify)
    monkeypatch.setattr(module, "try_auto_create_meeting_link", fake_meeting_link)

    return payout_calls, cancel_calls, success_notify_calls, cancel_notify_calls, meeting_link_calls


@pytest.mark.asyncio
async def test_payment_succeeded_marks_booking_paid(db, monkeypatch):
    booking_id = await make_reserved_booking(db)
    payout_calls, _, success_calls, _, meeting_link_calls = stub_side_effects(monkeypatch)

    ok = await apply_yookassa_webhook(
        event="payment.succeeded",
        payment_object={"id": "pay_1", "metadata": {"booking_id": str(booking_id)}},
    )

    assert ok is True

    async with db() as session:
        booking = await session.get(Booking, booking_id)
        assert booking.status == "paid"
        assert booking.payment_status == "paid"

    assert payout_calls == [booking_id]
    assert success_calls == [booking_id]
    assert meeting_link_calls == [booking_id]


@pytest.mark.asyncio
async def test_payment_succeeded_webhook_is_idempotent_on_retry(db, monkeypatch):
    # YooKassa can and does deliver the same webhook more than once - a
    # second "payment.succeeded" for an already-paid booking must not
    # create a second payout or send a second success notification.
    booking_id = await make_reserved_booking(db)
    payout_calls, _, success_calls, _, meeting_link_calls = stub_side_effects(monkeypatch)

    payload = {"id": "pay_1", "metadata": {"booking_id": str(booking_id)}}

    await apply_yookassa_webhook(event="payment.succeeded", payment_object=payload)
    await apply_yookassa_webhook(event="payment.succeeded", payment_object=payload)

    assert payout_calls == [booking_id]  # not called twice
    assert success_calls == [booking_id]  # not notified twice
    assert meeting_link_calls == [booking_id]  # meeting link creation attempted once, not twice


@pytest.mark.asyncio
async def test_payment_canceled_before_paid_cancels_booking(db, monkeypatch):
    booking_id = await make_reserved_booking(db)
    _, cancel_calls, _, cancel_notify_calls, _ = stub_side_effects(monkeypatch)

    ok = await apply_yookassa_webhook(
        event="payment.canceled",
        payment_object={"id": "pay_2", "metadata": {"booking_id": str(booking_id)}},
    )

    assert ok is True

    async with db() as session:
        booking = await session.get(Booking, booking_id)
        assert booking.status == "cancelled"
        assert booking.payment_status == "cancelled"

    assert cancel_notify_calls == [booking_id]


@pytest.mark.asyncio
async def test_payment_canceled_after_already_paid_does_not_unpay_it(db, monkeypatch):
    # A cancel event arriving after the booking is already marked paid
    # (e.g. a stray/out-of-order webhook) must not silently revert it.
    booking_id = await make_reserved_booking(db)
    stub_side_effects(monkeypatch)

    await apply_yookassa_webhook(
        event="payment.succeeded",
        payment_object={"id": "pay_3", "metadata": {"booking_id": str(booking_id)}},
    )
    await apply_yookassa_webhook(
        event="payment.canceled",
        payment_object={"id": "pay_3", "metadata": {"booking_id": str(booking_id)}},
    )

    async with db() as session:
        booking = await session.get(Booking, booking_id)
        assert booking.status == "paid"
        assert booking.payment_status == "paid"


@pytest.mark.asyncio
async def test_webhook_ignored_without_booking_id(db, monkeypatch):
    stub_side_effects(monkeypatch)

    ok = await apply_yookassa_webhook(event="payment.succeeded", payment_object={"id": "pay_4"})

    assert ok is False
