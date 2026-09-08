from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class BusyInterval(Base):
    __tablename__ = "busy_intervals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    psychologist_id: Mapped[int] = mapped_column(ForeignKey("psychologists.id"), index=True)

    date: Mapped[str] = mapped_column(String(20))
    start_time: Mapped[str] = mapped_column(String(10))
    end_time: Mapped[str] = mapped_column(String(10))

    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
