"""Human-readable formatting: app/services/answer_formatting.py."""
from app.services.answer_formatting import (
    pluralize,
    years_declension,
    minutes_declension,
    records_declension,
    format_booking_status,
    format_client_answers,
    format_code_list,
    CUSTOM_OPTION_PREFIX,
)


def test_years_declension_one():
    assert years_declension(1) == "1 год"
    assert years_declension(21) == "21 год"
    assert years_declension(31) == "31 год"


def test_years_declension_two_to_four():
    assert years_declension(2) == "2 года"
    assert years_declension(3) == "3 года"
    assert years_declension(4) == "4 года"
    assert years_declension(22) == "22 года"
    assert years_declension(23) == "23 года"


def test_years_declension_five_to_twenty():
    assert years_declension(0) == "0 лет"
    assert years_declension(5) == "5 лет"
    assert years_declension(6) == "6 лет"
    assert years_declension(10) == "10 лет"


def test_years_declension_eleven_to_fourteen_exception():
    # The 11-14 exception applies regardless of the last digit, e.g. "11"
    # ends in 1 but is NOT "11 год" - it's "11 лет".
    assert years_declension(11) == "11 лет"
    assert years_declension(12) == "12 лет"
    assert years_declension(13) == "13 лет"
    assert years_declension(14) == "14 лет"


def test_years_declension_matches_across_hundreds():
    assert years_declension(111) == "111 лет"  # still the 11-14 exception (11 % 100 range)
    assert years_declension(101) == "101 год"
    assert years_declension(102) == "102 года"


def test_format_booking_status_known_combinations():
    assert format_booking_status("reserved", "pending") == "Ожидает оплаты"
    assert format_booking_status("paid", "paid") == "Оплачено"
    assert format_booking_status("cancelled", "cancelled") == "Отменено клиентом"
    assert format_booking_status("cancelled", "expired") == "Отменено (истёк резерв на оплату)"


def test_format_booking_status_unknown_combination_falls_back_without_crashing():
    result = format_booking_status("weird", "state")
    assert "weird" in result
    assert "state" in result


def test_format_booking_status_never_shows_python_none():
    # Guards against a literal "None" string leaking to a psychologist/admin.
    result = format_booking_status(None, None)
    assert "None" not in result


def test_format_client_answers_empty_returns_explicit_not_specified():
    assert format_client_answers(None) == "Ответы клиента: не указаны"
    assert format_client_answers({}) == "Ответы клиента: не указаны"


def test_format_client_answers_omits_unanswered_fields():
    answers = {"requests": ["anxiety_stress"], "budget": None, "priorities": []}
    text = format_client_answers(answers)
    assert "Запрос: Тревога и стресс" in text
    assert "Бюджет" not in text
    assert "Что важно при выборе" not in text


def test_format_client_answers_hides_legacy_keys():
    answers = {"request": "old raw value", "expectation": "old raw value"}
    text = format_client_answers(answers)
    assert "old raw value" not in text


def test_format_client_answers_never_shows_raw_code_for_known_field():
    answers = {"budget": "under_2000"}
    text = format_client_answers(answers)
    assert "under_2000" not in text
    assert "2 000" in text


def test_format_client_answers_unknown_code_falls_back_to_raw_value_not_crash():
    answers = {"budget": "some_new_code_not_in_map_yet"}
    text = format_client_answers(answers)
    assert "some_new_code_not_in_map_yet" in text


def test_format_client_answers_appends_comment_when_separate():
    text = format_client_answers({"requests": ["loss"]}, comment="Хочу поговорить о маме")
    assert "Хочу поговорить о маме" in text


def test_pluralize_is_the_single_shared_rule_behind_every_declined_word():
    # one / few / many for a made-up noun, confirming the primitive itself
    # (not just years_declension) gets the 1 / 2-4 / 0,5-20 / 11-14 split right.
    assert pluralize(1, "штука", "штуки", "штук") == "штука"
    assert pluralize(2, "штука", "штуки", "штук") == "штуки"
    assert pluralize(4, "штука", "штуки", "штук") == "штуки"
    assert pluralize(5, "штука", "штуки", "штук") == "штук"
    assert pluralize(0, "штука", "штуки", "штук") == "штук"
    assert pluralize(11, "штука", "штуки", "штук") == "штук"
    assert pluralize(14, "штука", "штуки", "штук") == "штук"
    assert pluralize(21, "штука", "штуки", "штук") == "штука"
    assert pluralize(22, "штука", "штуки", "штук") == "штуки"
    assert pluralize(25, "штука", "штуки", "штук") == "штук"
    assert pluralize(111, "штука", "штуки", "штук") == "штук"  # 11-14 exception at any hundred
    assert pluralize(121, "штука", "штуки", "штук") == "штука"


def test_minutes_declension_covers_every_bookable_duration():
    # These are the exact durations offered in the booking flow (15/30/50/60/90)
    # plus the 11-14 exception and a couple of round numbers.
    assert minutes_declension(1) == "1 минута"
    assert minutes_declension(15) == "15 минут"
    assert minutes_declension(20) == "20 минут"  # RESERVATION_MINUTES
    assert minutes_declension(30) == "30 минут"
    assert minutes_declension(50) == "50 минут"
    assert minutes_declension(60) == "60 минут"
    assert minutes_declension(90) == "90 минут"
    assert minutes_declension(11) == "11 минут"
    assert minutes_declension(21) == "21 минута"
    assert minutes_declension(22) == "22 минуты"


def test_minutes_declension_never_shows_none_or_negative_crash():
    # duration is sometimes read via getattr(..., 0) as a display fallback -
    # 0 must render as a real word, not blow up or print "0 минут" wrong.
    assert minutes_declension(0) == "0 минут"


def test_records_declension_one_few_many():
    assert records_declension(1) == "1 запись"
    assert records_declension(2) == "2 записи"
    assert records_declension(5) == "5 записей"
    assert records_declension(11) == "11 записей"
    assert records_declension(21) == "21 запись"


# ---- format_code_list ---------------------------------------------------
# The single centralized function every psychologist card / search result /
# admin view / the psychologist's own cabinet must use to turn a list of
# internal codes (specializations, help_topics, styles,
# therapy_experience_fit) into Russian labels. Added after a real bug where
# a raw code like "family_therapist" leaked straight into a client-facing
# card because several places each had their own (sometimes wrong) local
# mapping instead of one shared source.

_SAMPLE_OPTIONS = {
    "family_therapist": "Семейный психолог / системный терапевт",
    "clinical": "Клинический психолог",
}


def test_format_code_list_maps_known_codes_to_labels():
    assert format_code_list(["family_therapist"], _SAMPLE_OPTIONS) == "Семейный психолог / системный терапевт"


def test_format_code_list_joins_multiple_labels_in_order():
    result = format_code_list(["family_therapist", "clinical"], _SAMPLE_OPTIONS)
    assert result == "Семейный психолог / системный терапевт, Клинический психолог"


def test_format_code_list_never_leaks_a_raw_unknown_code():
    # A code missing from the map (stale data, a renamed option) must be
    # dropped, never shown to the user as-is.
    result = format_code_list(["some_unknown_code"], _SAMPLE_OPTIONS)
    assert "some_unknown_code" not in result
    assert result == "не указано"


def test_format_code_list_drops_only_the_unknown_code_keeps_the_known_ones():
    result = format_code_list(["family_therapist", "some_unknown_code"], _SAMPLE_OPTIONS)
    assert "some_unknown_code" not in result
    assert result == "Семейный психолог / системный терапевт"


def test_format_code_list_empty_or_none_shows_placeholder_not_blank():
    assert format_code_list([], _SAMPLE_OPTIONS) == "не указано"
    assert format_code_list(None, _SAMPLE_OPTIONS) == "не указано"


# ---- format_code_list + psychologist-authored custom options -----------
# A psychologist can add their own free-text specialization/help_topic/
# style instead of being limited to the fixed catalog (see
# app/handlers/psychologist.py: psych4_add_custom_option_start_handler).
# It's stored inline in the same list, marked with CUSTOM_OPTION_PREFIX, so
# format_code_list must show it verbatim (prefix stripped) rather than
# trying to look it up in the fixed options map.

def test_format_code_list_shows_custom_option_text_verbatim():
    values = [f"{CUSTOM_OPTION_PREFIX}Работа с фобиями"]
    assert format_code_list(values, _SAMPLE_OPTIONS) == "Работа с фобиями"


def test_format_code_list_mixes_known_codes_and_custom_options_in_order():
    values = ["family_therapist", f"{CUSTOM_OPTION_PREFIX}Работа с фобиями"]
    result = format_code_list(values, _SAMPLE_OPTIONS)
    assert result == "Семейный психолог / системный терапевт, Работа с фобиями"


def test_format_code_list_never_shows_the_custom_prefix_itself():
    values = [f"{CUSTOM_OPTION_PREFIX}Работа с фобиями"]
    result = format_code_list(values, _SAMPLE_OPTIONS)
    assert CUSTOM_OPTION_PREFIX not in result


def test_format_code_list_drops_an_empty_custom_option():
    # Defensive: a custom entry that somehow ended up as just the prefix
    # with no text must not render as a blank/empty label.
    values = [CUSTOM_OPTION_PREFIX]
    assert format_code_list(values, _SAMPLE_OPTIONS) == "не указано"
