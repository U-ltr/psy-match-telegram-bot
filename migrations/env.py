import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.database import Base
from app.config import settings

# Import every model so Base.metadata knows about all tables before
# autogenerate compares it against the real database.
from app.models.user import User  # noqa: F401
from app.models.psychologist import Psychologist  # noqa: F401
from app.models.booking import Booking  # noqa: F401
from app.models.payment import Payment  # noqa: F401
from app.models.working_interval import WorkingInterval  # noqa: F401
from app.models.busy_interval import BusyInterval  # noqa: F401
from app.models.payout import Payout  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# The app's own DATABASE_URL (from .env via app.config.settings) is the one
# and only source of truth for where migrations run - never a second URL
# hardcoded in alembic.ini.
config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
