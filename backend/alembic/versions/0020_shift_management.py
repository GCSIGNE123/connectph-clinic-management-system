"""Phase 21: Receptionist Shift Management

Adds `shifts` - a per-receptionist cash-accountability session (opening
cash, opened/closed timestamps, actual cash count at close). Summary
figures (cash/non-cash collections, discounts, refunds, expected cash) are
deliberately NOT stored on this table - they are computed at read time from
the existing `payments`/`discounts`/`refunds` tables within the shift's
time window, so there is nothing here to keep in sync.

Revision ID: 0020_shift_management
Revises: 0019_internal_messaging
Create Date: 2026-07-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0020_shift_management"
down_revision: Union[str, None] = "0019_internal_messaging"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    shift_status = postgresql.ENUM("Open", "Closed", name="shift_status", create_type=False)
    shift_status.create(bind, checkfirst=True)

    op.create_table(
        "shifts",
        sa.Column("branch_id", sa.UUID(), nullable=True),
        sa.Column("receptionist_user_id", sa.UUID(), nullable=False),
        sa.Column("opening_cash", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_cash_count", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", shift_status, nullable=False, server_default="Open"),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["receptionist_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_shifts_branch_id"), "shifts", ["branch_id"], unique=False)
    op.create_index(op.f("ix_shifts_receptionist_user_id"), "shifts", ["receptionist_user_id"], unique=False)
    op.create_index(op.f("ix_shifts_clinic_id"), "shifts", ["clinic_id"], unique=False)
    op.create_index(op.f("ix_shifts_status"), "shifts", ["status"], unique=False)
    # Enforces "only one Open shift per receptionist at a time" at the DB
    # level too (the service layer also checks, but a partial unique index
    # closes the race-condition gap between check-and-insert).
    op.create_index(
        "ix_shifts_one_open_per_receptionist",
        "shifts",
        ["receptionist_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'Open'"),
    )


def downgrade() -> None:
    op.drop_index("ix_shifts_one_open_per_receptionist", table_name="shifts")
    op.drop_index(op.f("ix_shifts_status"), table_name="shifts")
    op.drop_index(op.f("ix_shifts_clinic_id"), table_name="shifts")
    op.drop_index(op.f("ix_shifts_receptionist_user_id"), table_name="shifts")
    op.drop_index(op.f("ix_shifts_branch_id"), table_name="shifts")
    op.drop_table("shifts")
    sa.Enum(name="shift_status").drop(op.get_bind(), checkfirst=True)
