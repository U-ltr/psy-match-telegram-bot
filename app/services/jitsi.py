"""Free, no-signup video meeting links via Jitsi Meet (meet.jit.si).

Replaces the earlier Yandex Telemost integration (app/services/telemost.py,
removed): that required a Yandex 360 for Business OAuth token that never
materialized, so every booking kept meeting_link empty and fell back to
the psychologist adding a link manually. Jitsi Meet needs no API call, no
auth, and no signup - any URL of the form https://meet.jit.si/<room-name>
IS the meeting: visiting it creates the room on first join, for free.

Because anyone who has the exact URL can join a Jitsi room, the room name
is not just the booking id - a short random suffix is appended so a room
can't be guessed or collide with someone else's meeting, while the
booking id prefix still makes it traceable back to the booking in logs.

A manually-set link (the psychologist's own "Добавить/изменить ссылку
встречи") is always authoritative and is never overwritten - see
get_or_create_meeting_link.
"""
import secrets

JITSI_BASE_URL = "https://meet.jit.si"


def generate_jitsi_link(booking_id: int) -> str:
    """A fresh, collision-resistant Jitsi Meet link for one specific
    booking. Pure and synchronous - no network call, so this can never
    fail the way the old Telemost API call could."""
    random_suffix = secrets.token_urlsafe(8).replace("_", "").replace("-", "")
    room_name = f"PsyMatch-{booking_id}-{random_suffix}"
    return f"{JITSI_BASE_URL}/{room_name}"


async def get_or_create_meeting_link(existing_link: str | None, booking_id: int) -> str:
    """The single entry point booking flows should use to obtain a meeting
    link. Never overwrites a link the psychologist already set manually -
    that manual link is always authoritative. Unlike the old Telemost
    integration, this never returns None for lack of configuration: a
    Jitsi link can always be generated, with no external dependency and no
    setup required.
    """
    if existing_link:
        return existing_link

    return generate_jitsi_link(booking_id)
