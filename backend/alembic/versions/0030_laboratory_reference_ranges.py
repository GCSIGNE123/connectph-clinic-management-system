"""Laboratory structured reference ranges (Feature 3).

Adds five additive, nullable columns to support automatic
BELOW/NORMAL/ABOVE (numeric) and NORMAL/ABNORMAL (qualitative) result
interpretation, without touching the existing free-text `normal_range`
columns or any existing data:

- `laboratory_template_parameters.range_low` (Numeric(14,4), nullable)
- `laboratory_template_parameters.range_high` (Numeric(14,4), nullable)
- `laboratory_template_parameters.expected_normal_text` (String(100), nullable)
- `laboratory_results.range_low` (Numeric(14,4), nullable)
- `laboratory_results.range_high` (Numeric(14,4), nullable)

No server_default needed - NULL is the correct/only sensible default for
"no structured range configured yet", which is true for every existing
row. No backfill, no data migration - every existing template/result
keeps working exactly as before; auto-interpretation simply stays
inactive (interpretation remains whatever it already was: manually set,
or null) until an Administrator fills these in via the Template admin UI.

Revision ID: 0030_laboratory_reference_ranges
Revises: 0029_yakap_classification
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_laboratory_reference_ranges"
down_revision: str | None = "0029_yakap_classification"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("laboratory_template_parameters", sa.Column("range_low", sa.Numeric(14, 4), nullable=True))
    op.add_column("laboratory_template_parameters", sa.Column("range_high", sa.Numeric(14, 4), nullable=True))
    op.add_column("laboratory_template_parameters", sa.Column("expected_normal_text", sa.String(100), nullable=True))

    op.add_column("laboratory_results", sa.Column("range_low", sa.Numeric(14, 4), nullable=True))
    op.add_column("laboratory_results", sa.Column("range_high", sa.Numeric(14, 4), nullable=True))


def downgrade() -> None:
    op.drop_column("laboratory_results", "range_high")
    op.drop_column("laboratory_results", "range_low")

    op.drop_column("laboratory_template_parameters", "expected_normal_text")
    op.drop_column("laboratory_template_parameters", "range_high")
    op.drop_column("laboratory_template_parameters", "range_low")
