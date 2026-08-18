"""Laboratory template parameter section/grouping (Phase 4A - Urinalysis).

Purely additive: adds one nullable column,
`laboratory_template_parameters.section` (varchar(100)), used as a generic
display-grouping label (e.g. "Physical Examination", "Chemical
Examination", "Microscopic Examination") for templates whose parameters
naturally fall into sections - not a Urinalysis-specific concept, any
future multi-section template can reuse it.

No existing column is touched. NULL is the correct default for every
existing row (CBC/Blood Typing/any parameter with no natural section) - no
backfill, no data migration.

Revision ID: 0032_lab_template_section
Revises: 0031_lab_structured_results
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_lab_template_section"
down_revision: str | None = "0031_lab_structured_results"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("laboratory_template_parameters", sa.Column("section", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("laboratory_template_parameters", "section")
