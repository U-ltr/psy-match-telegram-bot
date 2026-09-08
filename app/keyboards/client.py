from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подобрать психолога", callback_data="client:start_matching")],
            [InlineKeyboardButton(text="Ближайший психолог", callback_data="client:nearest_psychologists")],
            [InlineKeyboardButton(text="Найти психолога по ФИО", callback_data="client:find_by_name")],
            [InlineKeyboardButton(text="Бесплатная консультация по подбору психолога", callback_data="client:selection_15")],
            [InlineKeyboardButton(text="Помощь", callback_data="client:help")],
        ]
    )


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
        ]
    )


def request_keyboard(selected: list[str] | None = None) -> InlineKeyboardMarkup:
    selected = selected or []
    options = [
        ("anxiety_stress", "Тревога и стресс"),
        ("relationships", "Отношения"),
        ("selfesteem", "Самооценка"),
        ("burnout_work", "Выгорание и работа"),
        ("depressive_state", "Депрессивное состояние"),
        ("loss", "Утрата"),
        ("family", "Семейные вопросы"),
        ("addictions", "Зависимости"),
        ("guilt", "Чувство вины"),
        ("loneliness", "Одиночество"),
        ("self_understanding", "Хочу разобраться в себе"),
        ("other", "Другое"),
    ]
    rows = [[InlineKeyboardButton(text=("✅ " if code in selected else "") + title, callback_data=f"client:q1_toggle:{code}")] for code, title in options]
    rows.append([InlineKeyboardButton(text="Готово", callback_data="client:q1_done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def expectation_keyboard(selected: list[str] | None = None) -> InlineKeyboardMarkup:
    selected = selected or []
    options = [
        ("acceptance", "Выслушали и приняли без осуждения"),
        ("reasons", "Понять причины переживаний"),
        ("cope", "Научиться справляться с эмоциями"),
        ("patterns", "Разобраться с привычками и поведением"),
        ("thoughts", "Лучше понимать и контролировать мысли"),
        ("unknown", "Пока не знаю"),
    ]
    rows = [[InlineKeyboardButton(text=("✅ " if code in selected else "") + title, callback_data=f"client:q2_toggle:{code}")] for code, title in options]
    rows.append([InlineKeyboardButton(text="Готово", callback_data="client:q2_done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def therapy_experience_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Нет", callback_data="client:q3:none")],
            [InlineKeyboardButton(text="Да, положительный", callback_data="client:q3:positive")],
            [InlineKeyboardButton(text="Да, отрицательный", callback_data="client:q3:negative")],
        ]
    )


def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Неважно", callback_data="client:q4:any")],
            [InlineKeyboardButton(text="Женщина", callback_data="client:q4:female")],
            [InlineKeyboardButton(text="Мужчина", callback_data="client:q4:male")],
        ]
    )


def budget_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="До 2 000 ₽", callback_data="client:q6:under_2000")],
            [InlineKeyboardButton(text="2 000–3 000 ₽", callback_data="client:q6:2000_3000")],
            [InlineKeyboardButton(text="3 000–5 000 ₽", callback_data="client:q6:3000_5000")],
            [InlineKeyboardButton(text="5 000 ₽ и выше", callback_data="client:q6:5000_plus")],
            [InlineKeyboardButton(text="Цена не главный критерий", callback_data="client:q6:not_important")],
        ]
    )


def age_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="До 18", callback_data="client:q8:under_18")],
            [InlineKeyboardButton(text="18–24", callback_data="client:q8:18_24")],
            [InlineKeyboardButton(text="25–34", callback_data="client:q8:25_34")],
            [InlineKeyboardButton(text="35–44", callback_data="client:q8:35_44")],
            [InlineKeyboardButton(text="45+", callback_data="client:q8:45_plus")],
            [InlineKeyboardButton(text="Пропустить", callback_data="client:q8:skip")],
        ]
    )


def comment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, написать комментарий", callback_data="client:q9:yes")],
            [InlineKeyboardButton(text="Нет, перейти к подбору", callback_data="client:q9:no")],
        ]
    )


def summary_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подобрать психолога", callback_data="client:show_match")],
            [InlineKeyboardButton(text="Начать заново", callback_data="client:restart")],
        ]
    )


def psychologist_card_keyboard(psychologist_id: int | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Выбрать время", callback_data="client:choose_slot")],
            [
                InlineKeyboardButton(text="⬅️ Предыдущий", callback_data="client:psych_prev"),
                InlineKeyboardButton(text="Следующий ➡️", callback_data="client:psych_next"),
            ],
            [InlineKeyboardButton(text="Бесплатная консультация по подбору психолога", callback_data="client:selection_15")],
        ]
    )


def durations_keyboard(psychologist_id: int, durations: list[dict], back_callback_data: str) -> InlineKeyboardMarkup:
    rows = []

    for item in durations:
        minutes = item["minutes"]
        price = item["price"]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{minutes} мин — {price} ₽",
                    callback_data=f"client:duration:{psychologist_id}:{minutes}",
                )
            ]
        )

    rows.append([InlineKeyboardButton(text="Назад", callback_data=back_callback_data)])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def slots_keyboard(psychologist_id: int, slots: list[dict]) -> InlineKeyboardMarkup:
    rows = []

    for index, slot in enumerate(slots):
        text = f"{slot['date']} · {slot['time']} · {slot['duration']} мин"
        rows.append(
            [
                InlineKeyboardButton(
                    text=text,
                    callback_data=f"client:slot:{psychologist_id}:{index}",
                )
            ]
        )


    return InlineKeyboardMarkup(inline_keyboard=rows)


def after_booking_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Перейти к оплате", callback_data="client:payment_stub")],
            [InlineKeyboardButton(text="Начать заново", callback_data="client:restart")],
        ]
    )


def booking_consent_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, согласен", callback_data="client:booking_consent:yes")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="client:booking_consent:no")],
        ]
    )


def booking_phone_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пропустить телефон", callback_data="client:booking_phone:skip")],
            [InlineKeyboardButton(text="Отмена", callback_data="client:restart")],
        ]
    )


def booking_email_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пропустить email", callback_data="client:booking_email:skip")],
            [InlineKeyboardButton(text="Отмена", callback_data="client:restart")],
        ]
    )


def booking_created_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Перейти к оплате", callback_data="client:payment_stub")],
            [InlineKeyboardButton(text="Отменить запись", callback_data=f"client:cancel_booking:{booking_id}")],
            [InlineKeyboardButton(text="Главное меню", callback_data="client:restart")],
        ]
    )


def selection_slots_keyboard(slots: list[dict]):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = []

    for index, slot in enumerate(slots):
        keyboard.append([
            InlineKeyboardButton(
                text=f"{slot['date']} в {slot['time']} — {slot['price']} ₽",
                callback_data=f"client:selection_slot:{index}",
            )
        ])

    keyboard.append([
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def selection_phone_keyboard():
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пропустить телефон", callback_data="client:selection_skip_phone")],
        ]
    )


def selection_email_keyboard():
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пропустить email", callback_data="client:selection_skip_email")],
        ]
    )


def selection_consent_keyboard():
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Согласен / согласна", callback_data="client:selection_consent_yes")],
        ]
    )


def restart_reply_keyboard() -> ReplyKeyboardMarkup:
    """The client's persistent bottom keyboard - kept to exactly one
    button on purpose (see the requirements). Psychologists and admins
    have their own separate entry points (/psychologist and /admin) and
    do not need - and should not see - anything added here."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Начать заново")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Начать заново доступно через кнопку клавиатуры",
    )


def add_back_button(markup: InlineKeyboardMarkup, callback_data: str) -> InlineKeyboardMarkup:
    keyboard = [row[:] for row in markup.inline_keyboard]
    keyboard.append([
        InlineKeyboardButton(
            text="Вернуться к предыдущему вопросу",
            callback_data=callback_data,
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
