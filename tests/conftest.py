"""Shared pytest fixtures.

Sets required settings via environment variables *before* anything under
app/ is imported (app.config.Settings() runs at import time and requires
BOT_TOKEN/DATABASE_URL - importing any app module without these set would
fail immediately, real .env or not). Environment variables take priority
over the .env file in pydantic-settings, so this makes the test suite
hermetic regardless of what's in the developer's real .env - tests never
touch real credentials or a real database.
"""
import os

os.environ.setdefault("BOT_TOKEN", "test-bot-token")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ADMIN_IDS", "111111,222222")
os.environ.setdefault("YOOKASSA_SHOP_ID", "")
os.environ.setdefault("YOOKASSA_SECRET_KEY", "")
os.environ.setdefault("YOOKASSA_RETURN_URL", "")

import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.database import Base

# Import every model so Base.metadata is complete before create_all().
from app.models.user import User  # noqa: F401
from app.models.psychologist import Psychologist  # noqa: F401
from app.models.booking import Booking  # noqa: F401
from app.models.payment import Payment  # noqa: F401
from app.models.working_interval import WorkingInterval  # noqa: F401
from app.models.busy_interval import BusyInterval  # noqa: F401
from app.models.payout import Payout  # noqa: F401


@pytest_asyncio.fixture
async def sqlite_engine():
    """A fresh in-memory SQLite database per test.

    SQLite stands in for the real Postgres database here - good enough to
    exercise ORM/business logic (queries, transactions, commits), but it
    does NOT enforce real row-level locking: SQLAlchemy's SQLite dialect
    accepts `.with_for_update()` without erroring but does not turn it into
    an actual row lock (SQLite's own concurrency model is file/connection
    level, not row level). Tests here can and do verify the *logic* of
    services/bookings.py's overlap detection (including via
    create_booking_from_generated_slot end-to-end). The exact-duplicate
    race is additionally guarded by a real database-level constraint
    (uq_active_booking_slot, migrations/versions/
    0002_active_booking_slot_unique.py) that SQLite enforces exactly like
    PostgreSQL does. The more general partial-overlap race (a different
    start_time whose duration window still overlaps) is NOT something any
    SQLite configuration can validate - see
    tests/test_concurrency_postgres.py, which exercises that guarantee
    against a real PostgreSQL database.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db(sqlite_engine, monkeypatch):
    """Points the service modules exercised by the test suite at the
    isolated in-memory database for this one test.

    Every service module does `from app.database import async_session`,
    which copies a reference into that module's own namespace at import
    time - patching app.database.async_session alone would NOT affect
    modules that already imported it, so each module actually used by a
    DB-backed test is patched individually here.
    """
    session_maker = async_sessionmaker(sqlite_engine, expire_on_commit=False)

    import app.database as database_module
    import app.services.bookings as bookings_module
    import app.services.payouts as payouts_module
    import app.services.selection_15 as selection_15_module
    import app.services.psychologists as psychologists_module
    import app.services.psychologist_profile as psychologist_profile_module
    import app.services.reminders as reminders_module
    import app.services.yookassa_payments as yookassa_payments_module
    import app.handlers.psychologist as psychologist_handlers_module
    import app.scripts.fix_working_interval_durations as fix_durations_script_module

    for module in (
        database_module,
        bookings_module,
        payouts_module,
        selection_15_module,
        psychologists_module,
        psychologist_profile_module,
        reminders_module,
        yookassa_payments_module,
        psychologist_handlers_module,
        fix_durations_script_module,
    ):
        monkeypatch.setattr(module, "async_session", session_maker, raising=False)
        monkeypatch.setattr(module, "engine", sqlite_engine, raising=False)

    return session_maker


@pytest_asyncio.fixture
async def concurrent_sqlite_engine(tmp_path):
    """A real, file-backed SQLite database, used ONLY by tests that
    actually race two sessions against each other concurrently.

    The default sqlite_engine fixture above uses a `:memory:` URL, which
    SQLAlchemy's aiosqlite dialect defaults to StaticPool for - a SINGLE
    shared DBAPI connection for the whole engine (confirmed against
    SQLAlchemy's own source:
    dialects/sqlite/aiosqlite.py's get_pool_class()). That is fine for
    every test that only ever has one session open at a time, but it is
    actively wrong for a genuinely concurrent test: two AsyncSessions
    sharing one physical connection are NOT isolated from each other -
    one session's rollback can undo the other's already-"committed" work,
    because there is really only one transaction on that one connection
    no matter how many ORM Session objects think they each have their
    own. This was found the hard way: the exact-duplicate concurrency
    test below used to intermittently raise
    "sqlalchemy.exc.InvalidRequestError: Could not refresh instance"
    instead of cleanly rejecting the loser, because the loser's rollback
    was reaching into the winner's still-in-flight transaction.

    A file-backed URL (any path that isn't literally ":memory:") makes
    the aiosqlite dialect default to AsyncAdaptedQueuePool instead, so
    each session checkout gets a genuinely separate connection - real
    transaction isolation between the two racing sessions, exactly like
    two separate connections to a real PostgreSQL server. SQLite's own
    whole-database write lock (not row-level, but real) then correctly
    serializes the two INSERTs at the file level: whichever one's INSERT
    statement executes second sees the first one's already-committed row
    and is rejected by uq_active_booking_slot with a clean IntegrityError,
    without touching the winner's own session/transaction at all.

    `tmp_path` is pytest's built-in per-test temporary directory fixture -
    already unique per test and already cleaned up by pytest itself, so
    no manual temp-file bookkeeping is needed here.
    """
    db_path = tmp_path / "concurrency_test.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        connect_args={"timeout": 5},
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def concurrent_db(concurrent_sqlite_engine, monkeypatch):
    """Same wiring as `db`, but backed by concurrent_sqlite_engine's
    real, separately-connectable file database instead of the shared
    single in-memory connection. Only services/bookings.py is patched -
    the tests that use this fixture only exercise
    create_booking_from_generated_slot."""
    session_maker = async_sessionmaker(concurrent_sqlite_engine, expire_on_commit=False)

    import app.services.bookings as bookings_module

    monkeypatch.setattr(bookings_module, "async_session", session_maker, raising=False)
    monkeypatch.setattr(bookings_module, "engine", concurrent_sqlite_engine, raising=False)

    return session_maker


def stub_send_message_safely(monkeypatch, *modules, result=True):
    """Replace send_message_safely with a fake that records every call and
    returns `result`, in each given already-imported module's own
    namespace (each module did `from app.services.telegram_sender import
    send_message_safely`, which copies a reference at import time - so the
    real function must be patched per-module, not just on
    telegram_sender itself). Returns the list calls are appended to, as
    (chat_id, text) tuples.
    """
    calls: list[tuple[int, str]] = []

    async def _fake(chat_id, text, **kwargs):
        calls.append((chat_id, text))
        return result

    for module in modules:
        monkeypatch.setattr(module, "send_message_safely", _fake, raising=False)

    return calls


def stub_async_function(monkeypatch, *modules, attr_name):
    """Generic version of stub_send_message_safely for any other
    async function a module imported by name (e.g. notify_admins,
    notify_admin_booking_expired). Returns the list of (args, kwargs) each
    call was made with."""
    calls: list[tuple[tuple, dict]] = []

    async def _fake(*args, **kwargs):
        calls.append((args, kwargs))

    for module in modules:
        monkeypatch.setattr(module, attr_name, _fake, raising=False)

    return calls


def stub_notify_admins(monkeypatch, *modules):
    """notify_admins(text) - used directly by reminders.py for the
    missing-meeting-link alert."""
    return stub_async_function(monkeypatch, *modules, attr_name="notify_admins")


def stub_notify_admin_booking_expired(monkeypatch, *modules):
    """notify_admin_booking_expired(...) - used by services/bookings.py
    when a reservation's payment hold expires."""
    return stub_async_function(monkeypatch, *modules, attr_name="notify_admin_booking_expired")
