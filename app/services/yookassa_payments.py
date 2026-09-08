import base64
import uuid

from aiohttp import ClientSession
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.booking import Booking
from app.models.payment import Payment
from app.models.user import User
from app.services.notifications import (
    send_payment_success_notifications,
    send_payment_cancelled_notification,
)
from app.services.payouts import create_payout_for_booking, cancel_payout_for_booking
from app.services.bookings import try_auto_create_meeting_link


YOOKASSA_API_URL = "https://api.yookassa.ru/v3/payments"


def _auth_header() -> str:
    raw = f"{settings.yookassa_shop_id}:{settings.yookassa_secret_key}"
    encoded = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
    return f"Basic {encoded}"


async def create_yookassa_payment_for_booking(telegram_id: int, booking_id: int) -> str | None:
    if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
        print("YooKassa settings are empty")
        return None

    async with async_session() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            print("Payment create failed: user not found")
            return None

        booking = await session.get(Booking, booking_id)

        if not booking:
            print("Payment create failed: booking not found")
            return None

        if booking.user_id != user.id:
            print("Payment create failed: booking does not belong to user")
            return None

        if booking.status == "cancelled":
            print("Payment create failed: booking cancelled")
            return None

        if booking.payment_status == "paid":
            print("Payment create failed: booking already paid")
            return None

        if booking.price <= 0:
            print(f"Payment create failed: invalid booking price {booking.price}")
            return None

        existing_payment_result = await session.execute(
            select(Payment).where(
                Payment.booking_id == booking.id,
                Payment.status.in_(["pending", "waiting_for_capture"]),
            )
        )
        existing_payment = existing_payment_result.scalar_one_or_none()

        if existing_payment and existing_payment.confirmation_url:
            return existing_payment.confirmation_url

        amount_value = f"{booking.price:.2f}"

        payload = {
            "amount": {
                "value": amount_value,
                "currency": "RUB",
            },
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": settings.yookassa_return_url,
            },
            "description": f"Консультация психолога, запись №{booking.id}",
            "metadata": {
                "booking_id": str(booking.id),
                "telegram_id": str(telegram_id),
            },
        }

        headers = {
            "Authorization": _auth_header(),
            "Idempotence-Key": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }

    async with ClientSession() as client:
        async with client.post(YOOKASSA_API_URL, json=payload, headers=headers) as response:
            response_data = await response.json()

            if response.status not in [200, 201]:
                print("YooKassa payment create error:", response.status, response_data)
                return None

    payment_id = response_data.get("id")
    confirmation_url = response_data.get("confirmation", {}).get("confirmation_url")

    if not payment_id or not confirmation_url:
        print("YooKassa response without payment_id or confirmation_url:", response_data)
        return None

    async with async_session() as session:
        booking = await session.get(Booking, booking_id)

        if not booking:
            return None

        payment = Payment(
            booking_id=booking.id,
            user_id=booking.user_id,
            amount=booking.price,
            status=response_data.get("status", "pending"),
            payment_provider="yookassa",
            provider_payment_id=payment_id,
            confirmation_url=confirmation_url,
            email_for_receipt=None,
        )

        session.add(payment)
        await session.commit()

    return confirmation_url


async def apply_yookassa_webhook(event: str, payment_object: dict) -> bool:
    provider_payment_id = payment_object.get("id")
    metadata = payment_object.get("metadata") or {}
    booking_id_raw = metadata.get("booking_id")

    print("YooKassa webhook event:", event)
    print("YooKassa payment id:", provider_payment_id)
    print("YooKassa metadata:", metadata)

    if not provider_payment_id or not booking_id_raw:
        print("Webhook ignored: no payment id or booking_id")
        return False

    try:
        booking_id = int(booking_id_raw)
    except ValueError:
        print("Webhook ignored: invalid booking_id")
        return False

    should_notify_success = False
    should_notify_cancelled = False

    async with async_session() as session:
        booking = await session.get(Booking, booking_id)

        if not booking:
            print("Webhook ignored: booking not found")
            return False

        payment_result = await session.execute(
            select(Payment).where(Payment.provider_payment_id == provider_payment_id)
        )
        payment = payment_result.scalar_one_or_none()

        if event == "payment.succeeded":
            already_paid = booking.payment_status == "paid"

            booking.status = "paid"
            booking.payment_status = "paid"

            if payment:
                payment.status = "succeeded"

            should_notify_success = not already_paid

        elif event == "payment.canceled":
            if booking.payment_status != "paid":
                booking.status = "cancelled"
                booking.payment_status = "cancelled"

                if payment:
                    payment.status = "canceled"

                should_notify_cancelled = True

        else:
            print("Webhook ignored: unsupported event", event)
            return False

        await session.commit()

    if should_notify_success:
        print(f"Creating payout record for booking {booking_id}")
        await create_payout_for_booking(booking_id)

        print(f"Attempting to create a Jitsi meeting link for booking {booking_id}")
        await try_auto_create_meeting_link(booking_id)

        print(f"Sending payment success notifications for booking {booking_id}")
        await send_payment_success_notifications(booking_id)

    if should_notify_cancelled:
        print(f"Cancelling payout record (if any) for booking {booking_id}")
        await cancel_payout_for_booking(booking_id)

        print(f"Sending payment cancelled notification for booking {booking_id}")
        await send_payment_cancelled_notification(booking_id)

    return True




async def sync_yookassa_payment_status(provider_payment_id: str) -> bool:
    """
    Резервная проверка статуса платежа в ЮKassa.
    Нужна на случай, если webhook не дошёл.
    """

    if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
        print("YooKassa settings are empty")
        return False

    headers = {
        "Authorization": _auth_header(),
        "Content-Type": "application/json",
    }

    url = f"{YOOKASSA_API_URL}/{provider_payment_id}"

    async with ClientSession() as client:
        async with client.get(url, headers=headers) as response:
            response_data = await response.json()

            if response.status != 200:
                print("YooKassa payment status error:", response.status, response_data)
                return False

    payment_status = response_data.get("status")
    metadata = response_data.get("metadata") or {}

    print("YooKassa real payment status:", payment_status)
    print("YooKassa payment metadata:", metadata)

    if payment_status == "succeeded":
        return await apply_yookassa_webhook(
            event="payment.succeeded",
            payment_object=response_data,
        )

    if payment_status == "canceled":
        return await apply_yookassa_webhook(
            event="payment.canceled",
            payment_object=response_data,
        )

    print("Payment is not finished yet:", payment_status)
    return False

async def sync_pending_yookassa_payments_once() -> None:
    """
    Резервная синхронизация pending-платежей.
    Если webhook ЮKassa не дошёл, бот сам проверит статус платежа.
    """

    async with async_session() as session:
        result = await session.execute(
            select(Payment).where(
                Payment.payment_provider == "yookassa",
                Payment.status.in_(["pending", "waiting_for_capture"]),
                Payment.provider_payment_id.isnot(None),
            )
        )

        payments = result.scalars().all()

    if not payments:
        return

    print(f"YooKassa sync: found {len(payments)} pending payments")

    for payment in payments:
        if not payment.provider_payment_id:
            continue

        try:
            await sync_yookassa_payment_status(payment.provider_payment_id)
        except Exception as error:
            print(
                f"YooKassa sync failed for payment {payment.id} "
                f"{payment.provider_payment_id}: {error}"
            )


async def yookassa_payments_sync_loop() -> None:
    """
    Постоянный фоновый цикл проверки платежей.
    Работает как страховка к webhook.
    """

    import asyncio

    while True:
        try:
            await sync_pending_yookassa_payments_once()
        except Exception as error:
            print(f"YooKassa sync loop error: {error}")

        await asyncio.sleep(60)
