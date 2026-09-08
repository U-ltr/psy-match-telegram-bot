from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


_ACTIVE_SLOT_WHERE = (
    "status IN ('reserved', 'confirmed', 'paid') "
    "AND payment_status IN ('pending', 'paid')"
)
# Kept in sync with migrations/versions/0002_active_booking_slot_unique.py
# and ACTIVE_BOOKING_STATUSES/ACTIVE_PAYMENT_STATUSES in services/bookings.py.


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    psychologist_id: Mapped[int] = mapped_column(ForeignKey("psychologists.id"), index=True)

    date: Mapped[str] = mapped_column(String(20))
    start_time: Mapped[str] = mapped_column(String(10))

    status: Mapped[str] = mapped_column(String(50), default="reserved")
    payment_status: Mapped[str] = mapped_column(String(50), default="pending")

    price: Mapped[int] = mapped_column(Integer)
    duration: Mapped[int] = mapped_column(Integer)

    meeting_link: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    client_answers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    client_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    reserved_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    reminder_1h_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_10m_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_warning_10m_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    booking_type: Mapped[str] = mapped_column(String(50), default="consultation")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Defense-in-depth against the exact-duplicate-slot race: even if a
    # future code path ever inserted a booking without going through
    # create_booking_from_generated_slot's row lock + overlap recheck (or
    # a bug crept into that logic), the database itself physically cannot
    # hold two ACTIVE bookings for the same psychologist at the same
    # (date, start_time) - the second INSERT fails with an IntegrityError
    # regardless of any application-level race. This only catches an
    # EXACT (date, start_time) collision, not a partial-overlap collision
    # with a different start_time (e.g. a 90-minute 10:00 booking vs a
    # 30-minute 10:30 one) - that general case still relies on the row
    # lock (SELECT ... FOR UPDATE on the psychologist), which is correct
    # on real PostgreSQL but cannot be validated against SQLite (SQLite
    # has no equivalent of FOR UPDATE's block-then-refresh semantics) -
    # see tests/test_concurrency_postgres.py for that guarantee's real
    # test.
    #
    # The predicate mirrors ACTIVE_BOOKING_STATUSES/ACTIVE_PAYMENT_STATUSES
    # in services/bookings.py, and deliberately does NOT reference
    # reserved_until (an index predicate must be immutable in PostgreSQL -
    # "now()" cannot appear in one). This is safe because
    # create_booking_from_generated_slot always calls
    # release_expired_bookings() first, which flips any stale
    # reserved/pending row's status away from "reserved" before any new
    # insert is attempted - so this constraint never sees a merely-stale
    # reservation as blocking a legitimately free slot.
    __table_args__ = (
        Index(
            "uq_active_booking_slot",
            "psychologist_id",
            "date",
            "start_time",
            unique=True,
            sqlite_where=text(_ACTIVE_SLOT_WHERE),
            postgresql_where=text(_ACTIVE_SLOT_WHERE),
        ),
    )
