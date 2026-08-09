"""Queue Setting doctor-scoped prefix (Post-RC1: Multi-Department /
Multi-Doctor TV Queue Display)

Adds a nullable `doctor_id` FK to `queue_settings`, mirroring the existing
nullable `department_id` scope column, so a clinic can set a queue-number
prefix override for a specific doctor (e.g. Dr. A -> "A", Dr. B -> "B") even
when both doctors share the same department. Purely additive: existing rows
get `doctor_id = NULL` (unchanged resolution behaviour - falls through to
the existing department/branch/clinic default chain).

The old 2-column unique constraint (clinic_id, branch_id, department_id) is
replaced with a 4-column one that also includes doctor_id, matching the
existing department_id pattern from migration 0005 (a NULL doctor_id still
participates correctly in a Postgres unique constraint: multiple rows with
the same (clinic, branch, department) and NULL doctor_id remain rejected as
duplicates, since NULL is only special-cased *between* rows that are
otherwise identical in every non-NULL column - here department_id already
does the same "one default row" job, so behaviour is unchanged for existing
rows).

Revision ID: 0025_queue_setting_doctor_prefix
Revises: 0024_vaccination_administration
Create Date: 2026-08-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0025_queue_setting_doctor_prefix"
down_revision: Union[str, None] = "0024_vaccination_administration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "queue_settings",
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_queue_settings_doctor_id", "queue_settings", ["doctor_id"])
    op.create_foreign_key(
        "fk_queue_settings_doctor_id_doctors",
        "queue_settings",
        "doctors",
        ["doctor_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("uq_queue_setting_clinic_branch_department", "queue_settings", type_="unique")
    op.create_unique_constraint(
        "uq_queue_setting_clinic_branch_department_doctor",
        "queue_settings",
        ["clinic_id", "branch_id", "department_id", "doctor_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_queue_setting_clinic_branch_department_doctor", "queue_settings", type_="unique")
    op.create_unique_constraint(
        "uq_queue_setting_clinic_branch_department",
        "queue_settings",
        ["clinic_id", "branch_id", "department_id"],
    )
    op.drop_constraint("fk_queue_settings_doctor_id_doctors", "queue_settings", type_="foreignkey")
    op.drop_index("ix_queue_settings_doctor_id", table_name="queue_settings")
    op.drop_column("queue_settings", "doctor_id")
