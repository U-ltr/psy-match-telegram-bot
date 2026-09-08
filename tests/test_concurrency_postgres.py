"""Real PostgreSQL concurrency test for the booking row lock.

Why this file exists: services/bookings.py's create_booking_from_generated_slot
guards against double-booking with SELECT ... FOR UPDATE on the psychologist
row, inside one transaction, re-checking overlap before inserting. That is the
textbook-correct pattern for PostgreSQL - a second transaction's FOR UPDATE
blocks until the first commits, then re-reads and sees the first booking. It
CANNOT be validated against SQLite: SQLite has no row-level lock at all, and
`.with_for_update()` compiles to a plain SELECT there (see conftest.py's
sqlite_engine fixture docstring). tests/test_bookings.py's
test_concurrent_booking_attempts_only_one_succeeds now also passes on SQLite,
but only for the EXACT-duplicate-slot case, and only because of the separate
database-level uq_active_booking_slot unique index (migrations/versions/
0002_active_booking_slot_unique.py) - that index does not (and by design,
cannot, on an immutable index predicate) catch a partial overlap at a
DIFFERENT start_time (e.g. a 90-minute 10:00 booking racing a 30-minute 10:30
one). That general case is only protected by the row lock, and this file is
the only place it is actually exercised against real concurrent PostgreSQL
connections.

Opt-in and safe by design:
- Skipped entirely unless RUN_POSTGRES_TESTS=1 is set - the default
  `pytest -v` run never requires a live database.
- Skipped (not failed) if PostgreSQL isn't reachable, so an accidental
  RUN_POSTGRES_TESTS=1 without Docker running doesn't look like a real
  failure.
- Never touches the real "psybot" database. It creates and uses a separate
  "psybot_test" database on the same PostgreSQL server (same host/port/
  credentials as DATABASE_URL, database name swapped), and drops+recreates
  that test database's tables at the start of the run. Nothing here can
  reach "psybot" even by accident - the URL swap happens once, in
  _test_database_url(), and every fixture in this file is built from that
  swapped URL alone.

Run it explicitly, with the project's Postgres container already up:

    docker compose up -d postgres
    RUN_POSTGRES_TESTS=1 pytest tests/test_concurrency_postgres.py -v

It is intentionally not part of the default `pytest` run (see pytest.ini -
no special marker is needed for that: the skip happens in the fixture
itself before any real connection is attempted).
"""
import os

import pytest
import pytest_asyncio

RUN_POSTGRES_TESTS = os.environ.get("RUN_POSTGRES_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not RUN_POSTGRES_TESTS,
    reason=(
        "Opt-in only - set RUN_POSTGRES_TESTS=1 with a real PostgreSQL "
        "container running (docker compose up -d postgres) to exercise the "
        "real row-lock concurrency guarantee. See this file's module "
        "docstring."
    ),
)


def _test_database_url(async_driver_url: str) -> str:
    """Swap the database name in a postgresql+asyncpg URL for "psybot_test",
    keeping host/port/credentials identical. This is the ONLY place the
    test database name is decided - every fixture below is built from this
    function's return value, so there is no path by which this file can
    end up pointed at the real "psybot" database."""
    base, _, _ = async_driver_url.rpartition("/")
    return f"{base}/psybot_test"


def _maintenance_database_url(async_driver_url: str) -> str:
    """The default "postgres" maintenance database on the same server -
    needed once, to run CREATE DATABASE (which cannot run inside the
    transaction SQLAlchemy would otherwise wrap it in)."""
    base, _, _ = async_driver_url.rpartition("/")
    return f"{base}/postgres"


@pytest_asyncio.fixture(scope="module")
async def postgres_engine():
    if not RUN_POSTGRES_TESTS:
        pytest.skip("RUN_POSTGRES_TESTS not set")

    import asyncpg
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.config import settings
    from app.database import Base
    # Import every model so Base.metadata is complete before create_all(),
    # exactly like conftest.py's sqlite_engine fixture.
    from app.models.user import User  # noqa: F401
    from app.models.psychologist import Psychologist  # noqa: F401
    from app.models.booking import Booking  # noqa: F401
    from app.models.payment import Payment  # noqa: F401
    from app.models.working_interval import WorkingInterval  # noqa: F401
    from app.models.busy_interval import BusyInterval  # noqa: F401
    from app.models.payout import Payout  # noqa: F401

    test_url = _test_database_url(settings.database_url)
    maintenance_url = _maintenance_database_url(settings.database_url)

    # asyncpg wants a plain "postgresql://" DSN, not SQLAlchemy's
    # "postgresql+asyncpg://".
    maintenance_dsn = maintenance_url.replace("postgresql+asyncpg://", "postgresql://")
    test_db_name = "psybot_test"

    try:
        admin_conn = await asyncpg.connect(maintenance_dsn, timeout=5)
    except Exception as error:
        pytest.skip(f"PostgreSQL not reachable at {maintenance_dsn}: {error}")
        return

    try:
        exists = await admin_conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", test_db_name
        )
        if not exists:
            # CREATE DATABASE cannot run inside a transaction block -
            # asyncpg's plain .execute() on a fresh connection is not
            # wrapped in one by default, which is what we need here.
            await admin_conn.execute(f'CREATE DATABASE "{test_db_name}"')
    finally:
        await admin_conn.close()

    engine = create_async_engine(test_url)

    async with engine.begin() as conn:
        # Start every run from a clean slate - this database exists only
        # for this test file, so dropping and recreating its tables is
        # always safe and never touches "psybot".
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def pg_db(postgres_engine, monkeypatch):
    """Points services/bookings.py (and the notification stubs it needs) at
    the real, dedicated psybot_test database for one test."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    import app.services.bookings as bookings_module
    from tests.conftest import stub_send_message_safely, stub_notify_admin_booking_expired

    session_maker = async_sessionmaker(postgres_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(bookings_module, "async_session", session_maker, raising=False)

    # No test in this file expects a reservation to have already expired,
    # but stubbing this defensively matches
    # test_create_booking_ignores_reservation_whose_hold_has_passed's fix
    # in test_bookings.py - a real aiogram Bot must never be constructed
    # from a test.
    stub_send_message_safely(monkeypatch, bookings_module)
    stub_notify_admin_booking_expired(monkeypatch, bookings_module)

    return session_maker


async def _make_psychologist(pg_db, durations):
    from app.models.psychologist import Psychologist

    async with pg_db() as session:
        psychologist = Psychologist(
            telegram_id=None,
            name="Postgres Concurrency Test",
            education="",
            durations=durations,
            specializations=[],
            help_topics=[],
            styles=[],
            therapy_experience_fit=[],
            is_active=True,
        )
        session.add(psychologist)
        await session.commit()
        await session.refresh(psychologist)
        return psychologist.id


@pytest.mark.asyncio
async def test_concurrent_overlapping_different_start_times_only_one_succeeds(pg_db):
    """The scenario uq_active_booking_slot structurally cannot catch: two
    different start_time values whose duration windows still overlap
    (90 minutes at 10:00 is 10:00-11:30; 30 minutes at 10:30 is
    10:30-11:00 - these collide even though neither (date, start_time)
    pair matches the other). Only the row lock protects this, and only
    real concurrent PostgreSQL connections can prove it actually does.
    """
    import asyncio
    from app.services.bookings import create_booking_from_generated_slot

    psychologist_id = await _make_psychologist(
        pg_db, [{"minutes": 90, "price": 6000}, {"minutes": 30, "price": 2500}]
    )

    results = await asyncio.gather(
        create_booking_from_generated_slot(
            telegram_id=71001, username="pg_client1", full_name="PG Client One",
            phone=None, email=None, psychologist_id=psychologist_id,
            date="2099-03-01", start_time="10:00", duration=90,
        ),
        create_booking_from_generated_slot(
            telegram_id=71002, username="pg_client2", full_name="PG Client Two",
            phone=None, email=None, psychologist_id=psychologist_id,
            date="2099-03-01", start_time="10:30", duration=30,
        ),
    )

    successes = [r for r in results if r is not None]
    assert len(successes) == 1


@pytest.mark.asyncio
async def test_concurrent_back_to_back_bookings_both_succeed(pg_db):
    """The lock must not over-serialize into a false rejection: two
    genuinely non-overlapping back-to-back bookings (10:00-11:00 and
    11:00-12:00) raced concurrently must both succeed."""
    import asyncio
    from app.services.bookings import create_booking_from_generated_slot

    psychologist_id = await _make_psychologist(pg_db, [{"minutes": 60, "price": 4000}])

    results = await asyncio.gather(
        create_booking_from_generated_slot(
            telegram_id=72001, username="pg_client3", full_name="PG Client Three",
            phone=None, email=None, psychologist_id=psychologist_id,
            date="2099-03-02", start_time="10:00", duration=60,
        ),
        create_booking_from_generated_slot(
            telegram_id=72002, username="pg_client4", full_name="PG Client Four",
            phone=None, email=None, psychologist_id=psychologist_id,
            date="2099-03-02", start_time="11:00", duration=60,
        ),
    )

    successes = [r for r in results if r is not None]
    assert len(successes) == 2


@pytest.mark.asyncio
async def test_concurrent_bookings_for_different_psychologists_both_succeed(pg_db):
    """The row lock is scoped to one psychologist (SELECT ... FOR UPDATE on
    that single row) - two different psychologists booked at the exact
    same time concurrently must not block each other."""
    import asyncio
    from app.services.bookings import create_booking_from_generated_slot

    psychologist_a = await _make_psychologist(pg_db, [{"minutes": 60, "price": 4000}])
    psychologist_b = await _make_psychologist(pg_db, [{"minutes": 60, "price": 4500}])

    results = await asyncio.gather(
        create_booking_from_generated_slot(
            telegram_id=73001, username="pg_client5", full_name="PG Client Five",
            phone=None, email=None, psychologist_id=psychologist_a,
            date="2099-03-03", start_time="10:00", duration=60,
        ),
        create_booking_from_generated_slot(
            telegram_id=73002, username="pg_client6", full_name="PG Client Six",
            phone=None, email=None, psychologist_id=psychologist_b,
            date="2099-03-03", start_time="10:00", duration=60,
        ),
    )

    successes = [r for r in results if r is not None]
    assert len(successes) == 2


@pytest.mark.asyncio
async def test_concurrent_exact_duplicate_only_one_succeeds_on_real_postgres(pg_db):
    """Belt and suspenders: the exact-duplicate case is already covered on
    SQLite via uq_active_booking_slot (tests/test_bookings.py), but
    confirming it here too proves the row lock alone (independent of that
    index) also correctly serializes this simpler case on real
    PostgreSQL."""
    import asyncio
    from app.services.bookings import create_booking_from_generated_slot

    psychologist_id = await _make_psychologist(pg_db, [{"minutes": 60, "price": 4000}])

    results = await asyncio.gather(
        create_booking_from_generated_slot(
            telegram_id=74001, username="pg_client7", full_name="PG Client Seven",
            phone=None, email=None, psychologist_id=psychologist_id,
            date="2099-03-04", start_time="10:00", duration=60,
        ),
        create_booking_from_generated_slot(
            telegram_id=74002, username="pg_client8", full_name="PG Client Eight",
            phone=None, email=None, psychologist_id=psychologist_id,
            date="2099-03-04", start_time="10:00", duration=60,
        ),
    )

    successes = [r for r in results if r is not None]
    assert len(successes) == 1
