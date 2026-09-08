"""The one place that turns a Booking.client_answers dict into human text.

Every code here must match the callback_data values actually produced by
app/keyboards/client.py's questionnaire keyboards - see that file (or the
docstring on each map below) for where a given code comes from. If you add
a new questionnaire option, add its label here in the same change, or it
will render as a raw code to whoever reads booking answers (client answers
in the psychologist/admin "bookings" screens).
"""

QUESTION_TITLES = {
    "requests": "Запрос",
    "request_other": "Уточнение по запросу",
    "expectations": "Ожидание от терапии",
    "therapy_experience": "Опыт терапии",
    "preferred_gender": "Пожелание к специалисту",
    "start_time": "Когда удобно начать",
    "budget": "Комфортный бюджет",
    "priorities": "Что важно при выборе",
    "age_group": "Возраст",
    "comment": "Комментарий клиента",
}

# request_keyboard() in keyboards/client.py - "с чем хотите обратиться"
REQUEST_VALUE_TITLES = {
    "anxiety_stress": "Тревога и стресс",
    "relationships": "Отношения",
    "selfesteem": "Самооценка",
    "burnout_work": "Выгорание и работа",
    "depressive_state": "Депрессивное состояние",
    "loss": "Утрата",
    "family": "Семейные вопросы",
    "addictions": "Зависимости",
    "guilt": "Чувство вины",
    "loneliness": "Одиночество",
    "self_understanding": "Хочу разобраться в себе",
    "other": "Другое",
}

# expectation_keyboard() - "что ожидаете от работы с психологом"
EXPECTATION_VALUE_TITLES = {
    "acceptance": "Хочу, чтобы меня выслушали и приняли без осуждения",
    "reasons": "Хочу лучше понять причины своих переживаний",
    "cope": "Хочу научиться справляться со сложными ситуациями и эмоциями",
    "patterns": "Хочу разобраться, какие привычки или модели поведения мешают",
    "thoughts": "Хочу лучше понимать и контролировать свои мысли",
    "unknown": "Пока не знаю, нужна помощь с выбором",
}

# therapy_experience_keyboard()
THERAPY_EXPERIENCE_TITLES = {
    "none": "Не было опыта",
    "positive": "Да, положительный",
    "negative": "Да, отрицательный",
}

# gender_keyboard() - preferred specialist gender
PREFERRED_GENDER_TITLES = {
    "any": "Неважно",
    "female": "Женщина",
    "male": "Мужчина",
}

# start_time_keyboard()
START_TIME_TITLES = {
    "today": "Сегодня",
    "week": "В течение недели",
    "month": "В ближайший месяц",
    "specific_time": "Конкретное время",
}

# budget_keyboard()
BUDGET_TITLES = {
    "under_2000": "До 2 000 ₽",
    "2000_3000": "2 000–3 000 ₽",
    "3000_5000": "3 000–5 000 ₽",
    "5000_plus": "5 000 ₽ и выше",
    "not_important": "Цена не главный критерий",
}

# priorities_keyboard()
PRIORITIES_TITLES = {
    "request": "Совпадение по запросу",
    "price": "Цена",
    "time": "Ближайшее удобное время",
    "gender": "Пол специалиста",
    "experience": "Опыт психолога",
    "style": "Стиль работы",
    "duration": "Длительность консультации",
}

# age_keyboard()
AGE_GROUP_TITLES = {
    "under_18": "До 18 лет",
    "18_24": "18–24 года",
    "25_34": "25–34 года",
    "35_44": "35–44 года",
    "45_plus": "45 лет и старше",
}

# which value-map applies to which client_answers key
FIELD_VALUE_MAPS = {
    "requests": REQUEST_VALUE_TITLES,
    "expectations": EXPECTATION_VALUE_TITLES,
    "therapy_experience": THERAPY_EXPERIENCE_TITLES,
    "preferred_gender": PREFERRED_GENDER_TITLES,
    "start_time": START_TIME_TITLES,
    "budget": BUDGET_TITLES,
    "priorities": PRIORITIES_TITLES,
    "age_group": AGE_GROUP_TITLES,
}

# fields that are free text, not codes - shown as-is
FREE_TEXT_FIELDS = {"request_other", "comment"}

# internal/legacy keys that should never be shown even if present in the dict
HIDDEN_FIELDS = {"request", "expectation", "selected_psychologist_id", "selected_slot", "booking_id"}


def humanize_field_value(field: str, value):
    if isinstance(value, list):
        rendered = [humanize_field_value(field, item) for item in value if item not in (None, "")]
        return ", ".join(rendered) if rendered else None

    if value in (None, ""):
        return None

    value_map = FIELD_VALUE_MAPS.get(field)
    if value_map is not None:
        return value_map.get(str(value), str(value))

    return str(value)


# A psychologist can add their own free-text option (e.g. "Работа с
# фобиями") to specializations/help_topics/styles instead of being limited
# to the fixed catalog - see app/handlers/psychologist.py's
# psych4_add_custom_option_start_handler. Stored inline in the same JSON
# list as the predefined codes, marked with this prefix so format_code_list
# (below) can tell a psychologist-authored label apart from an internal
# snake_case code that's simply missing from the options map (the latter
# must still be dropped, not shown raw - see its docstring).
CUSTOM_OPTION_PREFIX = "custom:"


def format_code_list(values: list | None, options: dict) -> str:
    """Render a list of internal option codes (Psychologist.specializations /
    help_topics / styles / therapy_experience_fit - anything stored as a
    JSON list of short English/snake_case codes, optionally mixed with
    psychologist-authored free text prefixed with CUSTOM_OPTION_PREFIX) as
    a comma-separated, human-readable Russian string, using the given
    {code: label} map (e.g. app.keyboards.psychologist.SPECIALIZATION_OPTIONS).

    This is the ONE place that should ever turn such a code list into
    display text - every psychologist card, search result, admin view and
    the psychologist's own cabinet must go through this instead of a local
    ad hoc dict or a bare ", ".join(values), or a raw internal code (e.g.
    "family_therapist") ends up shown to a client/psychologist/admin.

    A code missing from `options` (stale data, a renamed option) is
    dropped rather than shown raw - a gap in the list is a far smaller
    problem than leaking an internal code to a user. A CUSTOM_OPTION_PREFIX
    entry is never looked up in `options` - it's shown as the psychologist
    typed it, prefix stripped.
    """
    if not values:
        return "не указано"

    labels = []
    for value in values:
        if isinstance(value, str) and value.startswith(CUSTOM_OPTION_PREFIX):
            custom_text = value[len(CUSTOM_OPTION_PREFIX):].strip()
            if custom_text:
                labels.append(custom_text)
            continue

        label = options.get(value)
        if label:
            labels.append(label)

    return ", ".join(labels) if labels else "не указано"


def format_client_answers(answers: dict | None, comment: str | None = None) -> str:
    """Render a Booking.client_answers dict as human-readable Russian text.

    Empty/unanswered fields are omitted entirely (never shown as
    'None'/'[]'/'unknown'-the-raw-string). If nothing at all was answered,
    returns the explicit "не указаны" line the spec asks for.
    """
    lines = []

    if answers:
        for field, title in QUESTION_TITLES.items():
            if field in HIDDEN_FIELDS:
                continue

            raw_value = answers.get(field)
            if field in FREE_TEXT_FIELDS:
                text_value = str(raw_value).strip() if raw_value else None
            else:
                text_value = humanize_field_value(field, raw_value)

            if not text_value:
                continue

            lines.append(f"{title}: {text_value}")

    body = "\n".join(lines) if lines else "Ответы клиента: не указаны"

    # `comment` kept as a separate optional param for backward compatibility
    # with callers that store it outside client_answers (e.g. Booking.client_comment)
    if comment and "comment" not in (answers or {}):
        body += f"\n\nКомментарий клиента:\n{comment}"

    return body


# Booking.status / Booking.payment_status combinations actually produced by
# services/bookings.py and services/yookassa_payments.py - never show these
# raw values to a psychologist/admin, always go through this.
BOOKING_STATUS_TITLES = {
    ("reserved", "pending"): "Ожидает оплаты",
    ("paid", "paid"): "Оплачено",
    ("cancelled", "cancelled"): "Отменено клиентом",
    ("cancelled", "expired"): "Отменено (истёк резерв на оплату)",
}


def format_booking_status(status: str | None, payment_status: str | None) -> str:
    label = BOOKING_STATUS_TITLES.get((status, payment_status))
    if label:
        return label
    # Unknown combination (shouldn't happen) - still avoid a bare code dump
    return f"{status or '—'} / {payment_status or '—'}"


def pluralize(n: int, one: str, few: str, many: str) -> str:
    """Standard Russian plural-form selection for a count `n`: 1/21/31.. ->
    `one`, 2-4/22-24/32-34.. -> `few`, 0/5-20/25-30.. -> `many`, with the
    11-14 exception (11..14 is always `many` regardless of the last digit -
    "11 лет", not "11 год"). This is the ONE place this rule should live -
    every count shown to a client/psychologist/admin (years, minutes,
    bookings, ...) must go through this, not a hardcoded word.
    """
    n_abs = abs(int(n))
    last_two = n_abs % 100
    last = n_abs % 10

    if 11 <= last_two <= 14:
        return many
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


def years_declension(n: int) -> str:
    """21 год, 2 года, 5 лет, 11 лет, 22 года, 0 лет ..."""
    return f"{n} {pluralize(n, 'год', 'года', 'лет')}"


def minutes_declension(n: int) -> str:
    """1 минута, 2 минуты, 5 минут, 11 минут, 21 минута, 30 минут ..."""
    return f"{n} {pluralize(n, 'минута', 'минуты', 'минут')}"


def records_declension(n: int) -> str:
    """1 запись, 2 записи, 5 записей, 11 записей, 21 запись ..."""
    return f"{n} {pluralize(n, 'запись', 'записи', 'записей')}"
