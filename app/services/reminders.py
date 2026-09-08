import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.booking import Booking
from app.models.psychologist import Psychologist
from app.models.user import User
from app.services.telegram_sender import send_message_safely
from app.services.admin_notifications import notify_admins
from app.services.answer_formatting import minutes_declension


def is_within_reminder_window(
    time_until_start: timedelta,
    min_minutes: int,
    max_minutes: int,
    already_sent: bool,
) -> bool:
    """Pure predicate factored out of process_booking_reminders_once so the
    windowing logic (not a naive `<= 60` cutoff - see module docstring
    context) can be unit tested without a database or event loop."""
    if already_sent:
        return False

    return timedelta(minutes=min_minutes) <= time_until_start <= timedelta(minutes=max_minutes)


def get_booking_start_datetime(booking: Booking) -> datetime:
    timezone = ZoneInfo(settings.timezone)

    start = datetime.strptime(
        f"{booking.date} {booking.start_time}",
        "%Y-%m-%d %H:%M",
    )

    return start.replace(tzinfo=timezone)


async def send_booking_reminder_1h(
    booking: Booking,
    user: User,
    psychologist: Psychologist | None,
) -> bool:
    """Send the 1h-before reminder. Returns True only if the CLIENT was
    actually reached - that is the only thing allowed to set
    reminder_1h_sent, per spec: never mark a reminder sent on a real
    delivery failure. The psychologist side is sent independently and its
    failure does not block the client flag (each side is delivered on its
    own, one slow/failed send must not affect the other)."""

    psychologist_name = psychologist.name if psychologist else "психолог"
    service_title = (
        "15-минутный подбор специалистом"
        if getattr(booking, "booking_type", "consultation") == "selection_15min"
        else "Консультация психолога"
    )

    client_text = (
        "Напоминание о консультации ⏰\n\n"
        f"Через 1 час у Вас встреча.\n"
        f"Услуга: {service_title}\n\n"
        f"Психолог: {psychologist_name}\n"
        f"Дата: {booking.date}\n"
        f"Время: {booking.start_time} (по Москве)\n"
        f"Длительность: {minutes_declension(booking.duration)}"
    )

    psychologist_text = (
        "Напоминание о консультации ⏰\n\n"
        f"Через 1 час у Вас встреча.\n"
        f"Услуга: {service_title}\n\n"
        f"Запись №{booking.id}\n"
        f"Дата: {booking.date}\n"
        f"Время: {booking.start_time} (по Москве)\n"
        f"Длительность: {minutes_declension(booking.duration)}\n"
        f"Клиент: {user.full_name or 'не указано'}\n"
        f"Телефон: {user.phone or 'не указан'}"
    )

    client_ok = await send_message_safely(user.telegram_id, client_text)

    if psychologist and psychologist.telegram_id:
        await send_message_safely(psychologist.telegram_id, psychologist_text)

    return client_ok


async def send_booking_reminder_10m(
    booking: Booking,
    user: User,
    psychologist: Psychologist | None,
) -> bool:
    """Send the 10m-before reminder, with the video-link fallback the spec
    requires: never invent a link, never send a broken/blank one. If there
    is no meeting_link yet, the client gets an honest "we're finalizing the
    link" message instead of a dead URL, and the psychologist + all admins
    get an urgent alert so a human can fix it before the consultation
    starts. Returns True only if the CLIENT was actually reached."""

    psychologist_name = psychologist.name if psychologist else "психолог"
    service_title = (
        "15-минутный подбор специалистом"
        if getattr(booking, "booking_type", "consultation") == "selection_15min"
        else "Консультация психолога"
    )
    meeting_link = booking.meeting_link

    if meeting_link:
        client_text = (
            "Консультация скоро начнётся ✅\n\n"
            f"До начала осталось около 10 минут.\n"
            f"Услуга: {service_title}\n\n"
            f"Психолог: {psychologist_name}\n"
            f"Дата: {booking.date}\n"
            f"Время: {booking.start_time} (по Москве)\n"
            f"Длительность: {minutes_declension(booking.duration)}\n\n"
            f"Ссылка на встречу:\n{meeting_link}"
        )
    else:
        # Never promise a link that doesn't exist.
        client_text = (
            "Консультация скоро начнётся ✅\n\n"
            f"До начала осталось около 10 минут.\n"
            f"Услуга: {service_title}\n\n"
            f"Психолог: {psychologist_name}\n"
            f"Дата: {booking.date}\n"
            f"Время: {booking.start_time} (по Москве)\n"
            f"Длительность: {minutes_declension(booking.duration)}\n\n"
            "Ссылку на видеовстречу пришлём отдельным сообщением в ближайшие минуты."
        )

    client_ok = await send_message_safely(user.telegram_id, client_text)

    if psychologist and psychologist.telegram_id:
        if meeting_link:
            psychologist_text = (
                "Консультация скоро начнётся ✅\n\n"
                f"До начала осталось около 10 минут.\n"
                f"Услуга: {service_title}\n\n"
                f"Запись №{booking.id}\n"
                f"Дата: {booking.date}\n"
                f"Время: {booking.start_time} (по Москве)\n"
                f"Длительность: {minutes_declension(booking.duration)}\n"
                f"Клиент: {user.full_name or 'не указано'}\n"
                f"Телефон: {user.phone or 'не указан'}\n\n"
                f"Ссылка на встречу:\n{meeting_link}"
            )
        else:
            psychologist_text = (
                "СРОЧНО: не добавлена ссылка на встречу ⚠️\n\n"
                f"До консультации №{booking.id} осталось около 10 минут, "
                "а ссылка на видеовстречу ещё не добавлена.\n\n"
                f"Дата: {booking.date}\n"
                f"Время: {booking.start_time} (по Москве)\n"
                f"Клиент: {user.full_name or 'не указано'}\n"
                f"Телефон: {user.phone or 'не указан'}\n\n"
                "Пожалуйста, добавьте ссылку в кабинете психолога прямо сейчас: "
                "«Добавить/изменить ссылку встречи»."
            )
        await send_message_safely(psychologist.telegram_id, psychologist_text)

    if not meeting_link:
        await notify_admins(
            "Админ-уведомление ⚠️ Нет ссылки на встречу\n\n"
            f"Запись №{booking.id}, начало через ~10 минут, а meeting_link не заполнен.\n"
            f"Психолог: {psychologist_name}\n"
            f"Дата: {booking.date}\n"
            f"Время: {booking.start_time}"
        )

    return client_ok


async def process_booking_reminders_once() -> None:
    timezone = ZoneInfo(settings.timezone)
    now = datetime.now(timezone)

    async with async_session() as session:
        result = await session.execute(
            select(Booking).where(
                Booking.status == "paid",
                Booking.payment_status == "paid",
            )
        )

        bookings = result.scalars().all()

        for booking in bookings:
            try:
                start_at = get_booking_start_datetime(booking)
            except ValueError:
                continue

            user = await session.get(User, booking.user_id)
            psychologist = await session.get(Psychologist, booking.psychologist_id)

            if not user:
                continue

            time_until_start = start_at - now

            # Windows per spec: ~55-65 min out for the 1h reminder, ~7-12
            # min out for the 10m one - not "<= 60" (that would still fire
            # correctly at minute 14, sending a "1 hour" message).
            should_send_1h = is_within_reminder_window(
                time_until_start, settings.reminder_1h_min, settings.reminder_1h_max, booking.reminder_1h_sent
            )

            should_send_10m = is_within_reminder_window(
                time_until_start, settings.reminder_10m_min, settings.reminder_10m_max, booking.reminder_10m_sent
            )

            if should_send_1h:
                delivered = await send_booking_reminder_1h(booking, user, psychologist)
                if delivered:
                    booking.reminder_1h_sent = True
                    await session.commit()
                else:
                    print(f"1h reminder NOT marked sent for booking {booking.id}: delivery failed")

            if should_send_10m:
                delivered = await send_booking_reminder_10m(booking, user, psychologist)
                if delivered:
                    booking.reminder_10m_sent = True
                    await session.commit()
                else:
                    print(f"10m reminder NOT marked sent for booking {booking.id}: delivery failed")


async def reminders_loop() -> None:
    while True:
        try:
            await process_booking_reminders_once()
        except Exception as error:
            print(f"Reminder loop error: {error}")

        await asyncio.sleep(60)
