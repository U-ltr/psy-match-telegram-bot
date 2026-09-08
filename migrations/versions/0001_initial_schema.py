"""Initial schema baseline

Hand-written to match app/models/*.py as of this pass (there is no earlier
Alembic history - the project previously relied on Base.metadata.create_all()
plus one hand-rolled ALTER TABLE in app/database.py's init_db(), which this
migration set replaces). Written against dev/seed data only, per project
decision - there is no real production data this needs to preserve.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-07

"""
from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("age_group", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "psychologists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("gender", sa.String(50), nullable=True),
        sa.Column("photo_file_id", sa.String(500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("education", sa.Text(), nullable=True),
        sa.Column("experience_years", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("durations", sa.JSON(), nullable=False),
        sa.Column("specializations", sa.JSON(), nullable=False),
        sa.Column("help_topics", sa.JSON(), nullable=False),
        sa.Column("styles", sa.JSON(), nullable=False),
        sa.Column("therapy_experience_fit", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_psychologists_telegram_id", "psychologists", ["telegram_id"], unique=True)

    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("psychologist_id", sa.Integer(), sa.ForeignKey("psychologists.id"), nullable=False),
        sa.Column("date", sa.String(20), nullable=False),
        sa.Column("start_time", sa.String(10), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="reserved"),
        sa.Column("payment_status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("meeting_link", sa.String(1000), nullable=True),
        sa.Column("client_answers", sa.JSON(), nullable=True),
        sa.Column("client_comment", sa.Text(), nullable=True),
        sa.Column("reserved_until", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("reminder_1h_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reminder_10m_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payment_warning_10m_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("booking_type", sa.String(50), nullable=False, server_default="consultation"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_bookings_user_id", "bookings", ["user_id"])
    op.create_index("ix_bookings_psychologist_id", "bookings", ["psychologist_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("payment_provider", sa.String(100), nullable=False, server_default="yookassa"),
        sa.Column("provider_payment_id", sa.String(255), nullable=True),
        sa.Column("confirmation_url", sa.String(1000), nullable=True),
        sa.Column("email_for_receipt", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_payments_booking_id", "payments", ["booking_id"])
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_provider_payment_id", "payments", ["provider_payment_id"])

    op.create_table(
        "working_intervals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("psychologist_id", sa.Integer(), sa.ForeignKey("psychologists.id"), nullable=False),
        sa.Column("date", sa.String(20), nullable=False),
        sa.Column("start_time", sa.String(10), nullable=False),
        sa.Column("end_time", sa.String(10), nullable=False),
        sa.Column("consultation_duration", sa.Integer(), nullable=False),
        sa.Column("break_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_working_intervals_psychologist_id", "working_intervals", ["psychologist_id"])

    op.create_table(
        "busy_intervals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("psychologist_id", sa.Integer(), sa.ForeignKey("psychologists.id"), nullable=False),
        sa.Column("date", sa.String(20), nullable=False),
        sa.Column("start_time", sa.String(10), nullable=False),
        sa.Column("end_time", sa.String(10), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_busy_intervals_psychologist_id", "busy_intervals", ["psychologist_id"])

    op.create_table(
        "payouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("psychologist_id", sa.Integer(), sa.ForeignKey("psychologists.id"), nullable=False),
        sa.Column("gross_amount", sa.Integer(), nullable=False),
        sa.Column("commission_amount", sa.Integer(), nullable=False),
        sa.Column("psychologist_amount", sa.Integer(), nullable=False),
        sa.Column("commission_percent", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_payouts_booking_id", "payouts", ["booking_id"], unique=True)
    op.create_index("ix_payouts_psychologist_id", "payouts", ["psychologist_id"])


def downgrade() -> None:
    op.drop_table("payouts")
    op.drop_table("busy_intervals")
    op.drop_table("working_intervals")
    op.drop_table("payments")
    op.drop_table("bookings")
    op.drop_table("psychologists")
    op.drop_table("users")
