from app.database import async_session
from app.models.booking import Booking
from app.models.psychologist import Psychologist
from app.models.user import User
from app.services.admin_notifications import notify_admin_payment_success
from app.services.telegram_sender import send_message_safely
from app.services.answer_formatting import minutes_declension


async def send_payment_success_notifications(booking_id: int) -> None:
    async with async_session() as session:
        booking = await session.get(Booking, booking_id)

        if not booking:
            print(f"Notification failed: booking {booking_id} not found")
            return

        user = await session.get(User, booking.user_id)
        psychologist = await session.get(Psychologist, booking.psychologist_id)

        if not user:
            print(f"Notification failed: user for booking {booking_id} not found")
            return

        psychologist_name = psychologist.name if psychologist else "психолог"
        service_title = (
            "15-минутный подбор специалистом"
            if getattr(booking, "booking_type", "consultation") == "selection_15min"
            else "Консультация психолога"
        )

        client_text = (
            "Оплата прошла успешно ✅\n\n"
            f"Запись №{booking.id} подтверждена.\n"
            f"Услуга: {service_title}\n\n"
            f"Психолог: {psychologist_name}\n"
            f"Дата: {booking.date}\n"
            f"Время: {booking.start_time}\n"
            f"Длительность: {minutes_declension(booking.duration)}\n"
            f"Стоимость: {booking.price} ₽\n\n"
            "За 1 час до консультации бот пришлёт напоминание.\n"
            "За 10 минут до начала Вы получите ссылку на видеовстречу."
        )

        await send_message_safely(user.telegram_id, client_text)

        await notify_admin_payment_success(
            booking_id=booking.id,
            client_name=user.full_name or "не указано",
            psychologist_name=psychologist_name,
            date=booking.date,
            start_time=booking.start_time,
            amount=booking.price,
        )

        if psychologist and psychologist.telegram_id:
            psychologist_text = (
                "Новая оплаченная запись ✅\n\n"
                f"Запись №{booking.id}\n"
                f"Услуга: {service_title}\n"
                f"Дата: {booking.date}\n"
                f"Время: {booking.start_time}\n"
                f"Длительность: {minutes_declension(booking.duration)}\n"
                f"Стоимость: {booking.price} ₽\n\n"
                f"Клиент: {user.full_name or 'не указано'}\n"
                f"Телефон: {user.phone or 'не указан'}\n"
                f"Email: {user.email or 'не указан'}\n\n"
                "Ответы клиента можно посмотреть в разделе «Мои записи»."
            )

            await send_message_safely(psychologist.telegram_id, psychologist_text)


async def send_payment_cancelled_notification(booking_id: int) -> None:
    async with async_session() as session:
        booking = await session.get(Booking, booking_id)

        if not booking:
            return

        user = await session.get(User, booking.user_id)

        if not user:
            return

        text = (
            "Оплата не прошла или была отменена ⚠️\n\n"
            f"Запись №{booking.id} отменена.\n"
            "Слот снова стал доступен для выбора."
        )

        await send_message_safely(user.telegram_id, text)
