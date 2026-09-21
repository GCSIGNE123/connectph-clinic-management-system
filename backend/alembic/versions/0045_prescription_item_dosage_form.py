"""Add prescription_items.dosage_form (Task #8 autocomplete support)

Task #8 (Prescription searchable dropdowns/autocomplete) adds a "Form"
field (e.g. Tablet, Capsule, Suspension) to the prescription-item form so a
doctor can capture the dosage form of what they prescribed, sourced from
the existing `Medicine.dosage_form` catalog field when a catalog medicine
is selected. `PrescriptionItem` had no column to hold it.

Additive and backward-compatible, exactly like every other prescription-item
field (`medicine`, `generic_name`, `brand_name`, `strength`, ...): a plain
nullable snapshot column, matching this codebase's established "snapshot,
never re-join" convention for anything a prescription prints - the same
convention `generic_name`/`brand_name`/`strength` already follow. Sized and
named to match `medicines.dosage_form` (VARCHAR(50)).

Every existing `prescription_items` row gets `dosage_form = NULL` and
remains fully valid/readable - nothing is backfilled or rewritten.

Revision ID: 0045_prescription_item_dosage_form
Revises: 0044_laboratory_order_item_fk
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045_prescription_item_dosage_form"
down_revision: str | None = "0044_laboratory_order_item_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("prescription_items", sa.Column("dosage_form", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("prescription_items", "dosage_form")
