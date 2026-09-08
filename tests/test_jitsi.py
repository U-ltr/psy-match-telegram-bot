"""app/services/jitsi.py - the free meet.jit.si replacement for the earlier
Yandex Telemost integration (removed; see git history and README.md's
"Ссылки на видеовстречу"). Telemost depended on a Yandex 360 for Business
OAuth token that never materialized in practice, so meeting_link stayed
empty on essentially every booking. Jitsi needs no API call, no auth, and
no signup - a URL of the form https://meet.jit.si/<room-name> IS the
meeting - so it can always produce a link and can never fail the way a
real API call could.
"""
import pytest

from app.services.jitsi import generate_jitsi_link, get_or_create_meeting_link, JITSI_BASE_URL


def test_generate_jitsi_link_points_at_meet_jit_si():
    link = generate_jitsi_link(booking_id=42)
    assert link.startswith(f"{JITSI_BASE_URL}/")


def test_generate_jitsi_link_is_traceable_to_the_booking():
    link = generate_jitsi_link(booking_id=42)
    assert "42" in link


def test_generate_jitsi_link_is_not_guessable_or_collision_prone():
    """Anyone with the exact URL can join a Jitsi room, so two links for
    the same booking id must never be identical - otherwise a stale link
    someone saw once (support chat, logs) would still work forever."""
    first = generate_jitsi_link(booking_id=42)
    second = generate_jitsi_link(booking_id=42)
    assert first != second


@pytest.mark.asyncio
async def test_never_overwrites_an_existing_manual_link():
    """The psychologist's own manually-added link is always authoritative."""
    existing = "https://t.me/some_psychologist_channel"
    link = await get_or_create_meeting_link(existing, booking_id=1)
    assert link == existing


@pytest.mark.asyncio
async def test_generates_a_link_when_none_exists_yet():
    link = await get_or_create_meeting_link(None, booking_id=7)
    assert link.startswith(f"{JITSI_BASE_URL}/")
    assert "7" in link


@pytest.mark.asyncio
async def test_get_or_create_never_returns_none():
    """Unlike the old Telemost integration (which returned None whenever
    unconfigured or the API call failed), this must always produce a
    usable link - there is no configuration to be missing."""
    link = await get_or_create_meeting_link(None, booking_id=99)
    assert link
