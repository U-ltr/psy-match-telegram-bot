"""Shared option labels for the psychologist profile editor.

The actual keyboards live in app/handlers/psychologist.py (the psych4_*
functions) next to the handlers that use them - this module now only holds
the label dictionaries, since a psychologist's profile options are shared
between the psychologist's own cabinet and (via the same codes) the client
questionnaire / matching logic.
"""

SPECIALIZATION_OPTIONS = {
    "clinical": "Клинический психолог",
    "family_therapist": "Семейный психолог / системный терапевт",
    "child_teen": "Детский и подростковый психолог",
    "psychoanalyst": "Психоаналитик",
    "cbt_therapist": "Когнитивно-поведенческий терапевт (КПТ)",
    "gestalt_therapist": "Гештальт-терапевт",
}

HELP_TOPIC_OPTIONS = {
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
    "crisis": "Кризисы",
}


STYLE_OPTIONS = {
    "supportive": "Поддерживающий",
    "deep": "Глубинный",
    "practical": "Практический",
    "cbt": "КПТ / работа с мыслями",
    "behavior": "Работа с поведением",
    "universal": "Универсальный",
}
