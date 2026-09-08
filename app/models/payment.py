from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    amount: Mapped[int] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String(50), default="pending")
    payment_provider: Mapped[str] = mapped_column(String(100), default="yookassa")

    provider_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    confirmation_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    email_for_receipt: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
