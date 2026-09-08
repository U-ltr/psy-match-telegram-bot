"""Background job for unpaid RESERVED bookings.

Two separate concerns used to live here and both wrote to the same rows:
a 10-minute-before-expiry warning to the client, and expiring the
reservation once reserved_until passed. The expiry half is now handled
solely by services/bookings.release_expired_bookings (see its docstring) -
this module only sends the warning and then triggers that shared expiry
check so notifications for anything it just expired go out immediately.
"""
import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select

from app.database import async_session
from app.models.booking import Booking
from app.models.user import User
from app.services.telegram_sender import send_message_safely
from app.services.bookings import release_expired_bookings


async def process_unpaid_bookings_once() -> None:
    now = datetime.utcnow()

    async with async_session() as session:
        result = await session.execute(
            select(Booking).where(
                Booking.status == "reserved",
                Booking.payment_status == "pending",
                Booking.reserved_until.is_not(None),
            )
        )

        bookings = result.scalars().all()

        for booking in bookings:
            warning_time = booking.reserved_until - timedelta(minutes=10)

            if not (now >= warning_time and now < booking.reserved_until and not booking.payment_warning_10m_sent):
                continue

            user = await session.get(User, booking.user_id)

            if not user:
                continue

            delivered = await send_message_safely(
                user.telegram_id,
                (
                    "Время на оплату почти истекло ⏳\n\n"
                    f"Запись №{booking.id} пока не оплачена.\n"
                    "Если оплата не будет завершена, выбранное время снова станет доступным другим клиентам."
                ),
            )

            if delivered:
                booking.payment_warning_10m_sent = True

        await session.commit()

    # Expire anything whose hold has now passed and notify about it - shared
    # with every other read path, see release_expired_bookings' docstring.
    await release_expired_bookings()


async def unpaid_bookings_loop() -> None:
    while True:
        try:
            await process_unpaid_bookings_once()
        except Exception as error:
            print(f"Unpaid bookings loop error: {error}")

        await asyncio.sleep(60)
