"""Clinical Orders & Prescriptions (Phase 9).

NOTE on migration-slot numbering: this file was created concurrently with
another in-progress phase that had already claimed `0009_billing_cashier.py`
as its migration slot. Per explicit coordination instructions, this
migration (Clinical Orders & Prescriptions) takes priority as "Phase 9" and
claims the `0009` slot with `down_revision = 0008_clinical_consultation`;
the billing migration is expected to be renumbered to `0010_billing_cashier`
descending from this one. Until that rename happens there will briefly be
two files both claiming to descend from 0008 (multiple heads) - this is
intentional/temporary per the coordination plan.

Adds:
- `orders` / `order_items` - Laboratory/Radiology/Vaccination/Custom orders
  created during an in-progress consultation. Shared `order_status` enum
  across categories (accepted simplification - "Collected" reads oddly for
  e.g. a Referral, but a future processing phase can build on one uniform
  status shape). `order_items` uses a few nullable typed columns
  (exam_type/body_part/clinical_indication) for Imaging-specific fields
  rather than a JSON blob, since the spec names those fields explicitly.
- `procedures` - its own lightweight table (NOT rows in `orders`), matching
  the spec's standalone "PROCEDURE ORDERS" field list (no Order Number).
- `referrals` - its own table too, matching the spec's DATABASE section
  listing "Referral" as a top-level table name.
- `prescriptions` / `prescription_items` - prescription header + unlimited
  line items. `prescription_status` is Draft/Finalized/Cancelled (spec did
  not enumerate values, this is a sensible minimal set).
- New `visit_timeline_event_type` enum values for order/procedure/referral/
  prescription creation events (same visit-scoped timeline reuse as Phase 8).

All new tables carry the legacy-migration mixin columns for future bulk
import compatibility, per project convention.

Revision ID: 0009_clinical_orders_prescriptions
Revises: 0008_clinical_consultation
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_clinical_orders"
down_revision: str | None = "0008_clinical_consultation"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


LEGACY_COLUMNS = [
    sa.Column("legacy_id", sa.String(length=64), nullable=True),
    sa.Column("legacy_meta", postgresql.JSONB(), nullable=True),
    sa.Column("legacy_created_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("legacy_updated_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("migration_batch_id", sa.String(length=64), nullable=True),
    sa.Column("migration_source", sa.String(length=100), nullable=True),
    sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
]


def _legacy_columns():
    # Return fresh Column objects each call - SQLAlchemy Column instances
    # cannot be reused across multiple Table definitions.
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
    bind = op.get_bind()

    for value in ("OrderCreated", "ProcedureCreated", "ReferralCreated", "PrescriptionCreated"):
        op.execute(f"ALTER TYPE visit_timeline_event_type ADD VALUE IF NOT EXISTS '{value}'")

    order_category_enum = postgresql.ENUM(
        "Laboratory", "Radiology", "Procedure", "Referral", "Vaccination", "Custom",
        name="order_category", create_type=False,
    )
    order_category_enum.create(bind, checkfirst=True)

    order_priority_enum = postgresql.ENUM("Routine", "STAT", name="order_priority", create_type=False)
    order_priority_enum.create(bind, checkfirst=True)

    order_status_enum = postgresql.ENUM(
        "Requested", "Collected", "Processing", "Completed", "Cancelled",
        name="order_status", create_type=False,
    )
    order_status_enum.create(bind, checkfirst=True)

    prescription_status_enum = postgresql.ENUM(
        "Draft", "Finalized", "Cancelled", name="prescription_status", create_type=False,
    )
    prescription_status_enum.create(bind, checkfirst=True)

    # --- orders ---
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("consultation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("order_number", sa.String(length=40), nullable=False),
        sa.Column("order_category", order_category_enum, nullable=False),
        sa.Column("priority", order_priority_enum, nullable=False, server_default="Routine"),
        sa.Column("scheduled_date", sa.Date(), nullable=True),
        sa.Column("clinical_notes", sa.Text(), nullable=True),
        sa.Column("status", order_status_enum, nullable=False, server_default="Requested"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_orders_clinic_id", "orders", ["clinic_id"])
    op.create_index("ix_orders_consultation_id", "orders", ["consultation_id"])
    op.create_index("ix_orders_visit_id", "orders", ["visit_id"])
    op.create_index("ix_orders_branch_id", "orders", ["branch_id"])
    op.create_index("ix_orders_patient_id", "orders", ["patient_id"])
    op.create_index("ix_orders_doctor_id", "orders", ["doctor_id"])
    op.create_index("ix_orders_order_number", "orders", ["order_number"])
    op.create_index("ix_orders_legacy_id", "orders", ["legacy_id"])
    op.create_index("ix_orders_migration_batch_id", "orders", ["migration_batch_id"])
    op.create_unique_constraint("uq_orders_clinic_order_number", "orders", ["clinic_id", "order_number"])

    # --- order_items ---
    op.create_table(
        "order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_name", sa.String(length=255), nullable=False),
        sa.Column("item_category", sa.String(length=100), nullable=True),
        sa.Column("exam_type", sa.String(length=255), nullable=True),
        sa.Column("body_part", sa.String(length=255), nullable=True),
        sa.Column("clinical_indication", sa.Text(), nullable=True),
    )
    op.create_index("ix_order_items_clinic_id", "order_items", ["clinic_id"])
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index("ix_order_items_legacy_id", "order_items", ["legacy_id"])
    op.create_index("ix_order_items_migration_batch_id", "order_items", ["migration_batch_id"])

    # --- procedures ---
    op.create_table(
        "procedures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("consultation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("procedure_name", sa.String(length=255), nullable=False),
        sa.Column("procedure_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", order_status_enum, nullable=False, server_default="Requested"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_procedures_clinic_id", "procedures", ["clinic_id"])
    op.create_index("ix_procedures_consultation_id", "procedures", ["consultation_id"])
    op.create_index("ix_procedures_visit_id", "procedures", ["visit_id"])
    op.create_index("ix_procedures_branch_id", "procedures", ["branch_id"])
    op.create_index("ix_procedures_patient_id", "procedures", ["patient_id"])
    op.create_index("ix_procedures_legacy_id", "procedures", ["legacy_id"])
    op.create_index("ix_procedures_migration_batch_id", "procedures", ["migration_batch_id"])

    # --- referrals ---
    op.create_table(
        "referrals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("consultation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("referred_to", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", order_status_enum, nullable=False, server_default="Requested"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_referrals_clinic_id", "referrals", ["clinic_id"])
    op.create_index("ix_referrals_consultation_id", "referrals", ["consultation_id"])
    op.create_index("ix_referrals_visit_id", "referrals", ["visit_id"])
    op.create_index("ix_referrals_branch_id", "referrals", ["branch_id"])
    op.create_index("ix_referrals_patient_id", "referrals", ["patient_id"])
    op.create_index("ix_referrals_legacy_id", "referrals", ["legacy_id"])
    op.create_index("ix_referrals_migration_batch_id", "referrals", ["migration_batch_id"])

    # --- prescriptions ---
    op.create_table(
        "prescriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("consultation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("prescription_number", sa.String(length=40), nullable=False),
        sa.Column("status", prescription_status_enum, nullable=False, server_default="Draft"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_prescriptions_clinic_id", "prescriptions", ["clinic_id"])
    op.create_index("ix_prescriptions_consultation_id", "prescriptions", ["consultation_id"])
    op.create_index("ix_prescriptions_visit_id", "prescriptions", ["visit_id"])
    op.create_index("ix_prescriptions_branch_id", "prescriptions", ["branch_id"])
    op.create_index("ix_prescriptions_patient_id", "prescriptions", ["patient_id"])
    op.create_index("ix_prescriptions_doctor_id", "prescriptions", ["doctor_id"])
    op.create_index("ix_prescriptions_prescription_number", "prescriptions", ["prescription_number"])
    op.create_index("ix_prescriptions_legacy_id", "prescriptions", ["legacy_id"])
    op.create_index("ix_prescriptions_migration_batch_id", "prescriptions", ["migration_batch_id"])
    op.create_unique_constraint("uq_prescriptions_clinic_prescription_number", "prescriptions", ["clinic_id", "prescription_number"])

    # --- prescription_items ---
    op.create_table(
        "prescription_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("prescription_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("medicine", sa.String(length=255), nullable=False),
        sa.Column("generic_name", sa.String(length=255), nullable=True),
        sa.Column("brand_name", sa.String(length=255), nullable=True),
        sa.Column("strength", sa.String(length=100), nullable=True),
        sa.Column("dosage", sa.String(length=100), nullable=True),
        sa.Column("frequency", sa.String(length=100), nullable=True),
        sa.Column("duration", sa.String(length=100), nullable=True),
        sa.Column("quantity", sa.String(length=50), nullable=True),
        sa.Column("route", sa.String(length=50), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("substitution_allowed", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_prescription_items_clinic_id", "prescription_items", ["clinic_id"])
    op.create_index("ix_prescription_items_prescription_id", "prescription_items", ["prescription_id"])
    op.create_index("ix_prescription_items_legacy_id", "prescription_items", ["legacy_id"])
    op.create_index("ix_prescription_items_migration_batch_id", "prescription_items", ["migration_batch_id"])


def downgrade() -> None:
    op.drop_index("ix_prescription_items_migration_batch_id", table_name="prescription_items")
    op.drop_index("ix_prescription_items_legacy_id", table_name="prescription_items")
    op.drop_index("ix_prescription_items_prescription_id", table_name="prescription_items")
    op.drop_index("ix_prescription_items_clinic_id", table_name="prescription_items")
    op.drop_table("prescription_items")

    op.drop_constraint("uq_prescriptions_clinic_prescription_number", "prescriptions", type_="unique")
    op.drop_index("ix_prescriptions_migration_batch_id", table_name="prescriptions")
    op.drop_index("ix_prescriptions_legacy_id", table_name="prescriptions")
    op.drop_index("ix_prescriptions_prescription_number", table_name="prescriptions")
    op.drop_index("ix_prescriptions_doctor_id", table_name="prescriptions")
    op.drop_index("ix_prescriptions_patient_id", table_name="prescriptions")
    op.drop_index("ix_prescriptions_branch_id", table_name="prescriptions")
    op.drop_index("ix_prescriptions_visit_id", table_name="prescriptions")
    op.drop_index("ix_prescriptions_consultation_id", table_name="prescriptions")
    op.drop_index("ix_prescriptions_clinic_id", table_name="prescriptions")
    op.drop_table("prescriptions")

    op.drop_index("ix_referrals_migration_batch_id", table_name="referrals")
    op.drop_index("ix_referrals_legacy_id", table_name="referrals")
    op.drop_index("ix_referrals_patient_id", table_name="referrals")
    op.drop_index("ix_referrals_branch_id", table_name="referrals")
    op.drop_index("ix_referrals_visit_id", table_name="referrals")
    op.drop_index("ix_referrals_consultation_id", table_name="referrals")
    op.drop_index("ix_referrals_clinic_id", table_name="referrals")
    op.drop_table("referrals")

    op.drop_index("ix_procedures_migration_batch_id", table_name="procedures")
    op.drop_index("ix_procedures_legacy_id", table_name="procedures")
    op.drop_index("ix_procedures_patient_id", table_name="procedures")
    op.drop_index("ix_procedures_branch_id", table_name="procedures")
    op.drop_index("ix_procedures_visit_id", table_name="procedures")
    op.drop_index("ix_procedures_consultation_id", table_name="procedures")
    op.drop_index("ix_procedures_clinic_id", table_name="procedures")
    op.drop_table("procedures")

    op.drop_index("ix_order_items_migration_batch_id", table_name="order_items")
    op.drop_index("ix_order_items_legacy_id", table_name="order_items")
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_index("ix_order_items_clinic_id", table_name="order_items")
    op.drop_table("order_items")

    op.drop_constraint("uq_orders_clinic_order_number", "orders", type_="unique")
    op.drop_index("ix_orders_migration_batch_id", table_name="orders")
    op.drop_index("ix_orders_legacy_id", table_name="orders")
    op.drop_index("ix_orders_order_number", table_name="orders")
    op.drop_index("ix_orders_doctor_id", table_name="orders")
    op.drop_index("ix_orders_patient_id", table_name="orders")
    op.drop_index("ix_orders_branch_id", table_name="orders")
    op.drop_index("ix_orders_visit_id", table_name="orders")
    op.drop_index("ix_orders_consultation_id", table_name="orders")
    op.drop_index("ix_orders_clinic_id", table_name="orders")
    op.drop_table("orders")

    # Note: enum types (order_category/order_priority/order_status/
    # prescription_status) and added visit_timeline_event_type values are
    # intentionally not dropped on downgrade, consistent with 0008's
    # handling of its own enum additions.
