"""Vitals-before-Queue (Consultation/Follow-up pre-queue draft visits)

Adds the `DraftVitals` value to `visit_status` (a Visit created by Reception
before a Queue ticket exists, so vitals can be captured first - see
`models/visit.py::VisitStatus` docstring), two additive optional vitals
columns on `soap_notes` (`pain_score`, `head_circumference_cm`), and a
per-clinic `require_head_circumference` boolean toggle on `clinics`.

Purely additive - no existing column/enum value is renamed or removed, and
all new columns are nullable / have server defaults, so every previously
queued Visit/Consultation/SoapNote row is unaffected.

Revision ID: 0022_pre_queue_vitals
Revises: 0021_doctor_session
Create Date: 2026-07-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0022_pre_queue_vitals"
down_revision: Union[str, None] = "0021_doctor_session"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New enum value - must run outside the migration's normal transaction
    # block (Postgres cannot use a new enum value in the same transaction
    # that added it), mirroring the established pattern in this project (see
    # 0011_laboratory_management.py / 0012_appointment_management.py).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE visit_status ADD VALUE IF NOT EXISTS 'DraftVitals'")

    op.add_column("soap_notes", sa.Column("pain_score", sa.Integer(), nullable=True))
    op.add_column("soap_notes", sa.Column("head_circumference_cm", sa.Float(), nullable=True))

    op.add_column(
        "clinics",
        sa.Column(
            "require_head_circumference",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("clinics", "require_head_circumference")
    op.drop_column("soap_notes", "head_circumference_cm")
    op.drop_column("soap_notes", "pain_score")
    # Postgres does not support removing an enum value - the 'DraftVitals'
    # value on `visit_status` is left in place on downgrade (harmless, same
    # approach as the other additive-enum migrations in this project).
