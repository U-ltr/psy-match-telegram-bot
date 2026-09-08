from zoneinfo import ZoneInfo
from datetime import datetime
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from app.config import settings
from app.keyboards.client import (
    main_menu_keyboard,
    request_keyboard,
    expectation_keyboard,
    therapy_experience_keyboard,
    gender_keyboard,
    budget_keyboard,
    age_keyboard,
    comment_keyboard,
    summary_keyboard,
    psychologist_card_keyboard,
    slots_keyboard,
    durations_keyboard,
    after_booking_keyboard,
    back_to_menu_keyboard,
    booking_consent_keyboard,
    booking_email_keyboard,
    booking_phone_keyboard,
    booking_created_keyboard,
    add_back_button,
)
from app.services.matching import get_ranked_psychologists
from app.services.psychologists import (
    get_active_psychologists_with_slots,
    get_psychologist_by_id_from_db,
    get_available_start_times_for_duration,
)
from app.services.bookings import (
    create_booking_from_generated_slot,
    cancel_user_booking,
    RESERVATION_MINUTES,
)
from app.services.yookassa_payments import create_yookassa_payment_for_booking
from app.models.booking import Booking
from app.services.answer_formatting import years_declension, minutes_declension, format_code_list
from app.services.pricing import format_priced_minutes_list
from app.keyboards.psychologist import SPECIALIZATION_OPTIONS, HELP_TOPIC_OPTIONS
from app.states.client import ClientSelectionStates, SelectionStates
from app.texts.client import (
    WELCOME_TEXT,
    MAIN_MENU_TEXT,
    START_MATCHING_TEXT,
    QUESTION_2_TEXT,
    QUESTION_3_TEXT,
    QUESTION_4_TEXT,
    QUESTION_6_TEXT,
    QUESTION_8_TEXT,
    QUESTION_9_TEXT,
    SHORT_SELECTION_TEXT,
    HELP_TEXT,
    REQUEST_OTHER_TEXT,
    COMMENT_TEXT,
    UNDER_18_TEXT,
)




def is_future_moscow_slot(date_value: str, time_value: str) -> bool:
    if not date_value or not time_value:
        return False

    try:
        slot_dt = datetime.strptime(f"{date_value} {time_value}", "%Y-%m-%d %H:%M")
    except ValueError:
        return False

    now_moscow = datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None)
    return slot_dt > now_moscow


def filter_future_slots(slots: list[dict]) -> list[dict]:
    return [
        slot for slot in slots
        if is_future_moscow_slot(
            slot.get("date"),
            slot.get("time") or slot.get("start_time"),
        )
    ]



def get_nearest_slot_datetime(psychologist: dict):
    slots = filter_future_slots(psychologist.get("slots", []))

    if not slots:
        return None

    first_slot = slots[0]
    date_value = first_slot.get("date")
    time_value = first_slot.get("time") or first_slot.get("start_time")

    try:
        return datetime.strptime(f"{date_value} {time_value}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def sort_psychologists_by_nearest_slot(psychologists: list[dict]) -> list[dict]:
    prepared = []

    for psychologist in psychologists:
        future_slots = filter_future_slots(psychologist.get("slots", []))

        future_slots = sorted(
            future_slots,
            key=lambda slot: datetime.strptime(
                f"{slot.get('date')} {slot.get('time') or slot.get('start_time')}",
                "%Y-%m-%d %H:%M",
            ),
        )

        psychologist["slots"] = future_slots

        nearest_dt = get_nearest_slot_datetime(psychologist)

        if nearest_dt:
            prepared.append((nearest_dt, psychologist))

    prepared.sort(key=lambda item: item[0])

    return [psychologist for _, psychologist in prepared]

router = Router(name="client")


REQUEST_LABELS = {
    "anxiety_stress": "Тревога и стресс",
    "relationships": "Отношения",
    "selfesteem": "Самооценка",
    "burnout_work": "Выгорание и работа",
    "depressive_state": "Депрессивное состояние",
    "loss": "Утрата",
    "family": "Семейные вопросы",
    "addictions": "Зависимости",
    "self_understanding": "Хочу разобраться в себе",
    "guilt": "Чувство вины",
    "loneliness": "Одиночество",
    "other": "Другое",
}

EXPECTATION_LABELS = {
    "acceptance": "Выслушали и приняли без осуждения",
    "reasons": "Понять причины переживаний",
    "cope": "Научиться справляться с эмоциями",
    "patterns": "Разобраться с привычками и поведением",
    "thoughts": "Лучше понимать и контролировать мысли",
    "unknown": "Пока не знаю",
}

THERAPY_EXPERIENCE_LABELS = {
    "none": "Нет",
    "positive": "Да, положительный",
    "negative": "Да, отрицательный",
}

GENDER_LABELS = {
    "any": "Неважно",
    "female": "Женщина",
    "male": "Мужчина",
}

START_TIME_LABELS = {
    "today": "Сегодня",
    "week": "В течение недели",
    "month": "В ближайший месяц",
    "specific_time": "Выбрать конкретное время",
}

BUDGET_LABELS = {
    "under_2000": "До 2 000 ₽",
    "2000_3000": "2 000–3 000 ₽",
    "3000_5000": "3 000–5 000 ₽",
    "5000_plus": "5 000 ₽ и выше",
    "not_important": "Цена не главный критерий",
}

PRIORITY_LABELS = {
    "request": "Совпадение по запросу",
    "price": "Цена",
    "time": "Ближайшее удобное время",
    "gender": "Пол специалиста",
    "experience": "Опыт психолога",
    "style": "Стиль работы",
    "duration": "Длительность консультации",
}

AGE_LABELS = {
    "under_18": "До 18",
    "18_24": "18–24",
    "25_34": "25–34",
    "35_44": "35–44",
    "45_plus": "45+",
}


@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext) -> None:
    await state.clear()

    from app.keyboards.client import main_menu_keyboard, restart_reply_keyboard

    welcome_text = (
        "Добро пожаловать 👋\n\n"
        "Я помогу подобрать психолога под Ваш запрос, удобное время и комфортный бюджет.\n\n"
        "Ответьте на несколько коротких вопросов — и я предложу подходящего специалиста.\n\n"
        "Важно: бот помогает подобрать психолога, но не оказывает экстренную медицинскую помощь. "
        "Если есть угроза жизни или здоровью, обратитесь в экстренные службы."
    )

    await message.answer(
        welcome_text,
        reply_markup=main_menu_keyboard(),
    )

    await message.answer(
        "Выберите действие выше 👆",
        reply_markup=restart_reply_keyboard(),
    )



async def show_psychologist_card(
    message,
    state: FSMContext,
    psychologist: dict,
    index: int,
    total: int,
    edit: bool = False,
) -> None:
    from app.keyboards.client import psychologist_card_keyboard

    slots = filter_future_slots(psychologist.get("slots", []))
    psychologist["slots"] = slots

    # Single source of truth for these labels: app.keyboards.psychologist
    # (SPECIALIZATION_OPTIONS / HELP_TOPIC_OPTIONS), same dicts the
    # psychologist's own cabinet uses to edit these fields - never a local
    # copy here, or the two drift and a raw code leaks (see format_code_list's
    # docstring).
    specializations = format_code_list(psychologist.get("specializations", []) or [], SPECIALIZATION_OPTIONS)
    help_topics = format_code_list(psychologist.get("help_topics", []) or [], HELP_TOPIC_OPTIONS)
    durations = format_priced_minutes_list(psychologist.get("durations", []))

    nearest_slots_text = "Ближайшие слоты:\n"

    if slots:
        for slot in slots[:3]:
            slot_time = slot.get("time") or slot.get("start_time")
            slot_duration = slot.get("duration") or slot.get("consultation_duration") or 60

            nearest_slots_text += (
                f"• {slot.get('date')} в {slot_time} · {slot_duration} мин\n"
            )
    else:
        nearest_slots_text += "Пока нет доступных будущих слотов.\n"

    data = await state.get_data()
    mode = data.get("matching_mode")

    if mode == "nearest":
        title = "Ближайший психолог"
    elif mode == "name_search":
        title = "Найденный психолог"
    else:
        title = "Подобранный психолог"

    card_text = (
        f"{title} ({index + 1} из {total})\n\n"
        f"{psychologist.get('name')}\n\n"
        f"Специализация: {specializations or '—'}\n"
        f"С чем может помочь: {help_topics or '—'}\n"
        f"Опыт: {years_declension(psychologist.get('experience_years') or 0)}\n"
        f"Образование: {psychologist.get('education') or '—'}\n"
        f"Стоимость: от {psychologist.get('min_price')} ₽\n"
        f"Длительность: {durations}\n\n"
        f"{psychologist.get('description') or ''}\n\n"
        f"{nearest_slots_text}"
    )

    photo_file_id = psychologist.get("photo_file_id")
    reply_markup = psychologist_card_keyboard(psychologist.get("id"))

    if edit:
        try:
            await message.delete()
        except Exception:
            pass

    if photo_file_id:
        if len(card_text) <= 1000:
            await message.answer_photo(
                photo=photo_file_id,
                caption=card_text,
                reply_markup=reply_markup,
            )
        else:
            await message.answer_photo(
                photo=photo_file_id,
                caption=f"{psychologist.get('name')}\nСтоимость: от {psychologist.get('min_price')} ₽",
            )
            await message.answer(
                card_text,
                reply_markup=reply_markup,
            )
    else:
        await message.answer(
            card_text,
            reply_markup=reply_markup,
        )

    await message.answer("Выберите действие выше 👆")







@router.callback_query(F.data == "client:nearest_psychologists")
async def nearest_psychologists_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()

    psychologists = await get_active_psychologists_with_slots()

    psychologists = sort_psychologists_by_nearest_slot(psychologists)
    psychologists = psychologists[:5]

    if not psychologists:
        await callback.message.answer(
            "Сейчас нет психологов с доступным будущим временем. Попробуйте позже.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    await state.update_data(
        matched_psychologists=psychologists,
        current_psychologist_index=0,
        matching_mode="nearest",
    )

    await show_psychologist_card(
        message=callback.message,
        state=state,
        psychologist=psychologists[0],
        index=0,
        total=len(psychologists),
        edit=False,
    )

@router.callback_query(F.data == "client:choose_slot")
async def choose_slot_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _show_duration_choices_for_current_match(callback, state)


async def _show_duration_choices_for_current_match(callback: CallbackQuery, state: FSMContext) -> None:
    from app.keyboards.client import slots_keyboard, back_to_menu_keyboard

    data = await state.get_data()
    psychologists = data.get("matched_psychologists") or []
    current_index = int(data.get("current_psychologist_index") or 0)

    if not psychologists:
        psychologists = await get_active_psychologists_with_slots()

        for psychologist in psychologists:
            psychologist["slots"] = filter_future_slots(psychologist.get("slots", []))

        psychologists = [
            psychologist for psychologist in psychologists
            if psychologist.get("slots")
        ]

        if not psychologists:
            await callback.message.answer(
                "Сейчас нет доступного будущего времени для записи. Попробуйте позже.",
                reply_markup=back_to_menu_keyboard(),
            )
            return

        current_index = 0
        await state.update_data(
            matched_psychologists=psychologists,
            current_psychologist_index=current_index,
        )

    if current_index >= len(psychologists):
        current_index = 0

    psychologist = psychologists[current_index]
    slots = filter_future_slots(psychologist.get("slots", []))

    if not slots:
        await callback.message.answer(
            "У этого психолога сейчас нет доступного будущего времени. Попробуйте выбрать другого специалиста.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    psychologist["slots"] = slots

    priced_durations = [item for item in psychologist.get("durations", []) if item.get("price")]

    if not priced_durations:
        await callback.message.answer(
            "У этого психолога пока не настроены цены на длительности консультаций. "
            "Попробуйте выбрать другого специалиста.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    await state.update_data(
        selected_psychologist=psychologist,
        selected_psychologist_id=psychologist.get("id"),
        matched_psychologists=psychologists,
        current_psychologist_index=current_index,
    )

    await callback.message.answer(
        f"{psychologist.get('name')}\n\n"
        "Выберите длительность консультации:\n\n"
        "Время записи ИДЁТ по Москве.",
        reply_markup=durations_keyboard(psychologist.get("id"), priced_durations, "client:back_to_slot_menu"),
    )

    await callback.message.answer("Выберите действие выше 👆")


@router.callback_query(F.data == "client:back_to_slot_menu")
async def back_to_slot_menu_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """"Назад" from the duration-choice screen. This used to call right
    back into _show_duration_choices_for_current_match - i.e. re-render
    the exact same duration list the person was already looking at - so
    tapping it looked like nothing happened and the only way out was
    "Начать заново". It now actually goes back a screen, to the
    psychologist's own card (photo, description, nearest slots, "Выбрать
    время" again if they change their mind)."""
    await callback.answer()

    data = await state.get_data()
    psychologists = data.get("matched_psychologists") or []
    current_index = int(data.get("current_psychologist_index") or 0)

    if not psychologists or current_index >= len(psychologists):
        # Nothing to go back to (state lost/expired) - fall back to
        # whatever duration choices we can still put together rather than
        # a dead end.
        await _show_duration_choices_for_current_match(callback, state)
        return

    await show_psychologist_card(
        message=callback.message,
        state=state,
        psychologist=psychologists[current_index],
        index=current_index,
        total=len(psychologists),
        edit=False,
    )


@router.callback_query(F.data.in_({"client:psych_next", "client:psych_prev"}))
async def switch_psychologist_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    data = await state.get_data()
    psychologists = data.get("matched_psychologists") or []
    current_index = int(data.get("current_psychologist_index") or 0)

    # Если список потерялся, загружаем заново из базы.
    if not psychologists:
        psychologists = await get_active_psychologists_with_slots()

        for psychologist in psychologists:
            psychologist["slots"] = filter_future_slots(psychologist.get("slots", []))

        psychologists = [
            psychologist for psychologist in psychologists
            if psychologist.get("slots")
        ]

        if not psychologists:
            await callback.message.answer(
                "Сейчас нет психологов с доступным будущим временем. Попробуйте позже.",
                reply_markup=back_to_menu_keyboard(),
            )
            return

        current_index = 0

    if callback.data == "client:psych_next":
        current_index = (current_index + 1) % len(psychologists)
    else:
        current_index = (current_index - 1) % len(psychologists)

    await state.update_data(
        matched_psychologists=psychologists,
        current_psychologist_index=current_index,
    )

    psychologist = psychologists[current_index]

    await show_psychologist_card(
        message=callback.message,
        state=state,
        psychologist=psychologist,
        index=current_index,
        total=len(psychologists),
        edit=True,
    )

@router.callback_query(F.data == "client:restart")
async def restart_handler(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await callback.answer()
    except Exception as error:
        print(f"Restart callback answer skipped: {error}")

    await state.clear()

    from app.keyboards.client import main_menu_keyboard, restart_reply_keyboard

    await callback.message.answer(
        "\n\n"
        "Выберите, что хотите сделать:",
        reply_markup=main_menu_keyboard(),
    )
@router.callback_query(F.data == "client:start_matching")
async def start_matching_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()

    await callback.message.edit_text(
        START_MATCHING_TEXT,
        reply_markup=request_keyboard(),
    )


@router.callback_query(F.data == "client:short_selection")
async def short_selection_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    await callback.message.edit_text(
        SHORT_SELECTION_TEXT,
        reply_markup=back_to_menu_keyboard(),
    )


@router.message(ClientSelectionStates.request_other_text, F.text != "Начать заново")
async def request_other_text_handler(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    requests = data.get("requests", [])
    await state.update_data(request_other_text=message.text, request=(requests[0] if requests else "other"))
    await state.set_state(None)

    await message.answer(
        QUESTION_2_TEXT,
        reply_markup=add_back_button(expectation_keyboard(), "client:back:q1"),
    )


@router.callback_query(F.data.startswith("client:q3:"))
async def q3_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    answer = callback.data.replace("client:q3:", "")
    await state.update_data(therapy_experience=answer)

    await callback.message.edit_text(
        QUESTION_4_TEXT,
        reply_markup=add_back_button(gender_keyboard(), "client:back:q3"),
    )


@router.callback_query(F.data.startswith("client:q4:"))
async def preferred_gender_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    gender = callback.data.split(":")[-1]

    await state.update_data(
        preferred_gender=gender,
        start_time="nearest",
    )

    from app.keyboards.client import budget_keyboard, add_back_button

    await callback.message.edit_text(
        "Какой бюджет Вам комфортен?",
        reply_markup=add_back_button(budget_keyboard(), "client:back:q4"),
    )

@router.callback_query(F.data.startswith("client:q6:"))
async def budget_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    budget = callback.data.split(":")[-1]

    await state.update_data(
        budget=budget,
        priorities=["match", "nearest_time", "price"],
    )

    from app.keyboards.client import age_keyboard, add_back_button

    await callback.message.edit_text(
        "Ваш возраст?",
        reply_markup=add_back_button(age_keyboard(), "client:back:q6"),
    )

@router.callback_query(F.data.startswith("client:q8:"))
async def q8_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    answer = callback.data.replace("client:q8:", "")

    if answer == "under_18":
        await state.clear()
        await callback.message.edit_text(
            UNDER_18_TEXT,
            reply_markup=back_to_menu_keyboard(),
        )
        return

    await state.update_data(age=answer)

    await callback.message.edit_text(
        QUESTION_9_TEXT,
        reply_markup=comment_keyboard(),
    )


@router.callback_query(F.data == "client:q9:yes")
async def q9_yes_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    await state.set_state(ClientSelectionStates.comment_text)
    await callback.message.edit_text(COMMENT_TEXT)


@router.message(ClientSelectionStates.comment_text, F.text != "Начать заново")
async def comment_text_handler(message: Message, state: FSMContext) -> None:
    await state.update_data(comment=message.text)
    await state.set_state(None)

    await send_summary(message, state)


@router.callback_query(F.data == "client:q9:no")
async def q9_no_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    await state.update_data(comment=None)
    await send_summary(callback.message, state, edit=True)


async def send_summary(message: Message, state: FSMContext, edit: bool = False) -> None:
    data = await state.get_data()

    priorities = data.get("priorities", [])
    priorities_text = ", ".join(PRIORITY_LABELS.get(item, item) for item in priorities)

    requests = data.get("requests", []) or ([data.get("request")] if data.get("request") else [])
    request_parts = [REQUEST_LABELS.get(item, item) for item in requests]
    if "other" in requests and data.get("request_other_text"):
        request_parts = [item for item in request_parts if item != REQUEST_LABELS.get("other")]
        request_parts.append(f"Другое: {data.get('request_other_text')}")
    request_text = ", ".join(request_parts) or "—"

    expectations = data.get("expectations", []) or ([data.get("expectation")] if data.get("expectation") else [])
    expectation_text = ", ".join(EXPECTATION_LABELS.get(item, item) for item in expectations) or "—"

    text = (
        "Готово ✅\n\n"
        "Проверьте ответы перед подбором:\n\n"
        f"Запросы: {request_text}\n"
        f"Ожидания: {expectation_text}\n"
        f"Опыт терапии: {THERAPY_EXPERIENCE_LABELS.get(data.get('therapy_experience'), '—')}\n"
        f"Пожелания к специалисту: {GENDER_LABELS.get(data.get('preferred_gender'), '—')}\n"
        f"Бюджет: {BUDGET_LABELS.get(data.get('budget'), '—')}\n"
        f"Возраст: {AGE_LABELS.get(data.get('age'), '—')}\n"
    )

    if data.get("comment"):
        text += f"\nКомментарий: {data.get('comment')}\n"

    if edit:
        await message.edit_text(text, reply_markup=summary_keyboard())
    else:
        await message.answer(text, reply_markup=summary_keyboard())


@router.callback_query(F.data == "client:show_match")
async def show_match_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    data = await state.get_data()

    psychologists = await get_active_psychologists_with_slots()

    for psychologist in psychologists:
        psychologist["slots"] = filter_future_slots(psychologist.get("slots", []))

    psychologists = [
        psychologist for psychologist in psychologists
        if psychologist.get("slots")
    ]
    ranked = get_ranked_psychologists(data, psychologists)

    if not ranked:
        await callback.message.edit_text(
            "Сейчас нет доступных психологов.\n\n"
            "Попробуйте позже или обратитесь к администратору.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    # Same state shape (matched_psychologists/current_psychologist_index)
    # and the same show_psychologist_card renderer as every other matching
    # flow (nearest, name search) - this used to keep its own separate
    # ranked_psychologist_ids state and a second, incomplete card renderer
    # (show_current_psychologist, removed - see git history), which caused
    # two real bugs: the card here never showed the photo or the
    # help_topics/styles lines show_psychologist_card already has, and
    # every downstream handler bound to this card's own keyboard
    # (choose_slot -> _show_duration_choices_for_current_match, psych_next/
    # psych_prev -> switch_psychologist_handler) only ever understood
    # matched_psychologists - so "Выбрать время"/"Следующий" on a card from
    # THIS flow found no matching state and silently fell back to the
    # first active psychologist in the whole database instead of the one
    # actually on screen.
    await state.update_data(
        matched_psychologists=ranked,
        current_psychologist_index=0,
        matching_mode="algorithm",
    )

    await show_psychologist_card(
        message=callback.message,
        state=state,
        psychologist=ranked[0],
        index=0,
        total=len(ranked),
        edit=True,
    )


@router.callback_query(F.data.startswith("client:duration:"))
async def duration_selected_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    parts = callback.data.split(":")
    psychologist_id = int(parts[2])
    duration = int(parts[3])

    psychologist = await get_psychologist_by_id_from_db(psychologist_id)
    if not psychologist:
        await callback.message.edit_text(
            "Психолог не найден.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    slots = await get_available_start_times_for_duration(psychologist_id, duration)

    if not slots:
        await callback.message.edit_text(
            f"Для длительности {minutes_declension(duration)} сейчас нет свободного времени у этого психолога. "
            "Попробуйте выбрать другую длительность или другого специалиста.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    await state.update_data(
        selected_psychologist_id=psychologist_id,
        duration_slots=slots,
    )

    await callback.message.edit_text(
        f"Выберите удобное время ({minutes_declension(duration)}):\n\n"
        "Время записи ИДЁТ по Москве.",
        reply_markup=slots_keyboard(psychologist_id, slots),
    )


@router.callback_query(F.data.startswith("client:slot:"))
async def slot_selected_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    parts = callback.data.split(":")
    psychologist_id = int(parts[2])
    slot_index = int(parts[3])

    psychologist = await get_psychologist_by_id_from_db(psychologist_id)
    if not psychologist:
        await callback.message.edit_text(
            "Психолог не найден.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    data = await state.get_data()
    slots = data.get("duration_slots") or psychologist.get("slots", [])

    try:
        slot = slots[slot_index]
    except IndexError:
        await callback.message.edit_text(
            "Слот не найден.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    await state.update_data(
        selected_psychologist_id=psychologist_id,
        selected_slot=slot,
    )

    text = (
        "Перед записью нужно подтвердить согласие на обработку персональных данных.\n\n"
        "Мы используем Ваши данные только для оформления записи, связи с Вами, отправки подтверждения, чека и напоминаний о консультации.\n\n"
        f"Психолог: {psychologist['name']}\n"
        f"Дата: {slot['date']}\n"
        f"Время: {slot['time']} (по Москве)\n"
        f"Длительность: {minutes_declension(slot['duration'])}\n"
        f"Стоимость: {slot['price']} ₽\n\n"
        "Вы согласны продолжить?"
    )

    await callback.message.edit_text(
        text,
        reply_markup=booking_consent_keyboard(),
    )


@router.callback_query(F.data == "client:booking_consent:no")
async def booking_consent_no_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()

    await callback.message.edit_text(
        "Запись отменена.\n\n"
        "Вы можете вернуться в главное меню и пройти подбор заново.",
        reply_markup=back_to_menu_keyboard(),
    )


@router.callback_query(F.data == "client:booking_consent:yes")
async def booking_consent_yes_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    await state.set_state(ClientSelectionStates.booking_phone)

    await callback.message.edit_text(
        "Введите Ваш номер телефона для связи.\n\n"
        "Например: +7 999 123-45-67\n\n"
        "Если сейчас не хотите указывать телефон, нажмите «Пропустить телефон».",
        reply_markup=booking_phone_keyboard(),
    )


@router.message(ClientSelectionStates.booking_phone, F.text != "Начать заново")
async def booking_phone_handler(message: Message, state: FSMContext) -> None:
    phone = message.text.strip()

    digits_count = sum(char.isdigit() for char in phone)

    if digits_count < 10:
        await message.answer(
            "Похоже, номер телефона введён некорректно.\n\n"
            "Введите номер ещё раз, например: +7 999 123-45-67, "
            "или нажмите «Пропустить телефон».",
            reply_markup=booking_phone_keyboard(),
        )
        return

    await state.update_data(booking_phone=phone)
    await state.set_state(ClientSelectionStates.booking_email)

    await message.answer(
        "Введите email для чека и уведомлений.\n\n"
        "Если email сейчас не нужен, нажмите «Пропустить email».",
        reply_markup=booking_email_keyboard(),
    )


@router.callback_query(F.data == "client:booking_phone:skip")
async def booking_phone_skip_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    await state.update_data(booking_phone=None)
    await state.set_state(ClientSelectionStates.booking_email)

    await callback.message.edit_text(
        "Введите email для чека и уведомлений.\n\n"
        "Если email сейчас не нужен, нажмите «Пропустить email».",
        reply_markup=booking_email_keyboard(),
    )


@router.message(ClientSelectionStates.booking_email, F.text != "Начать заново")
async def booking_email_text_handler(message: Message, state: FSMContext) -> None:
    email = message.text.strip()

    if "@" not in email or "." not in email:
        await message.answer(
            "Похоже, email введён некорректно.\n\n"
            "Введите email ещё раз или нажмите «Пропустить email».",
            reply_markup=booking_email_keyboard(),
        )
        return

    await state.update_data(booking_email=email)
    await create_booking_after_contacts(message, state)


@router.callback_query(F.data == "client:booking_email:skip")
async def booking_email_skip_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    await state.update_data(booking_email=None)
    await create_booking_after_contacts(callback.message, state, edit=True, callback=callback)


async def create_booking_after_contacts(
    message: Message,
    state: FSMContext,
    edit: bool = False,
    callback: CallbackQuery | None = None,
) -> None:
    data = await state.get_data()

    psychologist_id = data.get("selected_psychologist_id")
    slot = data.get("selected_slot")

    if not psychologist_id or not slot:
        text = "Не удалось найти выбранный слот. Попробуйте пройти подбор заново."

        if edit:
            await message.edit_text(text, reply_markup=back_to_menu_keyboard())
        else:
            await message.answer(text, reply_markup=back_to_menu_keyboard())

        return

    psychologist = await get_psychologist_by_id_from_db(psychologist_id)

    if not psychologist:
        text = "Психолог не найден. Попробуйте выбрать другого специалиста."

        if edit:
            await message.edit_text(text, reply_markup=back_to_menu_keyboard())
        else:
            await message.answer(text, reply_markup=back_to_menu_keyboard())

        return

    from_user = callback.from_user if callback else message.from_user

    client_answers_snapshot = {
        "request": data.get("request"),
        "requests": data.get("requests", []),
        "request_other": data.get("request_other"),
        "expectation": data.get("expectation"),
        "expectations": data.get("expectations", []),
        "therapy_experience": data.get("therapy_experience"),
        "preferred_gender": data.get("preferred_gender"),
        "start_time": data.get("start_time"),
        "budget": data.get("budget"),
        "priorities": data.get("priorities"),
        "age_group": data.get("age_group"),
        "comment": data.get("comment"),
    }

    booking = await create_booking_from_generated_slot(
        telegram_id=from_user.id,
        username=from_user.username,
        full_name=from_user.full_name,
        age_group=data.get("age"),
        phone=data.get("booking_phone"),
        email=data.get("booking_email"),
        psychologist_id=psychologist_id,
        date=slot["date"],
        start_time=slot["time"],
        duration=slot["duration"],
    )

    if not booking:
        text = (
            "Не удалось создать запись.\n\n"
            "Возможно, это время уже заняли. Вернитесь к подбору и выберите другой слот."
        )

        if edit:
            await message.edit_text(text, reply_markup=back_to_menu_keyboard())
        else:
            await message.answer(text, reply_markup=back_to_menu_keyboard())

        return

    await state.update_data(booking_id=booking.id)

    email_text = data.get("booking_email") or "не указан"
    phone_text = data.get("booking_phone") or "не указан"

    text = (
        "Запись создана ✅\n\n"
        f"Номер записи: {booking.id}\n"
        f"Психолог: {psychologist['name']}\n"
        f"Дата: {slot['date']}\n"
        f"Время: {slot['time']} (по Москве)\n"
        f"Длительность: {minutes_declension(slot['duration'])}\n"
        f"Стоимость: {slot['price']} ₽\n\n"
        f"Телефон: {phone_text}\n"
        f"Email: {email_text}\n\n"
        f"Время зарезервировано на {minutes_declension(RESERVATION_MINUTES)}.\n"
        "За это время нужно перейти к оплате, иначе слот снова станет доступен другим клиентам."
    )

    if edit:
        await message.edit_text(text, reply_markup=booking_created_keyboard(booking.id))
    else:
        await message.answer(text, reply_markup=booking_created_keyboard(booking.id))


@router.callback_query(F.data == "client:payment_stub")
async def payment_stub_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    data = await state.get_data()
    booking_id = data.get("booking_id")

    if not booking_id:
        await callback.message.edit_text(
            "Не удалось найти запись для оплаты. Попробуйте создать запись заново.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    payment_url = await create_yookassa_payment_for_booking(
        telegram_id=callback.from_user.id,
        booking_id=booking_id,
    )

    if not payment_url:
        await callback.message.edit_text(
            "Не удалось создать платёж. Проверьте настройки ЮKassa или попробуйте позже.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    await callback.message.edit_text(
        "Платёж создан ✅\n\n"
        "Перейдите по ссылке ниже и оплатите консультацию.\n"
        "После успешной оплаты ЮKassa отправит уведомление, и статус записи изменится автоматически.\n\n"
        f"{payment_url}",
        reply_markup=back_to_menu_keyboard(),
    )


@router.callback_query(F.data.startswith("client:cancel_booking:"))
async def cancel_booking_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    booking_id = int(callback.data.replace("client:cancel_booking:", ""))

    success = await cancel_user_booking(callback.from_user.id, booking_id)

    if not success:
        await callback.message.edit_text(
            "Не удалось отменить запись.\n\n"
            "Возможно, она уже оплачена или подтверждена.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    await callback.message.edit_text(
        "Запись отменена ✅\n\n"
        "Слот снова стал доступен для выбора.",
        reply_markup=back_to_menu_keyboard(),
    )




@router.callback_query(F.data == "client:help")
async def client_help_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    await callback.message.answer(
        "Помощь 💬\n\n"
        "Если возник вопрос по подбору психолога, оплате, переносу записи "
        "или ссылке на встречу — напишите в поддержку.\n\n"
        "Контакт поддержки: @egorinforest\n\n"
        "Если есть угроза жизни или здоровью, обратитесь в экстренные службы."
    )


@router.message(F.text == "Начать заново")
async def restart_text_button_handler(message: Message, state: FSMContext) -> None:
    await state.clear()

    from app.keyboards.client import main_menu_keyboard, restart_reply_keyboard

    welcome_text = (
        "Добро пожаловать 👋\n\n"
        "Я помогу подобрать психолога под Ваш запрос, удобное время и комфортный бюджет.\n\n"
        "Ответьте на несколько коротких вопросов — и я предложу подходящего специалиста.\n\n"
        "Важно: бот помогает подобрать психолога, но не оказывает экстренную медицинскую помощь. "
        "Если есть угроза жизни или здоровью, обратитесь в экстренные службы."
    )

    await message.answer(
        welcome_text,
        reply_markup=main_menu_keyboard(),
    )

    await message.answer(
        "Выберите действие выше 👆",
        reply_markup=restart_reply_keyboard(),
    )

@router.callback_query(F.data == "client:selection_15")
async def selection_15_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()

    from app.services.selection_15 import get_selection_available_slots
    from app.keyboards.client import selection_slots_keyboard, back_to_menu_keyboard

    slots = await get_selection_available_slots(limit=8)

    if not slots:
        await callback.message.edit_text(
            "Сейчас нет доступных слотов для 15-минутного подбора.\n\n"
            "Попробуйте позже или напишите администратору.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    await state.update_data(selection_slots=slots)

    await callback.message.edit_text(
        "15-минутный подбор поможет точнее выбрать специалиста, "
        "если Вы не знаете, с кем начать.\n\n"
        "На короткой встрече специалист уточнит Ваш запрос и поможет понять, "
        "какой психолог подойдёт лучше.\n\n"
        f"Стоимость: бесплатно\n"
        f"Длительность: {minutes_declension(settings.selection_15_duration)}\n\n"
        "Выберите удобное время:",
        reply_markup=selection_slots_keyboard(slots),
    )


@router.callback_query(F.data.startswith("client:selection_slot:"))
async def selection_15_slot_selected(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    from app.keyboards.client import selection_consent_keyboard

    index_raw = callback.data.split(":")[-1]

    if not index_raw.isdigit():
        await callback.message.edit_text("Не удалось определить выбранное время.")
        return

    index = int(index_raw)
    data = await state.get_data()
    slots = data.get("selection_slots") or []

    if index < 0 or index >= len(slots):
        await callback.message.edit_text("Этот слот уже недоступен. Попробуйте выбрать время заново.")
        return

    selected_slot = slots[index]
    await state.update_data(selection_selected_slot=selected_slot)

    await callback.message.edit_text(
        "Вы выбрали 15-минутный подбор специалистом:\n\n"
        f"Дата: {selected_slot['date']}\n"
        f"Время: {selected_slot['time']}\n"
        f"Длительность: {minutes_declension(selected_slot['duration'])}\n"
        f"Стоимость: бесплатно\n\n"
        "Важно: время указано по Москве.\n\nПеред оплатой подтвердите согласие на обработку персональных данных.",
        reply_markup=selection_consent_keyboard(),
    )


@router.callback_query(F.data == "client:selection_consent_yes")
async def selection_15_consent_yes(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Этот обработчик перехватывает согласие для 15-минутного подбора.
    Если в state нет selection_selected_slot, обычный сценарий должен обработаться старым хендлером.
    """

    await callback.answer()

    
    await state.set_state(SelectionStates.selection_waiting_phone)

    from app.keyboards.client import selection_phone_keyboard

    await callback.message.edit_text(
        "Введите номер телефона для связи.\n\n"
        "Например: +7 999 123-45-67\n\n"
        "Если сейчас не хотите указывать телефон, нажмите «Пропустить телефон».",
        reply_markup=selection_phone_keyboard(),
    )


@router.message(SelectionStates.selection_waiting_phone)
async def selection_15_phone(message: Message, state: FSMContext) -> None:
    from app.keyboards.client import selection_email_keyboard, selection_phone_keyboard

    phone = message.text.strip()

    if len(phone) < 7:
        await message.answer(
            "Пожалуйста, введите корректный номер телефона, "
            "или нажмите «Пропустить телефон».",
            reply_markup=selection_phone_keyboard(),
        )
        return

    await state.update_data(selection_phone=phone)
    await state.set_state(SelectionStates.selection_waiting_email)

    await message.answer(
        "Укажите email для чека.\n\n"
        "Если не хотите указывать email, чек/подтверждение останется в Telegram.",
        reply_markup=selection_email_keyboard(),
    )


@router.callback_query(F.data == "client:selection_skip_phone")
async def selection_15_skip_phone(callback: CallbackQuery, state: FSMContext) -> None:
    from app.keyboards.client import selection_email_keyboard

    await callback.answer()
    await state.update_data(selection_phone=None)
    await state.set_state(SelectionStates.selection_waiting_email)

    await callback.message.edit_text(
        "Укажите email для чека.\n\n"
        "Если не хотите указывать email, чек/подтверждение останется в Telegram.",
        reply_markup=selection_email_keyboard(),
    )


@router.message(SelectionStates.selection_waiting_email)
async def selection_15_email_text(message: Message, state: FSMContext) -> None:
    email = message.text.strip()

    if "@" not in email or "." not in email:
        await message.answer("Введите корректный email или нажмите «Пропустить email».")
        return

    await state.update_data(selection_email=email)
    await create_selection_15_booking_and_payment(message, state)


@router.callback_query(F.data == "client:selection_skip_email")
async def selection_15_skip_email(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(selection_email=None)
    await create_selection_15_booking_and_payment(callback.message, state, telegram_user=callback.from_user)


async def create_selection_15_booking_and_payment(
    message: Message,
    state: FSMContext,
    telegram_user=None,
) -> None:
    from app.services.selection_15 import get_or_create_selection_specialist
    from app.services.bookings import create_booking_from_generated_slot
    from app.services.yookassa_payments import create_yookassa_payment_for_booking
    from app.keyboards.client import back_to_menu_keyboard

    data = await state.get_data()
    selected_slot = data.get("selection_selected_slot")

    if not selected_slot:
        await message.answer(
            "Не удалось найти выбранное время. Возможно, это время только что заняли. Попробуйте выбрать другое время.",
            reply_markup=back_to_menu_keyboard(),
        )
        await state.clear()
        return

    user = telegram_user or message.from_user

    specialist = await get_or_create_selection_specialist()

    client_answers_snapshot = {
        "service": "15-минутный подбор специалистом",
        "goal": "Помочь клиенту выбрать подходящего психолога",
    }

    booking = await create_booking_from_generated_slot(
        telegram_id=user.id,
        username=user.username,
        full_name=user.full_name,
        phone=data.get("selection_phone"),
        email=data.get("selection_email"),
        psychologist_id=specialist.id,
        slot_data={
            "date": selected_slot["date"],
            "time": selected_slot["time"],
            "duration": selected_slot["duration"],
        },
        price=selected_slot["price"],
        client_answers=client_answers_snapshot,
        client_comment="15-минутный подбор специалистом",
    )

    if not booking:
        await message.answer(
            "Не удалось создать запись. Возможно, это время только что заняли. Попробуйте выбрать другое время.",
            reply_markup=back_to_menu_keyboard(),
        )
        await state.clear()
        return

    booking.booking_type = "selection_15min"

    from app.database import async_session

    async with async_session() as session:
        db_booking = await session.get(Booking, booking.id)
        if db_booking:
            db_booking.booking_type = "selection_15min"
            await session.commit()

    if selected_slot["price"] <= 0:
        from app.database import async_session
        from app.services.notifications import send_payment_success_notifications
        from app.services.admin_notifications import notify_admins

        async with async_session() as session:
            db_booking = await session.get(Booking, booking.id)
            if db_booking:
                db_booking.status = "paid"
                db_booking.payment_status = "paid"
                db_booking.booking_type = "selection_15min"
                await session.commit()

        from app.services.bookings import try_auto_create_meeting_link

        await try_auto_create_meeting_link(booking.id)

        await send_payment_success_notifications(booking.id)

        await notify_admins(
            "Админ-уведомление ✅\n\n"
            "Создана бесплатная консультация по подбору психолога.\n\n"
            f"Запись №{booking.id}\n"
            f"Клиент: {user.full_name or user.username or user.id}\n"
            f"Телефон: {data.get('selection_phone') or 'не указан'}\n"
            f"Дата: {selected_slot['date']}\n"
            f"Время: {selected_slot['time']}\n"
            f"Длительность: {minutes_declension(selected_slot['duration'])}"
        )

        await state.clear()

        await message.answer(
            "Запись на бесплатную консультацию по подбору психолога подтверждена ✅\n\n"
            "Время указано по Москве.\n\n"
            f"Дата: {selected_slot['date']}\n"
            f"Время: {selected_slot['time']}\n"
            f"Длительность: {minutes_declension(selected_slot['duration'])}\n\n"
            "За 1 час до встречи бот пришлёт напоминание.\n"
            "За 10 минут до начала Вы получите ссылку на видеовстречу.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    payment_url = await create_yookassa_payment_for_booking(
        telegram_id=user.id,
        booking_id=booking.id,
    )

    if not payment_url:
        await message.answer(
            "Запись создана, но не удалось создать платёж.\n\n"
            "Пожалуйста, обратитесь к администратору.",
            reply_markup=back_to_menu_keyboard(),
        )
        await state.clear()
        return

    await state.clear()

    await message.answer(
        "Запись на 15-минутный подбор создана ✅\n\n"
        f"Дата: {selected_slot['date']}\n"
        f"Время: {selected_slot['time']}\n"
        f"Длительность: {minutes_declension(selected_slot['duration'])}\n"
        f"Стоимость: {selected_slot['price']} ₽\n\n"
        "Для подтверждения записи перейдите к оплате:\n"
        f"{payment_url}",
        reply_markup=back_to_menu_keyboard(),
    )


@router.callback_query(F.data == "client:back:q1")
async def back_to_q1_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    from app.keyboards.client import request_keyboard

    await callback.message.edit_text(
        "С каким запросом Вы хотите обратиться к психологу?",
        reply_markup=request_keyboard((await state.get_data()).get("requests", [])),
    )


@router.callback_query(F.data == "client:back:q2")
async def back_to_q2_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    from app.keyboards.client import expectation_keyboard, add_back_button

    await callback.message.edit_text(
        "Что Вы хотите получить от работы с психологом?",
        reply_markup=add_back_button(expectation_keyboard((await state.get_data()).get("expectations", [])), "client:back:q1"),
    )


@router.callback_query(F.data == "client:back:q3")
async def back_to_q3_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    from app.keyboards.client import therapy_experience_keyboard, add_back_button

    await callback.message.edit_text(
        "Был ли у Вас опыт работы с психологом?",
        reply_markup=add_back_button(therapy_experience_keyboard(), "client:back:q2"),
    )


@router.callback_query(F.data == "client:back:q4")
async def back_to_q4_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    from app.keyboards.client import gender_keyboard, add_back_button

    await callback.message.edit_text(
        "Есть ли предпочтение по полу психолога?",
        reply_markup=add_back_button(gender_keyboard(), "client:back:q3"),
    )


@router.callback_query(F.data == "client:back:q6")
async def back_to_q6_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    from app.keyboards.client import budget_keyboard, add_back_button

    await callback.message.edit_text(
        "Какой бюджет Вам комфортен?",
        reply_markup=add_back_button(budget_keyboard(), "client:back:q4"),
    )


@router.callback_query(F.data == "client:back:q8")
async def back_to_q8_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    from app.keyboards.client import age_keyboard, add_back_button

    await callback.message.edit_text(
        "Ваш возраст?",
        reply_markup=add_back_button(age_keyboard(), "client:back:q6"),
    )



@router.callback_query(F.data.startswith("client:q1_toggle:"))
async def q1_toggle_multi_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    code = callback.data.split(":")[-1]
    data = await state.get_data()
    selected = list(data.get("requests", []))
    if code in selected:
        selected.remove(code)
    else:
        selected.append(code)
    await state.update_data(requests=selected)
    await callback.message.edit_reply_markup(reply_markup=request_keyboard(selected))


@router.callback_query(F.data == "client:q1_done")
async def q1_done_multi_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    selected = list(data.get("requests", []))
    if not selected:
        await callback.answer("Выберите хотя бы один вариант", show_alert=True)
        return
    await state.update_data(request=selected[0])
    if "other" in selected:
        await state.set_state(ClientSelectionStates.request_other_text)
        await callback.message.edit_text(REQUEST_OTHER_TEXT)
        return
    await callback.message.edit_text(
        QUESTION_2_TEXT,
        reply_markup=add_back_button(expectation_keyboard([]), "client:back:q1"),
    )


@router.callback_query(F.data.startswith("client:q2_toggle:"))
async def q2_toggle_multi_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    code = callback.data.split(":")[-1]
    data = await state.get_data()
    selected = list(data.get("expectations", []))
    if code in selected:
        selected.remove(code)
    else:
        selected.append(code)
    await state.update_data(expectations=selected)
    await callback.message.edit_reply_markup(
        reply_markup=add_back_button(expectation_keyboard(selected), "client:back:q1")
    )


@router.callback_query(F.data == "client:q2_done")
async def q2_done_multi_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    selected = list(data.get("expectations", []))
    if not selected:
        await callback.answer("Выберите хотя бы один вариант", show_alert=True)
        return
    await state.update_data(expectation=selected[0])
    await callback.message.edit_text(
        QUESTION_3_TEXT,
        reply_markup=add_back_button(therapy_experience_keyboard(), "client:back:q2"),
    )


@router.callback_query(F.data == "client:find_by_name")
async def find_psychologist_by_name_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(ClientSelectionStates.find_psychologist_name)
    await callback.message.answer(
        "Введите имя, фамилию или часть ФИО психолога, с которым хотите записаться."
    )


@router.message(ClientSelectionStates.find_psychologist_name, F.text != "Начать заново")
async def find_psychologist_by_name_value(message: Message, state: FSMContext) -> None:
    query = (message.text or "").strip().casefold()
    if len(query) < 2:
        await message.answer("Введите хотя бы 2 символа имени или фамилии.")
        return
    psychologists = await get_active_psychologists_with_slots()
    found = [item for item in psychologists if query in (item.get("name") or "").casefold()]
    for item in found:
        item["slots"] = filter_future_slots(item.get("slots", []))
    found = [item for item in found if item.get("slots")]
    if not found:
        # main_menu_keyboard() already gives exactly the three actions asked
        # for here: retry the name search, get matched by questionnaire, or
        # go back to the rest of the menu - no separate keyboard needed.
        await message.answer(
            "К сожалению, сейчас мы не нашли психолога по этому запросу. "
            "Проверьте, пожалуйста, правильность имени или фамилии либо "
            "попробуйте подобрать специалиста по вашей ситуации 💚",
            reply_markup=main_menu_keyboard(),
        )
        await state.clear()
        return
    await state.update_data(
        matched_psychologists=found,
        current_psychologist_index=0,
        matching_mode="name_search",
    )
    await state.set_state(None)
    await show_psychologist_card(message, state, found[0], 0, len(found), edit=False)


@router.message(F.text == "Кабинет психолога")
async def reply_open_psychologist(message: Message, state: FSMContext) -> None:
    await state.clear()
    from app.services.psychologist_profile import get_psychologist_by_telegram_id
    psychologist = await get_psychologist_by_telegram_id(message.from_user.id)
    if not psychologist:
        await message.answer("У Вас пока нет доступа к кабинету психолога.")
        return
    from app.handlers.psychologist import psych4_main_keyboard
    await message.answer("Кабинет психолога\n\nВыберите действие:", reply_markup=psych4_main_keyboard())


@router.message(F.text == "Админ-панель")
async def reply_open_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    from app.handlers.admin import is_admin_user, admin_panel_keyboard
    if not is_admin_user(message.from_user.id):
        await message.answer("У Вас нет доступа к админ-панели.")
        return
    await message.answer("Админ-панель\n\nВыберите действие:", reply_markup=admin_panel_keyboard())
