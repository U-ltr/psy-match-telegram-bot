import asyncio
import logging

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.database import check_db_connection
from app.error_handling import handle_unexpected_error
from app.handlers.admin import router as admin_router
from app.handlers.client import router as client_router
from app.handlers.psychologist import router as psychologist_router
from app.payment_webhook import start_payment_webhook_server
from app.services.reminders import reminders_loop
from app.services.yookassa_payments import yookassa_payments_sync_loop
from app.services.unpaid_bookings import unpaid_bookings_loop
from app.services.telegram_sender import get_shared_bot, close_shared_bot


logging.basicConfig(level=logging.INFO)


async def main() -> None:
    await check_db_connection()

    # One Bot/aiohttp session for the whole process - polling and every
    # outbound send (reminders, notifications) share it. See
    # services/telegram_sender.py.
    bot = await get_shared_bot()
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(admin_router)
    dp.include_router(psychologist_router)
    dp.include_router(client_router)

    dp.error.register(handle_unexpected_error)

    logging.info("Bot started")
    logging.info("Admin IDs: %s", settings.admin_id_list)

    try:
        await asyncio.gather(
            dp.start_polling(bot),
            start_payment_webhook_server(),
            reminders_loop(),
            yookassa_payments_sync_loop(),
            unpaid_bookings_loop(),
        )
    finally:
        await close_shared_bot()


if __name__ == "__main__":
    asyncio.run(main())
