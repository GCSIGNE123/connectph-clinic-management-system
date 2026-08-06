"""Laboratory Management (Phase 10).

Design decision (documented in full in docs/DATABASE.md): rather than
extending the Phase 9 `orders`/`order_items` tables in place, this phase
adds a new `laboratory_orders` table with a 1:1 `order_id` FK back to the
existing `orders` row. The Phase 9 `Order` (order_category=Laboratory) stays
the doctor-facing "I am requesting this test" record (created via the
existing `/consultations/{id}/orders` endpoint, unchanged); `laboratory_orders`
is the laboratory department's own richer workflow record layered on top of
it (collection/processing/result-entry/release timestamps+actors, an
optional link to a configurable `laboratory_templates` row, and idempotent
billing linkage). This avoids overloading the generic, multi-category
`orders` table with lab-only columns (six lab-specific status values incl.
"Released", collected_at/by, processing_started_at, released_at/by) that
would be meaningless for Radiology/Procedure/Referral/Vaccination/Custom
rows, while still reusing `orders.order_number`/`priority`/`scheduled_date`
so a receptionist/doctor never sees two different numbering schemes for
what is perceptually "the same order". `laboratory_orders.status` is its
own enum (`laboratory_order_status`), distinct from the shared `order_status`
Phase 9 enum, because it needs the extra terminal "Released" state Phase 9
never required.

Adds:
- `laboratory_templates` / `laboratory_template_parameters` - the
  Administrator-configurable "add a new test without code changes" catalog
  (test name/category/specimen type/price/turnaround + per-parameter
  name/unit/normal range).
- `laboratory_orders` - 1:1 with `orders.id`, tracks the lab workflow state
  machine (Requested -> Collected -> Processing -> Completed -> Released,
  or -> Cancelled from any non-terminal state), plus a nullable
  `invoice_item_id` FK used as the idempotency key for the auto-billing
  integration (see `services/laboratory_service.py`).
- `laboratory_results` - one row per result parameter (a CBC order has ~10),
  numeric or text valued, with its own normal range/units/interpretation.
- `laboratory_attachments` - reuses the exact presigned-URL-stub pattern
  from `consultation_attachments` (Phase 8), scoped to a laboratory_order
  instead of a consultation, since lab reports (PDF/scanned/image) are a
  distinct concern from consultation-level attachments.

All new tables get the legacy-migration mixin fields per spec.

Revision ID: 0011_laboratory_management
Revises: 0010_billing_cashier
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_laboratory_management"
down_revision: str | None = "0010_billing_cashier"
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
    # Extend the existing `visit_timeline_event_type` enum (Phase 6/8/9) with
    # this phase's Laboratory events. Must run as standalone statements
    # (autocommit block) - Postgres does not allow a newly added enum value
    # to be used in the same transaction that added it, but since these are
    # only *used* later at request time (not within this migration), a
    # plain ALTER TYPE ... ADD VALUE IF NOT EXISTS is safe here.
    with op.get_context().autocommit_block():
        for value in (
            "LabSpecimenCollected", "LabProcessingStarted", "LabResultsEntered",
            "LabResultsReleased", "LabOrderCancelled",
        ):
            op.execute(f"ALTER TYPE visit_timeline_event_type ADD VALUE IF NOT EXISTS '{value}'")

    # --- laboratory_templates ---
    op.create_table(
        "laboratory_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("test_name", sa.String(length=255), nullable=False),
        sa.Column("test_category", sa.String(length=100), nullable=True),
        sa.Column("specimen_type", sa.String(length=100), nullable=True),
        sa.Column("default_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("turnaround_time_hours", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_laboratory_templates_clinic_id", "laboratory_templates", ["clinic_id"])
    op.create_index("ix_laboratory_templates_legacy_id", "laboratory_templates", ["legacy_id"])
    op.create_index("ix_laboratory_templates_migration_batch_id", "laboratory_templates", ["migration_batch_id"])

    # --- laboratory_template_parameters ---
    op.create_table(
        "laboratory_template_parameters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("laboratory_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parameter_name", sa.String(length=255), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("normal_range", sa.String(length=100), nullable=True),
        sa.Column("result_type", sa.String(length=20), nullable=False, server_default="Numeric"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_laboratory_template_parameters_clinic_id", "laboratory_template_parameters", ["clinic_id"])
    op.create_index("ix_laboratory_template_parameters_template_id", "laboratory_template_parameters", ["template_id"])

    # --- laboratory_orders ---
    bind = op.get_bind()
    laboratory_order_status = postgresql.ENUM(
        "Requested", "Collected", "Processing", "Completed", "Released", "Cancelled",
        name="laboratory_order_status", create_type=False,
    )
    laboratory_order_status.create(bind, checkfirst=True)

    op.create_table(
        "laboratory_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("laboratory_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("test_type", sa.String(length=255), nullable=False),
        sa.Column("status", laboratory_order_status, nullable=False, server_default="Requested"),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("invoice_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoice_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_laboratory_orders_clinic_id", "laboratory_orders", ["clinic_id"])
    op.create_index("ix_laboratory_orders_order_id", "laboratory_orders", ["order_id"])
    op.create_index("ix_laboratory_orders_visit_id", "laboratory_orders", ["visit_id"])
    op.create_index("ix_laboratory_orders_patient_id", "laboratory_orders", ["patient_id"])
    op.create_index("ix_laboratory_orders_status", "laboratory_orders", ["status"])
    op.create_index("ix_laboratory_orders_legacy_id", "laboratory_orders", ["legacy_id"])
    op.create_index("ix_laboratory_orders_migration_batch_id", "laboratory_orders", ["migration_batch_id"])

    # --- laboratory_results ---
    op.create_table(
        "laboratory_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("laboratory_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("laboratory_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parameter_name", sa.String(length=255), nullable=False),
        sa.Column("result_type", sa.String(length=20), nullable=False, server_default="Numeric"),
        sa.Column("numeric_value", sa.Numeric(14, 4), nullable=True),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("normal_range", sa.String(length=100), nullable=True),
        sa.Column("units", sa.String(length=50), nullable=True),
        sa.Column("interpretation", sa.String(length=20), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("entered_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_laboratory_results_clinic_id", "laboratory_results", ["clinic_id"])
    op.create_index("ix_laboratory_results_laboratory_order_id", "laboratory_results", ["laboratory_order_id"])

    # --- laboratory_attachments ---
    laboratory_attachment_type = postgresql.ENUM(
        "PDFReport", "Image", "ScannedResult", name="laboratory_attachment_type", create_type=False,
    )
    laboratory_attachment_type.create(bind, checkfirst=True)

    op.create_table(
        "laboratory_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("laboratory_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("laboratory_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attachment_type", laboratory_attachment_type, nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_url", sa.String(length=500), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_laboratory_attachments_clinic_id", "laboratory_attachments", ["clinic_id"])
    op.create_index("ix_laboratory_attachments_laboratory_order_id", "laboratory_attachments", ["laboratory_order_id"])


def downgrade() -> None:
    op.drop_index("ix_laboratory_attachments_laboratory_order_id", table_name="laboratory_attachments")
    op.drop_index("ix_laboratory_attachments_clinic_id", table_name="laboratory_attachments")
    op.drop_table("laboratory_attachments")
    op.execute("DROP TYPE IF EXISTS laboratory_attachment_type")

    op.drop_index("ix_laboratory_results_laboratory_order_id", table_name="laboratory_results")
    op.drop_index("ix_laboratory_results_clinic_id", table_name="laboratory_results")
    op.drop_table("laboratory_results")

    op.drop_index("ix_laboratory_orders_migration_batch_id", table_name="laboratory_orders")
    op.drop_index("ix_laboratory_orders_legacy_id", table_name="laboratory_orders")
    op.drop_index("ix_laboratory_orders_status", table_name="laboratory_orders")
    op.drop_index("ix_laboratory_orders_patient_id", table_name="laboratory_orders")
    op.drop_index("ix_laboratory_orders_visit_id", table_name="laboratory_orders")
    op.drop_index("ix_laboratory_orders_order_id", table_name="laboratory_orders")
    op.drop_index("ix_laboratory_orders_clinic_id", table_name="laboratory_orders")
    op.drop_table("laboratory_orders")
    op.execute("DROP TYPE IF EXISTS laboratory_order_status")

    op.drop_index("ix_laboratory_template_parameters_template_id", table_name="laboratory_template_parameters")
    op.drop_index("ix_laboratory_template_parameters_clinic_id", table_name="laboratory_template_parameters")
    op.drop_table("laboratory_template_parameters")

    op.drop_index("ix_laboratory_templates_migration_batch_id", table_name="laboratory_templates")
    op.drop_index("ix_laboratory_templates_legacy_id", table_name="laboratory_templates")
    op.drop_index("ix_laboratory_templates_clinic_id", table_name="laboratory_templates")
    op.drop_table("laboratory_templates")
