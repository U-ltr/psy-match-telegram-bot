"""Finance/payout tracking for paid bookings.

One Payout row is created per successfully paid booking, splitting the
gross amount into the platform's commission and what's owed to the
psychologist. Free bookings (price=0) never reach create_payout_for_booking
- see services/yookassa_payments.py, the only caller, which only runs on a
real YooKassa payment.succeeded event.
"""
from datetime import datetime

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.booking import Booking
from app.models.payout import Payout


def split_amount(gross_amount: int, commission_percent: int | None = None) -> tuple[int, int]:
    """Returns (commission_amount, psychologist_amount). Commission is
    rounded down (in the platform's favor is the wrong framing - rounding
    down just avoids a fractional-kopeck psychologist_amount); the two
    always sum back to gross_amount."""
    percent = settings.platform_commission_percent if commission_percent is None else commission_percent
    commission_amount = (gross_amount * percent) // 100
    psychologist_amount = gross_amount - commission_amount
    return commission_amount, psychologist_amount


async def create_payout_for_booking(booking_id: int) -> Payout | None:
    """Idempotent: calling this more than once for the same booking (e.g. a
    retried webhook) never creates a second Payout row."""
    async with async_session() as session:
        existing = (
            await session.execute(select(Payout).where(Payout.booking_id == booking_id))
        ).scalar_one_or_none()

        if existing:
            return existing

        booking = await session.get(Booking, booking_id)

        if not booking:
            print(f"Payout create failed: booking {booking_id} not found")
            return None

        if booking.price <= 0:
            # Free bookings never get a payout - nothing was actually collected.
            return None

        commission_percent = settings.platform_commission_percent
        commission_amount, psychologist_amount = split_amount(booking.price, commission_percent)

        payout = Payout(
            booking_id=booking.id,
            psychologist_id=booking.psychologist_id,
            gross_amount=booking.price,
            commission_amount=commission_amount,
            psychologist_amount=psychologist_amount,
            commission_percent=commission_percent,
            status="pending",
        )

        session.add(payout)
        await session.commit()
        await session.refresh(payout)

        return payout


async def cancel_payout_for_booking(booking_id: int) -> bool:
    """Called when a booking that was already paid gets refunded/cancelled
    afterwards. Only cancels payouts that haven't been paid out yet - a
    payout already marked "paid" is a real bank transfer that already
    happened and must be resolved manually, not silently flipped."""
    async with async_session() as session:
        payout = (
            await session.execute(select(Payout).where(Payout.booking_id == booking_id))
        ).scalar_one_or_none()

        if not payout:
            return False

        if payout.status == "paid":
            print(f"Payout {payout.id} already paid out - not auto-cancelling, needs manual review")
            return False

        payout.status = "cancelled"
        await session.commit()

        return True


async def mark_payout_ready(payout_id: int) -> bool:
    async with async_session() as session:
        payout = await session.get(Payout, payout_id)

        if not payout or payout.status not in ("pending",):
            return False

        payout.status = "ready"
        await session.commit()

        return True


async def mark_payout_paid(payout_id: int, note: str | None = None) -> bool:
    async with async_session() as session:
        payout = await session.get(Payout, payout_id)

        if not payout or payout.status == "paid":
            return False

        payout.status = "paid"
        payout.paid_at = datetime.utcnow()

        if note:
            payout.note = note

        await session.commit()

        return True


async def get_payouts_summary() -> dict:
    """Aggregate totals for the admin finance view."""
    async with async_session() as session:
        payouts = (await session.execute(select(Payout))).scalars().all()

    summary = {
        "total_gross": 0,
        "total_commission": 0,
        "total_psychologist_amount": 0,
        "by_status": {"pending": 0, "ready": 0, "paid": 0, "cancelled": 0},
        "owed_unpaid": 0,  # psychologist_amount for pending+ready payouts
    }

    for payout in payouts:
        summary["total_gross"] += payout.gross_amount
        summary["total_commission"] += payout.commission_amount
        summary["total_psychologist_amount"] += payout.psychologist_amount
        summary["by_status"][payout.status] = summary["by_status"].get(payout.status, 0) + 1

        if payout.status in ("pending", "ready"):
            summary["owed_unpaid"] += payout.psychologist_amount

    return summary


async def get_payouts_for_psychologist(psychologist_id: int) -> list[Payout]:
    async with async_session() as session:
        result = await session.execute(
            select(Payout)
            .where(Payout.psychologist_id == psychologist_id)
            .order_by(Payout.created_at.desc())
        )
        return list(result.scalars().all())


async def get_all_payouts(status: str | None = None) -> list[Payout]:
    async with async_session() as session:
        query = select(Payout).order_by(Payout.created_at.desc())

        if status:
            query = query.where(Payout.status == status)

        result = await session.execute(query)
        return list(result.scalars().all())
