"""Per-doctor consultation workspace configuration.

Purely additive: adds one nullable column, `doctors.workspace_config`
(JSONB), storing a data-driven show/hide + required-toggle map for
consultation sections (vitals, diagnosis, prescription, lab requests,
medical certificate, attachments) - see `app/models/doctor.py`'s
`resolve_workspace_config()` for the resolution rules.

NULL is the correct default for every existing doctor row - a null value
resolves to "every section visible, none required", i.e. exactly the
consultation page's behavior before this feature existed. No backfill.

Revision ID: 0041_doctor_workspace_config
Revises: 0040_laboratory_signatories
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0041_doctor_workspace_config"
down_revision: str | None = "0040_laboratory_signatories"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("doctors", sa.Column("workspace_config", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("doctors", "workspace_config")
