from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Payout(Base):
    """One row per PAID booking, tracking what the platform owes the
    psychologist and whether that has actually been paid out.

    Never created for free bookings (price=0, never touches the YooKassa
    flow) - see services/payouts.py, the only place that should create or
    update these rows.
    """

    __tablename__ = "payouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), unique=True, index=True)
    psychologist_id: Mapped[int] = mapped_column(ForeignKey("psychologists.id"), index=True)

    gross_amount: Mapped[int] = mapped_column(Integer)
    commission_amount: Mapped[int] = mapped_column(Integer)
    psychologist_amount: Mapped[int] = mapped_column(Integer)
    commission_percent: Mapped[int] = mapped_column(Integer)

    # pending -> ready -> paid, or -> cancelled (e.g. the underlying booking
    # was refunded after already being marked payable)
    status: Mapped[str] = mapped_column(String(50), default="pending")

    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
