from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Psychologist(Base):
    __tablename__ = "psychologists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True, index=True)

    name: Mapped[str] = mapped_column(String(255))
    gender: Mapped[str | None] = mapped_column(String(50), nullable=True)
    photo_file_id: Mapped[str | None] = mapped_column(String(500), nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    education: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience_years: Mapped[int] = mapped_column(Integer, default=0)

    # Each psychologist sets their own price PER duration - there is no
    # single flat price. Stored as a JSON list of
    # {"minutes": int, "price": int} objects, e.g.
    # [{"minutes": 30, "price": 2500}, {"minutes": 60, "price": 4000}].
    # See services/pricing.py for the only place that should read/write this.
    durations: Mapped[list] = mapped_column(JSON, default=list)

    specializations: Mapped[list] = mapped_column(JSON, default=list)
    help_topics: Mapped[list] = mapped_column(JSON, default=list)
    styles: Mapped[list] = mapped_column(JSON, default=list)
    therapy_experience_fit: Mapped[list] = mapped_column(JSON, default=list)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
