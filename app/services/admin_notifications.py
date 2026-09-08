from app.config import settings
from app.services.telegram_sender import send_message_safely


async def notify_admins(text: str) -> None:
    for admin_id in settings.admin_id_list:
        await send_message_safely(admin_id, text)


async def notify_admin_payment_success(
    booking_id: int,
    client_name: str,
    psychologist_name: str,
    date: str,
    start_time: str,
    amount: int,
) -> None:
    text = (
        "Админ-уведомление ✅\n\n"
        "Прошла успешная оплата.\n\n"
        f"Запись №{booking_id}\n"
        f"Клиент: {client_name}\n"
        f"Психолог: {psychologist_name}\n"
        f"Дата: {date}\n"
        f"Время: {start_time}\n"
        f"Сумма: {amount} ₽"
    )
    await notify_admins(text)


async def notify_admin_payment_problem(booking_id: int | None, reason: str) -> None:
    text = (
        "Админ-уведомление ⚠️\n\n"
        "Проблема с оплатой или записью.\n\n"
        f"Запись: {booking_id or 'не определена'}\n"
        f"Причина: {reason}"
    )
    await notify_admins(text)


async def notify_admin_booking_expired(
    booking_id: int,
    client_name: str,
    date: str,
    start_time: str,
) -> None:
    text = (
        "Админ-уведомление ⏳\n\n"
        "Резерв записи истёк без оплаты.\n\n"
        f"Запись №{booking_id}\n"
        f"Клиент: {client_name}\n"
        f"Дата: {date}\n"
        f"Время: {start_time}"
    )
    await notify_admins(text)
