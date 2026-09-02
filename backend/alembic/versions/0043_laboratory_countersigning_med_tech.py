"""Laboratory Report: countersigning Med Technologist (manual signature).

Client requirement change: laboratory reports carry no Med Tech
e-signature at all going forward - both the Med Tech In Charge and a new
second, MANUALLY-signing "countersigning" MedTech print with a blank
physical-signature line. Only the Pathologist keeps an e-signature.

Purely additive - no existing column's semantics change, and no existing
data is touched:

1. `laboratory_orders.countersigning_med_tech_id` (nullable FK ->
   users.id, ON DELETE SET NULL) - kept for traceability/UI convenience
   only, same convention as the existing `pathologist_id` column (0040) -
   report rendering never re-joins it, only the two snapshot columns
   below.
2. `laboratory_orders.countersigning_med_tech_name_snapshot` (String(255))
   and `countersigning_med_tech_license_snapshot` (String(50)) - captured
   ONCE at `release_results()` time from whichever Laboratory-role User is
   selected as the countersigner, same "snapshot, never re-resolve"
   convention as every other signatory on this table (see 0040's own
   docstring) - a later rename or license change on that user's account
   must never alter an already-released report.

Deliberately NO `countersigning_med_tech_signature_snapshot_url` column -
this person always signs the printed page by hand, so there is nothing to
snapshot for it, and there never will be.

The existing `med_tech_signature_snapshot_url` column (0040) is NOT
touched/dropped here - it stays exactly as-is for historical
compatibility (an order released before this change keeps rendering its
already-captured Med Tech In Charge signature on reprint).
`release_results()` simply stops writing new values into it going
forward (a service-layer change, not a schema change).

Revision ID: 0043_laboratory_countersigning_med_tech
Revises: 0042_laboratory_standalone_order_number
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0043_laboratory_countersigning_med_tech"
down_revision: str | None = "0042_laboratory_standalone_order_number"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "laboratory_orders",
        sa.Column("countersigning_med_tech_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_laboratory_orders_countersigning_med_tech_id", "laboratory_orders", ["countersigning_med_tech_id"])
    op.add_column("laboratory_orders", sa.Column("countersigning_med_tech_name_snapshot", sa.String(length=255), nullable=True))
    op.add_column("laboratory_orders", sa.Column("countersigning_med_tech_license_snapshot", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("laboratory_orders", "countersigning_med_tech_license_snapshot")
    op.drop_column("laboratory_orders", "countersigning_med_tech_name_snapshot")
    op.drop_index("ix_laboratory_orders_countersigning_med_tech_id", table_name="laboratory_orders")
    op.drop_column("laboratory_orders", "countersigning_med_tech_id")
