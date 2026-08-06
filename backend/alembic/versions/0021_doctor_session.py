"""Client Acceptance Revisions Round 3, item 14: Doctor Session Control

Adds `doctor_sessions` - a lightweight per-(clinic, doctor, day) "actively
receiving patients" flag/window, mirroring the `shifts` table's "one open
row at a time" pattern (see `0020_shift_management.py`). No totals/summary
figures live on this table by design (see `models/doctor_session.py`
docstring) - it is purely a start/end timestamp gate.

Revision ID: 0021_doctor_session
Revises: 0020_shift_management
Create Date: 2026-07-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0021_doctor_session"
down_revision: Union[str, None] = "0020_shift_management"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "doctor_sessions",
        sa.Column("doctor_id", sa.UUID(), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_by", sa.UUID(), nullable=True),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["started_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clinic_id", "doctor_id", "session_date", name="uq_doctor_session_clinic_doctor_date"),
    )
    op.create_index(op.f("ix_doctor_sessions_doctor_id"), "doctor_sessions", ["doctor_id"], unique=False)
    op.create_index(op.f("ix_doctor_sessions_session_date"), "doctor_sessions", ["session_date"], unique=False)
    op.create_index(op.f("ix_doctor_sessions_clinic_id"), "doctor_sessions", ["clinic_id"], unique=False)
    # At most one *open* (ended_at IS NULL) session per doctor at a time -
    # same partial-unique-index technique as ix_shifts_one_open_per_receptionist.
    op.create_index(
        "ix_doctor_sessions_one_open_per_doctor",
        "doctor_sessions",
        ["doctor_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_doctor_sessions_one_open_per_doctor", table_name="doctor_sessions")
    op.drop_index(op.f("ix_doctor_sessions_clinic_id"), table_name="doctor_sessions")
    op.drop_index(op.f("ix_doctor_sessions_session_date"), table_name="doctor_sessions")
    op.drop_index(op.f("ix_doctor_sessions_doctor_id"), table_name="doctor_sessions")
    op.drop_table("doctor_sessions")
