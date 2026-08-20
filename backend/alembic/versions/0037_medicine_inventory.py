"""Medicine Inventory Phase 1: Medicine catalog + MedicineBatch tables.

Greenfield feature - no existing table/column is touched. Two new tables:

- `medicines`: catalog/master-data (generic_name, brand_name, strength,
  dosage_form, unit, reorder_level, is_active), same UUID/timestamp/
  soft-delete/tenant/legacy-migration column shape as every other Phase 4
  master-data catalog table (e.g. `services`, `laboratory_templates`).
- `medicine_batches`: one row per stocked batch/lot of a medicine
  (batch_number, quantity_received, quantity_remaining, expiry_date,
  received_date, supplier, cost_per_unit, status), FK `medicine_id` ->
  `medicines.id` ON DELETE CASCADE, plus its own `clinic_id` (redundant-but-
  enforced tenancy, same pattern as `laboratory_template_parameters`).
  `UNIQUE(clinic_id, medicine_id, batch_number)` matches the task's explicit
  constraint - the same batch number IS allowed to repeat under a different
  medicine.

No stock-movement ledger, no notifications, no scheduled job - out of scope
for this phase (see the Phase 1 implementation report).

Revision ID: 0037_medicine_inventory
Revises: 0036_doctor_signature_snapshots
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037_medicine_inventory"
down_revision: str | None = "0036_doctor_signature_snapshots"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _legacy_columns() -> list[sa.Column]:
    return [
        sa.Column("legacy_id", sa.String(length=64), nullable=True),
        sa.Column("legacy_meta", postgresql.JSONB(), nullable=True),
        sa.Column("legacy_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legacy_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("migration_batch_id", sa.String(length=64), nullable=True),
        sa.Column("migration_source", sa.String(length=100), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "medicines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("generic_name", sa.String(length=255), nullable=False),
        sa.Column("brand_name", sa.String(length=255), nullable=True),
        sa.Column("strength", sa.String(length=50), nullable=True),
        sa.Column("dosage_form", sa.String(length=50), nullable=True),
        sa.Column("unit", sa.String(length=30), nullable=True),
        sa.Column("reorder_level", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_medicines_clinic_id", "medicines", ["clinic_id"])
    op.create_index("ix_medicines_legacy_id", "medicines", ["legacy_id"])
    op.create_index("ix_medicines_migration_batch_id", "medicines", ["migration_batch_id"])

    op.create_table(
        "medicine_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("medicine_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("medicines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_number", sa.String(length=100), nullable=False),
        sa.Column("quantity_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quantity_remaining", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("received_date", sa.Date(), nullable=True),
        sa.Column("supplier", sa.String(length=255), nullable=True),
        sa.Column("cost_per_unit", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="Active"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("clinic_id", "medicine_id", "batch_number", name="uq_medicine_batch_clinic_medicine_number"),
    )
    op.create_index("ix_medicine_batches_clinic_id", "medicine_batches", ["clinic_id"])
    op.create_index("ix_medicine_batches_medicine_id", "medicine_batches", ["medicine_id"])
    op.create_index("ix_medicine_batches_expiry_date", "medicine_batches", ["expiry_date"])
    op.create_index("ix_medicine_batches_legacy_id", "medicine_batches", ["legacy_id"])
    op.create_index("ix_medicine_batches_migration_batch_id", "medicine_batches", ["migration_batch_id"])


def downgrade() -> None:
    op.drop_table("medicine_batches")
    op.drop_table("medicines")
