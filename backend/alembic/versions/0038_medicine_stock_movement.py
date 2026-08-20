"""Medicine Inventory Phase 2: MedicineStockMovement ledger.

Purely additive - no existing table (`medicines`, `medicine_batches`, or
anything earlier) is touched. One new table, `medicine_stock_movements`:
append-only ledger of quantity changes against a `MedicineBatch`
(movement_type, quantity_delta, resulting_quantity, reason, performed_by,
reference_type/reference_id reserved for a future phase's integration).
Same shape as `AuditLog` - `TimestampMixin` only, no soft-delete, since a
ledger row is never edited or deleted after insert.

No data migration/backfill: Phase 1 batches keep their existing
`quantity_received`/`quantity_remaining` values as-is: no synthetic
"opening balance" movement is created for batches that already existed
before this migration (see the Phase 2 report for the rationale - batch
creation intentionally does not synthesize a ledger entry, in this phase or
retroactively).

Revision ID: 0038_medicine_stock_movement
Revises: 0037_medicine_inventory
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0038_medicine_stock_movement"
down_revision: str | None = "0037_medicine_inventory"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "medicine_stock_movements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("medicine_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("movement_type", sa.String(length=20), nullable=False),
        sa.Column("quantity_delta", sa.Integer(), nullable=False),
        sa.Column("resulting_quantity", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("performed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reference_type", sa.String(length=100), nullable=True),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_medicine_stock_movements_clinic_id", "medicine_stock_movements", ["clinic_id"])
    op.create_index("ix_medicine_stock_movements_batch_id", "medicine_stock_movements", ["batch_id"])
    op.create_index("ix_medicine_stock_movements_performed_by", "medicine_stock_movements", ["performed_by"])


def downgrade() -> None:
    op.drop_table("medicine_stock_movements")
