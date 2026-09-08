from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,
    echo=False,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def check_db_connection() -> None:
    """Fails fast on startup if the database is unreachable or the schema
    hasn't been migrated yet, instead of the bot silently crashing on the
    first query a user triggers.

    Schema creation/changes are Alembic's job now (see migrations/ and
    README.md - "alembic upgrade head" is a required deployment step,
    run before starting the bot). This used to call
    Base.metadata.create_all() plus a hand-rolled ALTER TABLE on every
    startup; that's gone because a real migration history replaces it -
    create_all() doesn't version anything and can't express a column
    rename/drop, which is exactly what this pass needed (e.g. dropping
    the flat price column, adding payouts).
    """
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
        result = await conn.execute(
            text(
                "SELECT to_regclass('public.bookings'), "
                "to_regclass('public.payouts')"
            )
        )
        bookings_table, payouts_table = result.first()

        if not bookings_table or not payouts_table:
            raise RuntimeError(
                "Database schema is missing expected tables (bookings/payouts). "
                "Run migrations first: alembic upgrade head"
            )
