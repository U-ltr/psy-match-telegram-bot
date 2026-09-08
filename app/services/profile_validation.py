from app.models.psychologist import Psychologist
from app.services.pricing import get_priced_durations


def is_psychologist_profile_ready(psychologist: Psychologist | dict) -> bool:
    """
    Проверяет, можно ли показывать психолога клиентам.

    Цель: не допустить ситуацию, когда клиент записался к психологу
    с ценой 0, пустым описанием или незаполненной анкетой.
    """

    def get(field, default=None):
        if isinstance(psychologist, dict):
            return psychologist.get(field, default)
        return getattr(psychologist, field, default)

    if not get("is_active", False):
        return False

    if not get("name"):
        return False

    if not get("description"):
        return False

    specializations = get("specializations") or []
    help_topics = get("help_topics") or []
    styles = get("styles") or []

    if not specializations:
        return False

    if not help_topics:
        return False

    if not styles:
        return False

    # at least one duration must have an actual price set - a psychologist
    # is not bookable until they've priced at least one duration
    if not get_priced_durations(psychologist):
        return False

    return True


def get_psychologist_profile_missing_fields(psychologist: Psychologist | dict) -> list[str]:
    def get(field, default=None):
        if isinstance(psychologist, dict):
            return psychologist.get(field, default)
        return getattr(psychologist, field, default)

    missing = []

    if not get("name"):
        missing.append("имя")

    if not get("description"):
        missing.append("описание")

    if not get_priced_durations(psychologist):
        missing.append("длительности и цены консультаций")

    if not (get("specializations") or []):
        missing.append("специализации")

    if not (get("help_topics") or []):
        missing.append("запросы, с которыми психолог помогает")

    if not (get("styles") or []):
        missing.append("стиль работы")

    return missing
