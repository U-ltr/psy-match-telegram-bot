from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func

from app.config import settings
from app.database import async_session
from app.models.booking import Booking
from app.models.psychologist import Psychologist
from app.models.user import User
from app.services.pricing import format_durations_text
from app.services.answer_formatting import format_client_answers, format_booking_status, format_code_list, years_declension, minutes_declension, records_declension
from app.keyboards.psychologist import SPECIALIZATION_OPTIONS, HELP_TOPIC_OPTIONS
from app.models.payout import Payout
from app.services.payouts import (
    get_payouts_summary,
    get_all_payouts,
    mark_payout_ready,
    mark_payout_paid,
)


router = Router(name="admin")


class AdminPanelStates(StatesGroup):
    waiting_add_psychologist_telegram_id = State()
    waiting_add_psychologist_name = State()
    waiting_remove_psychologist_id = State()


def admin_user_ids() -> list[int]:
    raw_admin_ids = (
        getattr(settings, "admin_ids", None)
        or getattr(settings, "ADMIN_IDS", None)
        or []
    )

    if isinstance(raw_admin_ids, str):
        return [
            int(item.strip())
            for item in raw_admin_ids.split(",")
            if item.strip().isdigit()
        ]

    if isinstance(raw_admin_ids, list):
        return [int(item) for item in raw_admin_ids]

    return [1022067924]


def is_admin_user(user_id: int) -> bool:
    return int(user_id) in admin_user_ids()


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Психологи", callback_data="admin4:psychologists")],
            [InlineKeyboardButton(text="Добавить психолога", callback_data="admin4:add_psychologist")],
            [InlineKeyboardButton(text="Убрать психолога", callback_data="admin4:remove_psychologist")],
            [InlineKeyboardButton(text="Записи", callback_data="admin4:bookings")],
            [InlineKeyboardButton(text="Финансы", callback_data="admin4:finance")],
            [InlineKeyboardButton(text="Назад в главное меню", callback_data="admin4:back_to_main")],
        ]
    )


def admin_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад в админ-панель", callback_data="admin4:menu")],
        ]
    )


def admin_psychologists_keyboard(psychologists: list[Psychologist]) -> InlineKeyboardMarkup:
    rows = []

    for psychologist in psychologists[:30]:
        status = "✅" if psychologist.is_active else "🚫"
        rows.append([
            InlineKeyboardButton(
                text=f"{status} ID {psychologist.id}: {psychologist.name or 'Без имени'}",
                callback_data=f"admin4:psychologist:{psychologist.id}",
            )
        ])

    rows.append([InlineKeyboardButton(text="Назад в админ-панель", callback_data="admin4:menu")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_psychologist_card_keyboard(psychologist_id: int, is_active: bool) -> InlineKeyboardMarkup:
    action_text = "Убрать психолога" if is_active else "Вернуть психолога"
    action_callback = (
        f"admin4:deactivate_psychologist:{psychologist_id}"
        if is_active
        else f"admin4:activate_psychologist:{psychologist_id}"
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=action_text, callback_data=action_callback)],
            [InlineKeyboardButton(text="Назад к психологам", callback_data="admin4:psychologists")],
            [InlineKeyboardButton(text="Назад в админ-панель", callback_data="admin4:menu")],
        ]
    )


def format_psychologist_card(psychologist: Psychologist, bookings_count: int = 0) -> str:
    status = "активен ✅" if psychologist.is_active else "убран 🚫"

    durations = format_durations_text(psychologist.durations)

    # Same centralized labels as everywhere else - see format_code_list's
    # docstring. This admin card used to join the raw codes directly
    # (e.g. "family_therapist"), which is exactly the kind of leak that
    # must never happen in an admin view either.
    specializations = format_code_list(psychologist.specializations or [], SPECIALIZATION_OPTIONS)
    help_topics = format_code_list(getattr(psychologist, "help_topics", []) or [], HELP_TOPIC_OPTIONS)

    return (
        "Психолог\n\n"
        f"ID: {psychologist.id}\n"
        f"Telegram ID: {psychologist.telegram_id}\n"
        f"Имя: {psychologist.name or 'не указано'}\n"
        f"Статус: {status}\n"
        f"Опыт: {years_declension(psychologist.experience_years or 0)}\n"
        f"Длительности и цены:\n{durations}\n"
        f"Специализация: {specializations}\n"
        f"С чем помогает: {help_topics}\n"
        f"Записей: {bookings_count}\n"
    )


def format_booking_for_admin(booking: Booking, psychologist: Psychologist, user: User) -> str:
    client_name = (
        getattr(user, "full_name", None)
        or getattr(user, "username", None)
        or getattr(user, "telegram_id", None)
        or "не указан"
    )

    client_phone = getattr(user, "phone", None) or "не указан"

    psychologist_name = (
        getattr(psychologist, "name", None)
        or f"ID {getattr(psychologist, 'id', '—')}"
    )

    answers = getattr(booking, "client_answers", None)
    comment = getattr(booking, "client_comment", None)
    answers_text = format_client_answers(answers, comment)

    return (
        f"Запись №{getattr(booking, 'id', '—')}\n"
        f"Дата: {getattr(booking, 'date', '—')}\n"
        f"Время: {getattr(booking, 'start_time', '—')}\n"
        f"Длительность: {minutes_declension(getattr(booking, 'duration', 0)) if getattr(booking, 'duration', None) is not None else '—'}\n"
        f"Психолог: {psychologist_name}\n"
        f"Клиент: {client_name}\n"
        f"Телефон: {client_phone}\n"
        f"Статус: {format_booking_status(getattr(booking, 'status', None), getattr(booking, 'payment_status', None))}\n"
        f"Ссылка: {getattr(booking, 'meeting_link', None) or 'не добавлена'}\n"
        f"{answers_text}"
    )


async def answer_admin_panel(message_or_callback) -> None:
    target_message = (
        message_or_callback
        if isinstance(message_or_callback, Message)
        else message_or_callback.message
    )

    await target_message.answer(
        "Админ-панель\n\nВыберите действие:",
        reply_markup=admin_panel_keyboard(),
    )


@router.message(Command("admin"))
async def admin_command_handler(message: Message, state: FSMContext) -> None:
    await state.clear()

    if not is_admin_user(message.from_user.id):
        await message.answer("У Вас нет доступа к админ-панели.")
        return

    await answer_admin_panel(message)


@router.callback_query(F.data == "admin4:menu")
async def admin_menu_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()

    if not is_admin_user(callback.from_user.id):
        await callback.message.answer("У Вас нет доступа к админ-панели.")
        return

    await answer_admin_panel(callback)


@router.callback_query(F.data == "admin4:back_to_main")
async def admin_back_to_main_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()

    try:
        from app.keyboards.client import main_menu_keyboard

        await callback.message.answer(
            "Главное меню\n\nВыберите действие:",
            reply_markup=main_menu_keyboard(),
        )
    except Exception:
        await callback.message.answer(
            "Главное меню\n\nЧтобы открыть клиентское меню, отправьте /start."
        )


@router.callback_query(F.data == "admin4:psychologists")
async def admin_psychologists_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    if not is_admin_user(callback.from_user.id):
        await callback.message.answer("У Вас нет доступа к админ-панели.")
        return

    async with async_session() as session:
        result = await session.execute(
            select(Psychologist).order_by(Psychologist.id)
        )
        psychologists = result.scalars().all()

    if not psychologists:
        await callback.message.answer(
            "Психологов пока нет.",
            reply_markup=admin_back_keyboard(),
        )
        return

    active_count = sum(1 for psychologist in psychologists if psychologist.is_active)
    inactive_count = len(psychologists) - active_count

    text = (
        "Психологи\n\n"
        f"Всего: {len(psychologists)}\n"
        f"Активных: {active_count}\n"
        f"Убранных: {inactive_count}\n\n"
        "Нажмите на психолога, чтобы открыть карточку."
    )

    await callback.message.answer(
        text,
        reply_markup=admin_psychologists_keyboard(psychologists),
    )


@router.callback_query(F.data.startswith("admin4:psychologist:"))
async def admin_psychologist_card_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    if not is_admin_user(callback.from_user.id):
        await callback.message.answer("У Вас нет доступа к админ-панели.")
        return

    psychologist_id = int(callback.data.split(":")[-1])

    async with async_session() as session:
        psychologist = await session.get(Psychologist, psychologist_id)

        if not psychologist:
            await callback.message.answer(
                "Психолог не найден.",
                reply_markup=admin_back_keyboard(),
            )
            return

        count_result = await session.execute(
            select(func.count(Booking.id)).where(Booking.psychologist_id == psychologist.id)
        )
        bookings_count = count_result.scalar() or 0

    await callback.message.answer(
        format_psychologist_card(psychologist, bookings_count),
        reply_markup=admin_psychologist_card_keyboard(
            psychologist.id,
            psychologist.is_active,
        ),
    )


@router.callback_query(F.data == "admin4:add_psychologist")
async def admin_add_psychologist_start_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    if not is_admin_user(callback.from_user.id):
        await callback.message.answer("У Вас нет доступа к админ-панели.")
        return

    await state.set_state(AdminPanelStates.waiting_add_psychologist_telegram_id)

    await callback.message.answer(
        "Добавление психолога\n\n"
        "Введите Telegram ID психолога.\n\n"
        "Например: 1022067924",
        reply_markup=admin_back_keyboard(),
    )


@router.message(AdminPanelStates.waiting_add_psychologist_telegram_id)
async def admin_add_psychologist_telegram_id_handler(message: Message, state: FSMContext) -> None:
    if not is_admin_user(message.from_user.id):
        await state.clear()
        await message.answer("У Вас нет доступа к админ-панели.")
        return

    telegram_id_raw = (message.text or "").strip()

    if not telegram_id_raw.isdigit():
        await message.answer("Введите Telegram ID числом. Например: 1022067924")
        return

    telegram_id = int(telegram_id_raw)

    async with async_session() as session:
        result = await session.execute(
            select(Psychologist).where(Psychologist.telegram_id == telegram_id)
        )
        existing_psychologist = result.scalar_one_or_none()

    if existing_psychologist:
        await state.clear()
        await message.answer(
            "Психолог с таким Telegram ID уже есть.\n\n"
            f"ID: {existing_psychologist.id}\n"
            f"Имя: {existing_psychologist.name or 'не указано'}",
            reply_markup=admin_panel_keyboard(),
        )
        return

    await state.update_data(new_psychologist_telegram_id=telegram_id)
    await state.set_state(AdminPanelStates.waiting_add_psychologist_name)

    await message.answer(
        "Теперь введите имя психолога.\n\n"
        "Например: Анна Смирнова"
    )


@router.message(AdminPanelStates.waiting_add_psychologist_name)
async def admin_add_psychologist_name_handler(message: Message, state: FSMContext) -> None:
    if not is_admin_user(message.from_user.id):
        await state.clear()
        await message.answer("У Вас нет доступа к админ-панели.")
        return

    name = (message.text or "").strip()

    if not name:
        await message.answer("Имя не должно быть пустым.")
        return

    data = await state.get_data()
    telegram_id = data.get("new_psychologist_telegram_id")

    if not telegram_id:
        await state.clear()
        await message.answer(
            "Не нашёл Telegram ID. Начните добавление заново.",
            reply_markup=admin_panel_keyboard(),
        )
        return

    async with async_session() as session:
        psychologist = Psychologist(
            telegram_id=int(telegram_id),
            name=name,
            is_active=True,
            gender=None,
            experience_years=0,
            durations=[],
            specializations=[],
            help_topics=[],
            styles=[],
            education="",
            description="",
        )

        session.add(psychologist)
        await session.commit()
        await session.refresh(psychologist)

    await state.clear()

    await message.answer(
        "Психолог добавлен ✅\n\n"
        f"ID: {psychologist.id}\n"
        f"Telegram ID: {psychologist.telegram_id}\n"
        f"Имя: {psychologist.name}\n\n"
        "Теперь психолог может открыть кабинет командой /psychologist и заполнить анкету.",
        reply_markup=admin_panel_keyboard(),
    )


@router.callback_query(F.data == "admin4:remove_psychologist")
async def admin_remove_psychologist_start_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    if not is_admin_user(callback.from_user.id):
        await callback.message.answer("У Вас нет доступа к админ-панели.")
        return

    await state.set_state(AdminPanelStates.waiting_remove_psychologist_id)

    await callback.message.answer(
        "Введите ID психолога, которого нужно убрать.\n\n"
        "Например: 3",
        reply_markup=admin_back_keyboard(),
    )


@router.message(AdminPanelStates.waiting_remove_psychologist_id)
async def admin_remove_psychologist_value_handler(message: Message, state: FSMContext) -> None:
    if not is_admin_user(message.from_user.id):
        await state.clear()
        await message.answer("У Вас нет доступа к админ-панели.")
        return

    raw_id = (message.text or "").strip()

    if not raw_id.isdigit():
        await message.answer("Введите ID психолога числом. Например: 3")
        return

    psychologist_id = int(raw_id)

    async with async_session() as session:
        psychologist = await session.get(Psychologist, psychologist_id)

        if not psychologist:
            await state.clear()
            await message.answer(
                "Психолог с таким ID не найден.",
                reply_markup=admin_panel_keyboard(),
            )
            return

        psychologist.is_active = False
        await session.commit()

    await state.clear()

    await message.answer(
        f"Психолог ID {psychologist_id} убран ✅\n\n"
        "Он больше не будет показываться клиентам.",
        reply_markup=admin_panel_keyboard(),
    )


@router.callback_query(F.data.startswith("admin4:deactivate_psychologist:"))
async def admin_deactivate_psychologist_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    if not is_admin_user(callback.from_user.id):
        await callback.message.answer("У Вас нет доступа к админ-панели.")
        return

    psychologist_id = int(callback.data.split(":")[-1])

    async with async_session() as session:
        psychologist = await session.get(Psychologist, psychologist_id)

        if not psychologist:
            await callback.message.answer(
                "Психолог не найден.",
                reply_markup=admin_panel_keyboard(),
            )
            return

        psychologist.is_active = False
        await session.commit()

    await callback.message.answer(
        f"Психолог ID {psychologist_id} убран ✅",
        reply_markup=admin_panel_keyboard(),
    )


@router.callback_query(F.data.startswith("admin4:activate_psychologist:"))
async def admin_activate_psychologist_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    if not is_admin_user(callback.from_user.id):
        await callback.message.answer("У Вас нет доступа к админ-панели.")
        return

    psychologist_id = int(callback.data.split(":")[-1])

    async with async_session() as session:
        psychologist = await session.get(Psychologist, psychologist_id)

        if not psychologist:
            await callback.message.answer(
                "Психолог не найден.",
                reply_markup=admin_panel_keyboard(),
            )
            return

        psychologist.is_active = True
        await session.commit()

    await callback.message.answer(
        f"Психолог ID {psychologist_id} снова активен ✅",
        reply_markup=admin_panel_keyboard(),
    )


@router.callback_query(F.data == "admin4:bookings")
async def admin_bookings_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    if not is_admin_user(callback.from_user.id):
        await callback.message.answer("У Вас нет доступа к админ-панели.")
        return

    async with async_session() as session:
        result = await session.execute(
            select(Booking, Psychologist, User)
            .join(Psychologist, Psychologist.id == Booking.psychologist_id)
            .join(User, User.id == Booking.user_id)
            .order_by(Booking.date.desc(), Booking.start_time.desc())
            .limit(30)
        )
        rows = result.all()

    if not rows:
        await callback.message.answer(
            "Записей пока нет.",
            reply_markup=admin_panel_keyboard(),
        )
        return

    await callback.message.answer(
        f"Записи 📋\n\nНайдено: {records_declension(len(rows))}\nПоказываю карточками по 5 записей."
    )

    chunk = []
    chunk_size = 5

    for booking, psychologist, user in rows:
        chunk.append(format_booking_for_admin(booking, psychologist, user))

        if len(chunk) == chunk_size:
            await callback.message.answer(
                "\n━━━━━━━━━━━━━━\n\n".join(chunk)
            )
            chunk = []

    if chunk:
        await callback.message.answer(
            "\n━━━━━━━━━━━━━━\n\n".join(chunk)
        )

    await callback.message.answer(
        "Действия админ-панели:",
        reply_markup=admin_panel_keyboard(),
    )


PAYOUT_STATUS_LABELS = {
    "pending": "Ожидает подготовки",
    "ready": "Готово к выплате",
    "paid": "Выплачено",
    "cancelled": "Отменено",
}


def format_finance_summary(summary: dict) -> str:
    by_status = summary["by_status"]
    return (
        "Финансы 💰\n\n"
        f"Всего оплаченных: {records_declension(sum(by_status.values()))}\n"
        f"Общая сумма оплат: {summary['total_gross']} ₽\n"
        f"Комиссия платформы: {summary['total_commission']} ₽\n"
        f"Причитается психологам: {summary['total_psychologist_amount']} ₽\n"
        f"Не выплачено (ожидает/готово): {summary['owed_unpaid']} ₽\n\n"
        f"Ожидает подготовки: {by_status.get('pending', 0)}\n"
        f"Готово к выплате: {by_status.get('ready', 0)}\n"
        f"Выплачено: {by_status.get('paid', 0)}\n"
        f"Отменено: {by_status.get('cancelled', 0)}\n\n"
        f"Текущий процент комиссии по умолчанию: {settings.platform_commission_percent}% "
        "(задаётся переменной окружения PLATFORM_COMMISSION_PERCENT; "
        "значение не подтверждено бизнесом и требует явного решения владельца)."
    )


def format_payout_card(payout: Payout, psychologist_name: str) -> str:
    return (
        f"Выплата №{payout.id} (запись №{payout.booking_id})\n"
        f"Психолог: {psychologist_name}\n"
        f"Статус: {PAYOUT_STATUS_LABELS.get(payout.status, payout.status)}\n"
        f"Сумма оплаты: {payout.gross_amount} ₽\n"
        f"Комиссия ({payout.commission_percent}%): {payout.commission_amount} ₽\n"
        f"К выплате психологу: {payout.psychologist_amount} ₽"
    )


def payout_action_keyboard(payout: Payout) -> InlineKeyboardMarkup | None:
    if payout.status == "pending":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Отметить «готово к выплате»", callback_data=f"admin4:payout_ready:{payout.id}")],
            ]
        )
    if payout.status == "ready":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Отметить «выплачено»", callback_data=f"admin4:payout_paid:{payout.id}")],
            ]
        )
    return None


@router.callback_query(F.data == "admin4:finance")
async def admin_finance_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    if not is_admin_user(callback.from_user.id):
        await callback.message.answer("У Вас нет доступа к админ-панели.")
        return

    summary = await get_payouts_summary()
    await callback.message.answer(format_finance_summary(summary))

    async with async_session() as session:
        psychologists = (await session.execute(select(Psychologist))).scalars().all()
    names_by_id = {p.id: p.name for p in psychologists}

    actionable = [
        payout for payout in await get_all_payouts()
        if payout.status in ("pending", "ready")
    ][:20]

    if not actionable:
        await callback.message.answer(
            "Нет выплат, ожидающих действия.",
            reply_markup=admin_panel_keyboard(),
        )
        return

    await callback.message.answer("Выплаты, ожидающие действия:")

    for payout in actionable:
        psychologist_name = names_by_id.get(payout.psychologist_id, f"ID {payout.psychologist_id}")
        await callback.message.answer(
            format_payout_card(payout, psychologist_name),
            reply_markup=payout_action_keyboard(payout),
        )

    await callback.message.answer(
        "Действия админ-панели:",
        reply_markup=admin_panel_keyboard(),
    )


@router.callback_query(F.data.startswith("admin4:payout_ready:"))
async def admin_payout_ready_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    if not is_admin_user(callback.from_user.id):
        await callback.message.answer("У Вас нет доступа к админ-панели.")
        return

    payout_id = int(callback.data.split(":")[-1])
    ok = await mark_payout_ready(payout_id)

    await callback.message.answer(
        "Выплата помечена как готовая ✅" if ok else "Не удалось изменить статус выплаты.",
        reply_markup=admin_panel_keyboard(),
    )


@router.callback_query(F.data.startswith("admin4:payout_paid:"))
async def admin_payout_paid_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    if not is_admin_user(callback.from_user.id):
        await callback.message.answer("У Вас нет доступа к админ-панели.")
        return

    payout_id = int(callback.data.split(":")[-1])
    ok = await mark_payout_paid(payout_id)

    await callback.message.answer(
        "Выплата отмечена как выплаченная ✅" if ok else "Не удалось изменить статус выплаты.",
        reply_markup=admin_panel_keyboard(),
    )
