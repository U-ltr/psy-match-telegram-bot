"""Partial unique index guarding against exact-duplicate active bookings

Defense-in-depth against the exact-duplicate-slot race found during the
concurrency audit: create_booking_from_generated_slot already takes a row
lock on the psychologist (SELECT ... FOR UPDATE) and rechecks overlap
before inserting, which is the correct guard for PostgreSQL - but that
guarantee lives entirely in application code. This migration adds a
database-level backstop so that even a future code path that bypassed the
lock (or a bug in it) cannot physically result in two ACTIVE bookings for
the same psychologist at the same (date, start_time) - the second INSERT
fails with an IntegrityError instead of silently succeeding.

This only catches an EXACT (date, start_time) collision, not a
partial-overlap collision at a different start_time (e.g. a 90-minute
10:00 booking vs. a 30-minute 10:30 one) - PostgreSQL has no immutable-
predicate way to express a time-range overlap in a plain unique index
(that needs a range type + an EXCLUDE ... USING gist constraint, which
requires the btree_gist extension). The general partial-overlap case is
already handled correctly by the row lock, is not something a simple
unique index can help with, and was deliberately not added here as a
speculative schema change - see docs/final_report_2026-09-round3.md for
the reasoning and how the row-lock guarantee is verified instead
(tests/test_concurrency_postgres.py, run against a real PostgreSQL
database since SQLite has no equivalent of FOR UPDATE's block-then-refresh
semantics).

The predicate deliberately does not reference reserved_until - a
PostgreSQL index predicate must be IMMUTABLE and "now()" is not - so it
mirrors ACTIVE_BOOKING_STATUSES/ACTIVE_PAYMENT_STATUSES in
services/bookings.py by status alone. This is safe because
create_booking_from_generated_slot always calls release_expired_bookings()
first, which flips any stale reserved/pending row's status away before any
new insert is attempted, so a merely-stale reservation is never counted as
"active" by the time this constraint is checked.

Dev/seed data only, per project decision - nothing here needs to preserve
production data, and no existing row is expected to violate this
constraint (the application has never allowed two active bookings at the
same exact slot; this migration only makes that already-true invariant
enforced by the database too).

Revision ID: 0002_active_booking_slot_unique
Revises: 0001_initial_schema
Create Date: 2026-09-07

"""
from alembic import op
import sqlalchemy as sa


revision = "0002_active_booking_slot_unique"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


ACTIVE_SLOT_WHERE = (
    "status IN ('reserved', 'confirmed', 'paid') "
    "AND payment_status IN ('pending', 'paid')"
)


def upgrade() -> None:
    op.create_index(
        "uq_active_booking_slot",
        "bookings",
        ["psychologist_id", "date", "start_time"],
        unique=True,
        postgresql_where=sa.text(ACTIVE_SLOT_WHERE),
    )


def downgrade() -> None:
    op.drop_index("uq_active_booking_slot", table_name="bookings")
