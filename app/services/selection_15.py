from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.booking import Booking
from app.models.psychologist import Psychologist


SELECTION_SPECIALIST_NAME = "Специалист по подбору психолога"


def is_future_moscow_slot(date_value: str, time_value: str) -> bool:
    slot_dt = datetime.strptime(f"{date_value} {time_value}", "%Y-%m-%d %H:%M")
    now_moscow = datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None)

    return slot_dt > now_moscow



async def get_or_create_selection_specialist() -> Psychologist:
    async with async_session() as session:
        result = await session.execute(
            select(Psychologist).where(Psychologist.name == SELECTION_SPECIALIST_NAME)
        )
        specialist = result.scalar_one_or_none()

        if specialist:
            specialist.durations = [{"minutes": settings.selection_15_duration, "price": 0}]
            specialist.specializations = ["selection"]
            specialist.styles = ["universal"]
            specialist.description = (
                "15-минутный подбор поможет точнее выбрать психолога, "
                "если Вы не знаете, с кем начать."
            )
            specialist.is_active = True
            await session.commit()
            return specialist

        specialist = Psychologist(
            telegram_id=None,
            name=SELECTION_SPECIALIST_NAME,
            gender="any",
            description=(
                "15-минутный подбор поможет точнее выбрать психолога, "
                "если Вы не знаете, с кем начать."
            ),
            education="",
            experience_years=0,
            specializations=["selection"],
            styles=["universal"],
            durations=[{"minutes": settings.selection_15_duration, "price": 0}],
            therapy_experience_fit=["no", "positive", "negative"],
            is_active=True,
        )

        session.add(specialist)
        await session.commit()
        await session.refresh(specialist)

        return specialist


async def get_selection_available_slots(limit: int = 8) -> list[dict]:
    """
    MVP-слоты для 15-минутного подбора.

    Для простоты даём фиксированные окна на ближайшие 7 дней:
    12:00, 15:00, 18:00, 20:00.
    Занятые/оплаченные/зарезервированные записи исключаются.
    """

    specialist = await get_or_create_selection_specialist()

    timezone = ZoneInfo(settings.timezone)
    now = datetime.now(timezone)

    candidate_times = ["12:00", "15:00", "18:00", "20:00"]
    candidate_slots = []

    for day_offset in range(0, 8):
        current_date = now.date() + timedelta(days=day_offset)

        for start_time in candidate_times:
            slot_dt = datetime.strptime(
                f"{current_date} {start_time}",
                "%Y-%m-%d %H:%M",
            ).replace(tzinfo=timezone)

            if slot_dt <= now + timedelta(minutes=30):
                continue

            if not is_future_moscow_slot(str(current_date), start_time):
                continue

            candidate_slots.append(
                {
                    "date": current_date.strftime("%Y-%m-%d"),
                    "time": start_time,
                    "duration": settings.selection_15_duration,
                    "price": 0,  # this consultation is always free, never sent to YooKassa
                    "psychologist_id": specialist.id,
                }
            )

    async with async_session() as session:
        result = await session.execute(
            select(Booking).where(
                Booking.psychologist_id == specialist.id,
                Booking.status.in_(["reserved", "paid", "confirmed"]),
                Booking.payment_status.in_(["pending", "paid"]),
            )
        )
        active_bookings = result.scalars().all()

    busy_pairs = {(booking.date, booking.start_time) for booking in active_bookings}

    available = [
        slot for slot in candidate_slots
        if (slot["date"], slot["time"]) not in busy_pairs
    ]

    return available[:limit]


async def get_selection_slot_by_index(index: int) -> dict | None:
    slots = await get_selection_available_slots(limit=20)

    if index < 0 or index >= len(slots):
        return None

    return slots[index]
