from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from app.database import async_session
from app.models.booking import Booking
from app.models.psychologist import Psychologist
from app.models.user import User
from app.models.working_interval import WorkingInterval
from app.services.telegram_sender import send_message_safely

from app.keyboards.psychologist import (
    SPECIALIZATION_OPTIONS,
    HELP_TOPIC_OPTIONS,
    STYLE_OPTIONS,
)
from app.services.psychologist_profile import get_psychologist_by_telegram_id
from app.services.pricing import normalize_durations, format_durations_text, upsert_duration, remove_duration, get_priced_durations
from app.services.answer_formatting import format_client_answers, format_booking_status, format_code_list, CUSTOM_OPTION_PREFIX, years_declension, minutes_declension
from app.texts.psychologist import NO_PSYCHOLOGIST_ACCESS_TEXT


router = Router(name="psychologist")


# === PSYCHOLOGIST CABINET V4 START ===

# Shared by the "add your own option" / "remove your own option" handlers
# below - one place mapping a keyboard prefix ("specialization" etc, the
# same prefix psych4:toggle_<prefix>:<key> already used) to the model
# field it edits and the fixed catalog for that field.
PROFILE_LIST_FIELDS = {
    "specialization": ("specializations", SPECIALIZATION_OPTIONS),
    "help_topic": ("help_topics", HELP_TOPIC_OPTIONS),
    "style": ("styles", STYLE_OPTIONS),
}


class PsychologistCabinetV4States(StatesGroup):
    waiting_profile_value = State()
    waiting_profile_photo = State()
    waiting_duration_value = State()
    waiting_custom_option_value = State()

    waiting_schedule_date = State()
    waiting_schedule_start = State()
    waiting_schedule_end = State()

    waiting_link_booking_id = State()
    waiting_link_value = State()


def psych4_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Анкета", callback_data="psych4:profile")],
            [InlineKeyboardButton(text="Расписание", callback_data="psych4:schedule")],
            [InlineKeyboardButton(text="Записи", callback_data="psych4:bookings")],
            [InlineKeyboardButton(text="Добавить/изменить ссылку встречи", callback_data="psych4:meeting_link")],
        ]
    )


def psych4_profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Редактировать анкету", callback_data="psych4:edit_profile")],
            [InlineKeyboardButton(text="Назад в кабинет психолога", callback_data="psych4:menu")],
        ]
    )


def psych4_edit_profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Имя", callback_data="psych4:edit_field:name")],
            [InlineKeyboardButton(text="Фото", callback_data="psych4:edit_field:photo_file_id")],
            [InlineKeyboardButton(text="Описание", callback_data="psych4:edit_field:description")],
            [InlineKeyboardButton(text="Образование", callback_data="psych4:edit_field:education")],
            [InlineKeyboardButton(text="Опыт", callback_data="psych4:edit_field:experience_years")],
            [InlineKeyboardButton(text="Пол", callback_data="psych4:edit_gender")],
            [InlineKeyboardButton(text="Специализация", callback_data="psych4:edit_specializations")],
            [InlineKeyboardButton(text="С чем могу помочь", callback_data="psych4:edit_help_topics")],
            [InlineKeyboardButton(text="Стиль работы", callback_data="psych4:edit_styles")],
            [InlineKeyboardButton(text="Длительности и цены", callback_data="psych4:edit_durations")],
            [InlineKeyboardButton(text="Назад к анкете", callback_data="psych4:profile")],
        ]
    )


def psych4_schedule_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Редактировать расписание", callback_data="psych4:edit_schedule")],
            [InlineKeyboardButton(text="Назад в кабинет психолога", callback_data="psych4:menu")],
        ]
    )


def psych4_edit_schedule_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Добавить свободный интервал", callback_data="psych4:add_interval")],
            [InlineKeyboardButton(text="Удалить свободный интервал", callback_data="psych4:delete_interval_menu")],
            [InlineKeyboardButton(text="Назад к расписанию", callback_data="psych4:schedule")],
        ]
    )


def psych4_gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Женщина", callback_data="psych4:set_gender:female"),
                InlineKeyboardButton(text="Мужчина", callback_data="psych4:set_gender:male"),
            ],
            [InlineKeyboardButton(text="Назад к редактированию анкеты", callback_data="psych4:edit_profile")],
        ]
    )


def psych4_durations_menu_keyboard(durations: list[dict]) -> InlineKeyboardMarkup:
    rows = []

    for item in durations:
        label = f"{item['minutes']} мин — {item['price']} ₽" if item["price"] else f"{item['minutes']} мин — цена не задана"
        rows.append([
            InlineKeyboardButton(text=label, callback_data=f"psych4:edit_one_duration:{item['minutes']}"),
            InlineKeyboardButton(text="✕", callback_data=f"psych4:remove_duration:{item['minutes']}"),
        ])

    rows.append([InlineKeyboardButton(text="➕ Добавить длительность", callback_data="psych4:add_duration")])
    rows.append([InlineKeyboardButton(text="Назад к анкете", callback_data="psych4:profile")])
    rows.append([InlineKeyboardButton(text="Назад к редактированию анкеты", callback_data="psych4:edit_profile")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def psych4_options_keyboard(prefix: str, options: dict, selected: list | None = None) -> InlineKeyboardMarkup:
    selected = selected or []
    rows = []

    for key, label in options.items():
        mark = "✅ " if key in selected else ""
        rows.append([
            InlineKeyboardButton(
                text=f"{mark}{label}",
                callback_data=f"psych4:toggle_{prefix}:{key}",
            )
        ])

    # Psychologist-authored free-text options, on top of the fixed catalog
    # above - stored inline with a CUSTOM_OPTION_PREFIX marker (see
    # app.services.answer_formatting.format_code_list). Each gets its own
    # row with a single tap to remove it (index-based callback_data, since
    # Telegram's 64-byte limit rules out embedding arbitrary text there).
    # Same tap-to-remove interaction as the predefined options above (a
    # checked "✅ ..." row toggles off when tapped) - no separate wording
    # needed, the pattern is already established by the rows right above it.
    custom_values = [value for value in selected if value.startswith(CUSTOM_OPTION_PREFIX)]
    for index, value in enumerate(custom_values):
        label = value[len(CUSTOM_OPTION_PREFIX):]
        rows.append([
            InlineKeyboardButton(
                text=f"✅ {label}",
                callback_data=f"psych4:remove_custom_{prefix}:{index}",
            )
        ])

    rows.append([InlineKeyboardButton(text="➕ Свой вариант", callback_data=f"psych4:add_custom_{prefix}")])
    rows.append([InlineKeyboardButton(text="Готово", callback_data="psych4:profile")])
    rows.append([InlineKeyboardButton(text="Назад к редактированию анкеты", callback_data="psych4:edit_profile")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def psych4_format_profile_text(psychologist) -> str:
    specializations = format_code_list(psychologist.specializations or [], SPECIALIZATION_OPTIONS)
    help_topics = format_code_list(getattr(psychologist, "help_topics", []) or [], HELP_TOPIC_OPTIONS)
    styles = format_code_list(psychologist.styles or [], STYLE_OPTIONS)

    gender = {
        "female": "Женщина",
        "male": "Мужчина",
    }.get(psychologist.gender, "не указано")

    return (
        "Анкета\n\n"
        f"Имя: {psychologist.name or 'не указано'}\n"
        f"Пол: {gender}\n"
        f"Опыт: {years_declension(psychologist.experience_years or 0)}\n"
        f"Длительности и цены:\n{format_durations_text(psychologist.durations)}\n\n"
        f"Специализация: {specializations}\n\n"
        f"С чем могу помочь: {help_topics}\n\n"
        f"Стиль работы: {styles}\n\n"
        f"Образование:\n{psychologist.education or 'не указано'}\n\n"
        f"Описание:\n{psychologist.description or 'не указано'}"
    )


def psych4_format_client_answers(booking) -> str:
    answers = getattr(booking, "client_answers", None)
    comment = getattr(booking, "client_comment", None)
    return format_client_answers(answers, comment)


async def psych4_get_psychologist_or_answer(message_or_callback):
    user_id = message_or_callback.from_user.id
    psychologist = await get_psychologist_by_telegram_id(user_id)

    if not psychologist:
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(NO_PSYCHOLOGIST_ACCESS_TEXT)
        else:
            await message_or_callback.message.answer(NO_PSYCHOLOGIST_ACCESS_TEXT)
        return None

    return psychologist


@router.message(Command("psychologist"))
async def psych4_psychologist_command(message: Message, state: FSMContext) -> None:
    await state.clear()

    psychologist = await psych4_get_psychologist_or_answer(message)

    if not psychologist:
        return

    await message.answer(
        "Кабинет психолога\n\nВыберите действие:",
        reply_markup=psych4_main_keyboard(),
    )


@router.callback_query(F.data == "psych4:menu")
async def psych4_menu_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()

    await callback.message.answer(
        "Кабинет психолога\n\nВыберите действие:",
        reply_markup=psych4_main_keyboard(),
    )


@router.callback_query(F.data == "psych4:profile")
async def psych4_profile_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()

    psychologist = await psych4_get_psychologist_or_answer(callback)

    if not psychologist:
        return

    photo_file_id = getattr(psychologist, "photo_file_id", None)
    text = psych4_format_profile_text(psychologist)

    if photo_file_id:
        await callback.message.answer_photo(
            photo=photo_file_id,
            caption="Фото анкеты",
        )

    await callback.message.answer(
        text,
        reply_markup=psych4_profile_keyboard(),
    )


@router.callback_query(F.data == "psych4:edit_profile")
async def psych4_edit_profile_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()

    await callback.message.answer(
        "Редактирование анкеты\n\nВыберите поле:",
        reply_markup=psych4_edit_profile_keyboard(),
    )


@router.callback_query(F.data.startswith("psych4:edit_field:"))
async def psych4_edit_field_start_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    field = callback.data.split(":")[-1]

    titles = {
        "name": "имя",
        "photo_file_id": "фото",
        "description": "описание",
        "education": "образование",
        "experience_years": "опыт в годах",
    }

    if field == "photo_file_id":
        await state.set_state(PsychologistCabinetV4States.waiting_profile_photo)
        await callback.message.answer("Пришлите новое фото анкеты.")
        return

    await state.set_state(PsychologistCabinetV4States.waiting_profile_value)
    await state.update_data(profile_field=field)

    await callback.message.answer(f"Введите новое значение поля: {titles.get(field, field)}")


@router.message(PsychologistCabinetV4States.waiting_profile_photo, F.photo)
async def psych4_profile_photo_handler(message: Message, state: FSMContext) -> None:
    psychologist = await psych4_get_psychologist_or_answer(message)

    if not psychologist:
        await state.clear()
        return

    photo_file_id = message.photo[-1].file_id

    async with async_session() as session:
        db_psychologist = await session.get(Psychologist, psychologist.id)
        db_psychologist.photo_file_id = photo_file_id
        await session.commit()

    await state.clear()

    psychologist = await get_psychologist_by_telegram_id(message.from_user.id)

    await message.answer("Фото обновлено ✅")
    await message.answer_photo(photo=photo_file_id, caption="Фото анкеты")
    await message.answer(
        psych4_format_profile_text(psychologist),
        reply_markup=psych4_profile_keyboard(),
    )


@router.message(PsychologistCabinetV4States.waiting_profile_photo)
async def psych4_profile_photo_wrong_handler(message: Message) -> None:
    await message.answer("Пожалуйста, пришлите именно фото.")


@router.message(PsychologistCabinetV4States.waiting_profile_value)
async def psych4_profile_value_handler(message: Message, state: FSMContext) -> None:
    psychologist = await psych4_get_psychologist_or_answer(message)

    if not psychologist:
        await state.clear()
        return

    data = await state.get_data()
    field = data.get("profile_field")
    value = (message.text or "").strip()

    if not value:
        await message.answer("Значение не должно быть пустым.")
        return

    if field in {"experience_years"}:
        if not value.isdigit():
            await message.answer("Введите число.")
            return
        value = int(value)

    allowed_fields = {
        "name",
        "description",
        "education",
        "experience_years",
    }

    if field not in allowed_fields:
        await state.clear()
        await message.answer("Неизвестное поле анкеты.")
        return

    async with async_session() as session:
        db_psychologist = await session.get(Psychologist, psychologist.id)
        setattr(db_psychologist, field, value)
        await session.commit()

    await state.clear()

    psychologist = await get_psychologist_by_telegram_id(message.from_user.id)

    await message.answer("Анкета обновлена ✅")
    photo_file_id = getattr(psychologist, "photo_file_id", None)

    if photo_file_id:
        await message.answer_photo(photo=photo_file_id, caption="Фото анкеты")

    await message.answer(
        psych4_format_profile_text(psychologist),
        reply_markup=psych4_profile_keyboard(),
    )


@router.callback_query(F.data == "psych4:edit_gender")
async def psych4_edit_gender_handler(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        "Выберите пол:",
        reply_markup=psych4_gender_keyboard(),
    )


@router.callback_query(F.data.startswith("psych4:set_gender:"))
async def psych4_set_gender_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    gender = callback.data.split(":")[-1]
    psychologist = await psych4_get_psychologist_or_answer(callback)

    if not psychologist:
        return

    async with async_session() as session:
        db_psychologist = await session.get(Psychologist, psychologist.id)
        db_psychologist.gender = gender
        await session.commit()

    await callback.message.answer(
        "Пол обновлён ✅",
        reply_markup=psych4_edit_profile_keyboard(),
    )


@router.callback_query(F.data == "psych4:edit_specializations")
async def psych4_edit_specializations_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    psychologist = await psych4_get_psychologist_or_answer(callback)

    if not psychologist:
        return

    await callback.message.answer(
        "Выберите специализации. Можно нажимать несколько вариантов:",
        reply_markup=psych4_options_keyboard(
            "specialization",
            SPECIALIZATION_OPTIONS,
            psychologist.specializations or [],
        ),
    )


@router.callback_query(F.data.startswith("psych4:toggle_specialization:"))
async def psych4_toggle_specialization_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    key = callback.data.split(":")[-1]
    psychologist = await psych4_get_psychologist_or_answer(callback)

    if not psychologist:
        return

    current = list(psychologist.specializations or [])

    if key in current:
        current.remove(key)
    else:
        current.append(key)

    async with async_session() as session:
        db_psychologist = await session.get(Psychologist, psychologist.id)
        db_psychologist.specializations = current
        await session.commit()

    psychologist = await get_psychologist_by_telegram_id(callback.from_user.id)

    await callback.message.answer(
        "Специализации обновлены ✅",
        reply_markup=psych4_options_keyboard(
            "specialization",
            SPECIALIZATION_OPTIONS,
            psychologist.specializations or [],
        ),
    )


@router.callback_query(F.data == "psych4:edit_help_topics")
async def psych4_edit_help_topics_handler(callback: CallbackQuery) -> None:
    await callback.answer()
    psychologist = await psych4_get_psychologist_or_answer(callback)
    if not psychologist:
        return
    await callback.message.answer(
        "Выберите запросы, с которыми Вы помогаете. Можно выбрать несколько вариантов:",
        reply_markup=psych4_options_keyboard(
            "help_topic",
            HELP_TOPIC_OPTIONS,
            psychologist.help_topics or [],
        ),
    )


@router.callback_query(F.data.startswith("psych4:toggle_help_topic:"))
async def psych4_toggle_help_topic_handler(callback: CallbackQuery) -> None:
    await callback.answer()
    key = callback.data.split(":")[-1]
    psychologist = await psych4_get_psychologist_or_answer(callback)
    if not psychologist:
        return
    current = list(psychologist.help_topics or [])
    if key in current:
        current.remove(key)
    else:
        current.append(key)
    async with async_session() as session:
        db_psychologist = await session.get(Psychologist, psychologist.id)
        db_psychologist.help_topics = current
        await session.commit()
    psychologist = await get_psychologist_by_telegram_id(callback.from_user.id)
    await callback.message.answer(
        "Список запросов обновлён ✅",
        reply_markup=psych4_options_keyboard(
            "help_topic",
            HELP_TOPIC_OPTIONS,
            psychologist.help_topics or [],
        ),
    )


@router.callback_query(F.data == "psych4:edit_styles")
async def psych4_edit_styles_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    psychologist = await psych4_get_psychologist_or_answer(callback)

    if not psychologist:
        return

    await callback.message.answer(
        "Выберите стиль работы. Можно нажимать несколько вариантов:",
        reply_markup=psych4_options_keyboard(
            "style",
            STYLE_OPTIONS,
            psychologist.styles or [],
        ),
    )


@router.callback_query(F.data.startswith("psych4:toggle_style:"))
async def psych4_toggle_style_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    key = callback.data.split(":")[-1]
    psychologist = await psych4_get_psychologist_or_answer(callback)

    if not psychologist:
        return

    current = list(psychologist.styles or [])

    if key in current:
        current.remove(key)
    else:
        current.append(key)

    async with async_session() as session:
        db_psychologist = await session.get(Psychologist, psychologist.id)
        db_psychologist.styles = current
        await session.commit()

    psychologist = await get_psychologist_by_telegram_id(callback.from_user.id)

    await callback.message.answer(
        "Стиль работы обновлён ✅",
        reply_markup=psych4_options_keyboard(
            "style",
            STYLE_OPTIONS,
            psychologist.styles or [],
        ),
    )


@router.callback_query(F.data.startswith("psych4:add_custom_"))
async def psych4_add_custom_option_start_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    prefix = callback.data.split("psych4:add_custom_", 1)[1]
    if prefix not in PROFILE_LIST_FIELDS:
        return

    psychologist = await psych4_get_psychologist_or_answer(callback)
    if not psychologist:
        return

    await state.set_state(PsychologistCabinetV4States.waiting_custom_option_value)
    await state.update_data(custom_option_prefix=prefix)

    await callback.message.answer(
        "Напишите свой вариант текстом (например: «Работа с фобиями»). "
        "До 100 символов."
    )


@router.message(PsychologistCabinetV4States.waiting_custom_option_value)
async def psych4_custom_option_value_handler(message: Message, state: FSMContext) -> None:
    psychologist = await psych4_get_psychologist_or_answer(message)

    if not psychologist:
        await state.clear()
        return

    data = await state.get_data()
    prefix = data.get("custom_option_prefix")
    field_info = PROFILE_LIST_FIELDS.get(prefix)

    if not field_info:
        await state.clear()
        await message.answer("Не удалось определить, к какому полю анкеты это относится. Попробуйте ещё раз.")
        return

    field_name, options = field_info

    text = (message.text or "").strip()

    if not text:
        await message.answer("Значение не должно быть пустым.")
        return

    if len(text) > 100:
        await message.answer("Слишком длинно - напишите короче, до 100 символов.")
        return

    custom_value = f"{CUSTOM_OPTION_PREFIX}{text}"
    current = list(getattr(psychologist, field_name) or [])

    if custom_value not in current:
        current.append(custom_value)

    async with async_session() as session:
        db_psychologist = await session.get(Psychologist, psychologist.id)
        setattr(db_psychologist, field_name, current)
        await session.commit()

    await state.clear()

    psychologist = await get_psychologist_by_telegram_id(message.from_user.id)
    updated = list(getattr(psychologist, field_name) or [])

    await message.answer(
        "Добавлено ✅",
        reply_markup=psych4_options_keyboard(prefix, options, updated),
    )


@router.callback_query(F.data.startswith("psych4:remove_custom_"))
async def psych4_remove_custom_option_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    remainder = callback.data.split("psych4:remove_custom_", 1)[1]
    prefix, _, index_text = remainder.rpartition(":")
    field_info = PROFILE_LIST_FIELDS.get(prefix)

    if not field_info or not index_text.isdigit():
        return

    field_name, options = field_info
    index = int(index_text)

    psychologist = await psych4_get_psychologist_or_answer(callback)
    if not psychologist:
        return

    current = list(getattr(psychologist, field_name) or [])
    custom_values = [value for value in current if value.startswith(CUSTOM_OPTION_PREFIX)]

    if 0 <= index < len(custom_values):
        current.remove(custom_values[index])

    async with async_session() as session:
        db_psychologist = await session.get(Psychologist, psychologist.id)
        setattr(db_psychologist, field_name, current)
        await session.commit()

    psychologist = await get_psychologist_by_telegram_id(callback.from_user.id)
    updated = list(getattr(psychologist, field_name) or [])

    await callback.message.answer(
        "Удалено ✅",
        reply_markup=psych4_options_keyboard(prefix, options, updated),
    )


@router.callback_query(F.data == "psych4:edit_durations")
async def psych4_edit_durations_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    psychologist = await psych4_get_psychologist_or_answer(callback)

    if not psychologist:
        return

    durations = normalize_durations(psychologist.durations)

    await callback.message.answer(
        "Длительности и цены консультаций.\n\n"
        "У каждой длительности - своя цена, единой цены на все длительности нет. "
        "Нажмите на длительность, чтобы изменить её цену, ✕ - чтобы удалить, "
        "или добавьте новую длительность.",
        reply_markup=psych4_durations_menu_keyboard(durations),
    )


@router.callback_query(F.data == "psych4:add_duration")
async def psych4_add_duration_start_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(PsychologistCabinetV4States.waiting_duration_value)
    await state.update_data(duration_minutes=None)

    await callback.message.answer(
        "Введите длительность в минутах и цену через пробел.\n\n"
        "Например: 30 2500\n"
        "(это добавит консультацию на 30 минут за 2500 ₽; "
        "если такая длительность уже есть, её цена обновится)"
    )


@router.callback_query(F.data.startswith("psych4:edit_one_duration:"))
async def psych4_edit_one_duration_start_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    minutes = int(callback.data.split(":")[-1])
    await state.set_state(PsychologistCabinetV4States.waiting_duration_value)
    await state.update_data(duration_minutes=minutes)

    await callback.message.answer(f"Введите новую цену для длительности {minutes_declension(minutes)} (только число, в рублях).")


@router.message(PsychologistCabinetV4States.waiting_duration_value)
async def psych4_duration_value_handler(message: Message, state: FSMContext) -> None:
    psychologist = await psych4_get_psychologist_or_answer(message)

    if not psychologist:
        await state.clear()
        return

    data = await state.get_data()
    fixed_minutes = data.get("duration_minutes")
    raw = (message.text or "").strip().split()

    try:
        if fixed_minutes is not None:
            if len(raw) != 1:
                raise ValueError
            minutes = int(fixed_minutes)
            price = int(raw[0])
        else:
            if len(raw) != 2:
                raise ValueError
            minutes = int(raw[0])
            price = int(raw[1])

        if minutes <= 0 or price <= 0:
            raise ValueError
    except ValueError:
        if fixed_minutes is not None:
            await message.answer("Введите одно число - цену в рублях, например: 3000")
        else:
            await message.answer("Введите длительность и цену через пробел, например: 30 2500")
        return

    async with async_session() as session:
        db_psychologist = await session.get(Psychologist, psychologist.id)
        db_psychologist.durations = upsert_duration(db_psychologist.durations, minutes, price)
        await session.commit()
        updated = normalize_durations(db_psychologist.durations)

    await state.clear()

    await message.answer(
        f"Сохранено: {minutes_declension(minutes)} — {price} ₽ ✅",
        reply_markup=psych4_durations_menu_keyboard(updated),
    )


@router.callback_query(F.data.startswith("psych4:remove_duration:"))
async def psych4_remove_duration_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    minutes = int(callback.data.split(":")[-1])
    psychologist = await psych4_get_psychologist_or_answer(callback)

    if not psychologist:
        return

    async with async_session() as session:
        db_psychologist = await session.get(Psychologist, psychologist.id)
        db_psychologist.durations = remove_duration(db_psychologist.durations, minutes)
        await session.commit()
        updated = normalize_durations(db_psychologist.durations)

    await callback.message.answer(
        "Длительность удалена ✅",
        reply_markup=psych4_durations_menu_keyboard(updated),
    )


@router.callback_query(F.data == "psych4:schedule")
async def psych4_schedule_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()

    psychologist = await psych4_get_psychologist_or_answer(callback)

    if not psychologist:
        return

    async with async_session() as session:
        intervals_result = await session.execute(
            select(WorkingInterval)
            .where(WorkingInterval.psychologist_id == psychologist.id)
            .order_by(WorkingInterval.date, WorkingInterval.start_time)
        )
        intervals = intervals_result.scalars().all()

        bookings_result = await session.execute(
            select(Booking, User)
            .join(User, User.id == Booking.user_id)
            .where(
                Booking.psychologist_id == psychologist.id,
                Booking.status.in_(["reserved", "paid", "confirmed"]),
            )
            .order_by(Booking.date, Booking.start_time)
        )
        bookings = bookings_result.all()

    text = "Расписание\n\n"

    text += "Свободные интервалы:\n"
    if intervals:
        for interval in intervals:
            text += f"• {interval.date}, {interval.start_time}–{interval.end_time}\n"
    else:
        text += "Пока нет свободных интервалов.\n"

    text += "\nЗанятые записи:\n"
    if bookings:
        for booking, user in bookings:
            text += (
                f"• Запись №{booking.id}: {booking.date} в {booking.start_time}, "
                f"{booking.duration} мин, клиент: {user.full_name or user.username or user.telegram_id}, "
                f"статус: {format_booking_status(booking.status, booking.payment_status)}\n"
            )
    else:
        text += "Пока нет занятых записей.\n"

    await callback.message.answer(
        text,
        reply_markup=psych4_schedule_keyboard(),
    )


@router.callback_query(F.data == "psych4:edit_schedule")
async def psych4_edit_schedule_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()

    await callback.message.answer(
        "Редактирование расписания\n\n"
        "Добавьте время, когда вы готовы проводить консультации.\n\n"
        "Например: 2026-06-28 с 11:00 до 16:00.",
        reply_markup=psych4_edit_schedule_keyboard(),
    )


@router.callback_query(F.data == "psych4:add_interval")
async def psych4_add_interval_start_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    psychologist = await psych4_get_psychologist_or_answer(callback)

    if not psychologist:
        return

    if not get_priced_durations(psychologist):
        # No priced duration yet - an interval created now would get a
        # duration that can never match a real price and would silently
        # never show up to clients (see psych4_add_interval_end_handler).
        await callback.message.answer(
            "Сначала укажите хотя бы одну длительность консультации и её "
            "цену в разделе «Длительность и цена» — иначе свободное время "
            "не будет видно клиентам."
        )
        return

    await state.set_state(PsychologistCabinetV4States.waiting_schedule_date)

    await callback.message.answer(
        "Введите дату свободного интервала в формате ГГГГ-ММ-ДД.\n\nНапример: 2026-06-28"
    )


@router.message(PsychologistCabinetV4States.waiting_schedule_date)
async def psych4_add_interval_date_handler(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()

    try:
        datetime.strptime(value, "%Y-%m-%d")
    except Exception:
        await message.answer("Введите дату в формате ГГГГ-ММ-ДД. Например: 2026-06-28")
        return

    await state.update_data(schedule_date=value)
    await state.set_state(PsychologistCabinetV4States.waiting_schedule_start)

    await message.answer("Введите время начала в формате ЧЧ:ММ.\n\nНапример: 11:00")


@router.message(PsychologistCabinetV4States.waiting_schedule_start)
async def psych4_add_interval_start_time_handler(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()

    try:
        datetime.strptime(value, "%H:%M")
    except Exception:
        await message.answer("Введите время в формате ЧЧ:ММ. Например: 11:00")
        return

    await state.update_data(schedule_start=value)
    await state.set_state(PsychologistCabinetV4States.waiting_schedule_end)

    await message.answer("Введите время окончания в формате ЧЧ:ММ.\n\nНапример: 16:00")


@router.message(PsychologistCabinetV4States.waiting_schedule_end)
async def psych4_add_interval_end_handler(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()

    try:
        datetime.strptime(value, "%H:%M")
    except Exception:
        await message.answer("Введите время в формате ЧЧ:ММ. Например: 16:00")
        return

    data = await state.get_data()

    start_time = datetime.strptime(data["schedule_start"], "%H:%M")
    end_time = datetime.strptime(value, "%H:%M")

    if end_time <= start_time:
        await message.answer("Время окончания должно быть позже времени начала.")
        return

    psychologist = await psych4_get_psychologist_or_answer(message)

    if not psychologist:
        await state.clear()
        return

    priced_durations = get_priced_durations(psychologist)

    if not priced_durations:
        # Profile lost its pricing between "add_interval" and now (e.g. the
        # psychologist removed it mid-flow) - never fall back to a made-up
        # duration, since that duration would never match a real price and
        # the interval would silently never show up to clients.
        await state.clear()
        await message.answer(
            "Сначала укажите длительность консультации и цену в разделе "
            "«Длительность и цена», а затем добавьте свободное время ещё раз."
        )
        return

    # The interval itself is just an availability window (see
    # compute_available_start_times in app/services/schedule.py) - the
    # actual booking duration is chosen per-client later. consultation_duration
    # only drives the *preview* grid on get_active_psychologists_with_slots,
    # so it must be one of the psychologist's own priced durations (the
    # shortest one) rather than a hardcoded value - a hardcoded 50 silently
    # hid every psychologist who never priced exactly 50 minutes.
    preview_duration = priced_durations[0]["minutes"]

    async with async_session() as session:
        interval = WorkingInterval(
            psychologist_id=psychologist.id,
            date=data["schedule_date"],
            start_time=data["schedule_start"],
            end_time=value,
            consultation_duration=preview_duration,
            break_minutes=10,
        )
        session.add(interval)
        await session.commit()

    await state.clear()

    await message.answer(
        "Свободный интервал добавлен ✅\n\n"
        f"{data['schedule_date']}, {data['schedule_start']}–{value}\n\n"
        "Можете добавить ещё один интервал через «Редактировать расписание».",
        reply_markup=psych4_schedule_keyboard(),
    )


@router.callback_query(F.data == "psych4:delete_interval_menu")
async def psych4_delete_interval_menu_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    psychologist = await psych4_get_psychologist_or_answer(callback)

    if not psychologist:
        return

    async with async_session() as session:
        result = await session.execute(
            select(WorkingInterval)
            .where(WorkingInterval.psychologist_id == psychologist.id)
            .order_by(WorkingInterval.date, WorkingInterval.start_time)
        )
        intervals = result.scalars().all()

    if not intervals:
        await callback.message.answer(
            "Свободных интервалов пока нет.",
            reply_markup=psych4_edit_schedule_keyboard(),
        )
        return

    rows = []

    for interval in intervals[:30]:
        rows.append([
            InlineKeyboardButton(
                text=f"Удалить: {interval.date} {interval.start_time}–{interval.end_time}",
                callback_data=f"psych4:delete_interval:{interval.id}",
            )
        ])

    rows.append([InlineKeyboardButton(text="Назад к расписанию", callback_data="psych4:schedule")])

    await callback.message.answer(
        "Выберите свободный интервал, который нужно удалить:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("psych4:delete_interval:"))
async def psych4_delete_interval_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    interval_id = int(callback.data.split(":")[-1])
    psychologist = await psych4_get_psychologist_or_answer(callback)

    if not psychologist:
        return

    async with async_session() as session:
        interval = await session.get(WorkingInterval, interval_id)

        if not interval or interval.psychologist_id != psychologist.id:
            await callback.message.answer("Интервал не найден.")
            return

        await session.delete(interval)
        await session.commit()

    await callback.message.answer(
        "Свободный интервал удалён ✅",
        reply_markup=psych4_edit_schedule_keyboard(),
    )


@router.callback_query(F.data == "psych4:bookings")
async def psych4_bookings_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()

    psychologist = await psych4_get_psychologist_or_answer(callback)

    if not psychologist:
        return

    async with async_session() as session:
        result = await session.execute(
            select(Booking, User)
            .join(User, User.id == Booking.user_id)
            .where(Booking.psychologist_id == psychologist.id)
            .order_by(Booking.date.desc(), Booking.start_time.desc())
            .limit(30)
        )
        rows = result.all()

    if not rows:
        await callback.message.answer(
            "Записей пока нет.",
            reply_markup=psych4_main_keyboard(),
        )
        return

    text = "Записи\n\n"

    for booking, user in rows:
        text += (
            f"Запись №{booking.id}\n"
            f"Дата: {booking.date}\n"
            f"Время: {booking.start_time}\n"
            f"Длительность: {minutes_declension(booking.duration)}\n"
            f"Клиент: {user.full_name or user.username or user.telegram_id}\n"
            f"Телефон: {getattr(user, 'phone', None) or 'не указан'}\n"
            f"Статус: {format_booking_status(booking.status, booking.payment_status)}\n"
            f"Ссылка: {booking.meeting_link or 'не добавлена'}\n"
            f"{psych4_format_client_answers(booking)}\n\n"
        )

    await callback.message.answer(
        text,
        reply_markup=psych4_main_keyboard(),
    )


@router.callback_query(F.data == "psych4:meeting_link")
async def psych4_meeting_link_start_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(PsychologistCabinetV4States.waiting_link_booking_id)

    await callback.message.answer(
        "Введите номер записи, для которой хотите добавить или изменить ссылку.\n\nНапример: 17"
    )


@router.message(PsychologistCabinetV4States.waiting_link_booking_id)
async def psych4_meeting_link_booking_id_handler(message: Message, state: FSMContext) -> None:
    raw_id = (message.text or "").strip()

    if not raw_id.isdigit():
        await message.answer("Введите номер записи числом. Например: 17")
        return

    booking_id = int(raw_id)
    psychologist = await psych4_get_psychologist_or_answer(message)

    if not psychologist:
        await state.clear()
        return

    async with async_session() as session:
        booking = await session.get(Booking, booking_id)

        if not booking or booking.psychologist_id != psychologist.id:
            await message.answer("Запись не найдена или она не относится к Вашему профилю.")
            await state.clear()
            return

        current_link = booking.meeting_link

    await state.update_data(link_booking_id=booking_id)
    await state.set_state(PsychologistCabinetV4States.waiting_link_value)

    if current_link:
        await message.answer(
            f"Сейчас у записи №{booking_id} уже есть ссылка:\n\n"
            f"{current_link}\n\n"
            "Отправьте новую ссылку, если хотите заменить текущую."
        )
    else:
        await message.answer(
            f"У записи №{booking_id} пока нет ссылки.\n\n"
            "Отправьте ссылку на встречу."
        )


@router.message(PsychologistCabinetV4States.waiting_link_value)
async def psych4_meeting_link_value_handler(message: Message, state: FSMContext) -> None:
    link = (message.text or "").strip()

    if not (
        link.startswith("http://")
        or link.startswith("https://")
        or link.startswith("t.me/")
    ):
        await message.answer("Похоже, это не ссылка. Пришлите ссылку, начинающуюся с https://, http:// или t.me/")
        return

    data = await state.get_data()
    booking_id = data.get("link_booking_id")

    if not booking_id:
        await message.answer("Не нашёл номер записи. Начните заново через кнопку «Добавить/изменить ссылку встречи».")
        await state.clear()
        return

    psychologist = await psych4_get_psychologist_or_answer(message)

    if not psychologist:
        await state.clear()
        return

    async with async_session() as session:
        booking = await session.get(Booking, int(booking_id))

        if not booking or booking.psychologist_id != psychologist.id:
            await message.answer("Запись не найдена или она не относится к Вашему профилю.")
            await state.clear()
            return

        booking.meeting_link = link

        # Важно: НЕ отправляем ссылку клиенту сразу.
        # Просто разрешаем reminder-задаче отправить её за 10 минут до начала.
        booking.reminder_10m_sent = False

        await session.commit()

    await state.clear()

    await message.answer(
        "Ссылка на встречу сохранена ✅\n\n"
        f"Запись №{booking_id}\n"
        f"Ссылка: {link}\n\n"
        "Клиент получит эту ссылку автоматически за 10 минут до начала встречи.",
        reply_markup=psych4_main_keyboard(),
    )


# === PSYCHOLOGIST CABINET V4 END ===

