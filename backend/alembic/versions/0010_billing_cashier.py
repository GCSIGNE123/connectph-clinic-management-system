"""Billing & Cashier (Phase 9).

Adds:
- `invoices` / `invoice_items` - the core Draft->PendingPayment->
  PartiallyPaid->Paid billing document per Visit, auto-created on
  Consultation completion (see `services/invoice_service.py`).
- `invoice_counters` - concurrency-safe backing counter for
  `InvoiceNumberGenerator` (`INV-YYYYMMDD-000001`), mirrors `visit_counters`.
- `discounts` - invoice-level (not line-level) discounts.
- `payments` - supports split payments as multiple rows per invoice.
- `refunds` - architecture-only per spec (model + migration, no UI/workflow).

Design choice: no `payment_methods` lookup table and no separate `receipts`
table - `payment_method` is a plain enum (closed 5-value list per spec) and
a receipt is a computed/printable projection of an invoice + its payments,
not its own persisted entity (see `schemas/billing.py::ReceiptPayload` and
`InvoiceService`'s receipt generation). Both documented in `docs/DATABASE.md`.

Revision ID: 0010_billing_cashier
Revises: 0009_clinical_orders
Create Date: 2026-07-26

Renumbered from 0009 to 0010: this migration was originally developed
concurrently with, and under the same down_revision (0008) as,
0009_clinical_orders_prescriptions.py. The user's phase numbering placed
Clinical Orders & Prescriptions at Phase 9 and Billing implicitly after it
(Laboratory Management/Phase 10 assumes Billing already exists), so this
migration was relinked to descend from 0009_clinical_orders rather than
0008 directly, keeping the migration chain linear.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_billing_cashier"
down_revision: str | None = "0009_clinical_orders"
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
    bind = op.get_bind()

    invoice_status_enum = postgresql.ENUM(
        "Draft", "PendingPayment", "PartiallyPaid", "Paid", "Cancelled", name="invoice_status", create_type=False,
    )
    invoice_status_enum.create(bind, checkfirst=True)

    invoice_item_type_enum = postgresql.ENUM(
        "ConsultationFee", "FollowUpFee", "MedicalCertificate", "Laboratory", "XRay", "Procedure",
        "Vaccination", "Custom", name="invoice_item_type", create_type=False,
    )
    invoice_item_type_enum.create(bind, checkfirst=True)

    discount_type_enum = postgresql.ENUM(
        "SeniorCitizen", "PWD", "Employee", "Custom", name="discount_type", create_type=False,
    )
    discount_type_enum.create(bind, checkfirst=True)

    discount_calc_enum = postgresql.ENUM(
        "Percentage", "FixedAmount", name="discount_calculation_type", create_type=False,
    )
    discount_calc_enum.create(bind, checkfirst=True)

    payment_method_enum = postgresql.ENUM(
        "Cash", "GCash", "BankTransfer", "CreditCard", "DebitCard", name="payment_method", create_type=False,
    )
    payment_method_enum.create(bind, checkfirst=True)

    payment_status_enum = postgresql.ENUM("Completed", "Voided", name="payment_status", create_type=False)
    payment_status_enum.create(bind, checkfirst=True)

    # --- invoice_counters ---
    op.create_table(
        "invoice_counters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("counter_date", sa.Date(), nullable=False),
        sa.Column("next_number", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("clinic_id", "counter_date", name="uq_invoice_counter_clinic_date"),
    )
    op.create_index("ix_invoice_counters_clinic_id", "invoice_counters", ["clinic_id"])

    # --- invoices ---
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("invoice_number", sa.String(length=30), nullable=False),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visits.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("status", invoice_status_enum, nullable=False, server_default="Draft"),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("discount_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_total", sa.Numeric(12, 2), nullable=True),
        sa.Column("grand_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("amount_paid", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("balance_due", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("clinic_id", "invoice_number", name="uq_invoice_clinic_invoice_number"),
    )
    op.create_index("ix_invoices_clinic_id", "invoices", ["clinic_id"])
    op.create_index("ix_invoices_visit_id", "invoices", ["visit_id"])
    op.create_index("ix_invoices_branch_id", "invoices", ["branch_id"])
    op.create_index("ix_invoices_patient_id", "invoices", ["patient_id"])
    op.create_index("ix_invoices_doctor_id", "invoices", ["doctor_id"])
    op.create_index("ix_invoices_invoice_date", "invoices", ["invoice_date"])
    op.create_index("ix_invoices_status", "invoices", ["status"])
    op.create_index("ix_invoices_legacy_id", "invoices", ["legacy_id"])
    op.create_index("ix_invoices_migration_batch_id", "invoices", ["migration_batch_id"])

    # --- invoice_items ---
    op.create_table(
        "invoice_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("item_type", invoice_item_type_enum, nullable=False, server_default="Custom"),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_invoice_items_clinic_id", "invoice_items", ["clinic_id"])
    op.create_index("ix_invoice_items_invoice_id", "invoice_items", ["invoice_id"])
    op.create_index("ix_invoice_items_legacy_id", "invoice_items", ["legacy_id"])
    op.create_index("ix_invoice_items_migration_batch_id", "invoice_items", ["migration_batch_id"])

    # --- discounts ---
    op.create_table(
        "discounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("discount_type", discount_type_enum, nullable=False),
        sa.Column("calculation_type", discount_calc_enum, nullable=False),
        sa.Column("value", sa.Numeric(12, 2), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_discounts_clinic_id", "discounts", ["clinic_id"])
    op.create_index("ix_discounts_invoice_id", "discounts", ["invoice_id"])
    op.create_index("ix_discounts_legacy_id", "discounts", ["legacy_id"])
    op.create_index("ix_discounts_migration_batch_id", "discounts", ["migration_batch_id"])

    # --- payments ---
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payment_method", payment_method_enum, nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reference_number", sa.String(length=100), nullable=True),
        sa.Column("status", payment_status_enum, nullable=False, server_default="Completed"),
        sa.Column("received_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_payments_clinic_id", "payments", ["clinic_id"])
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_index("ix_payments_legacy_id", "payments", ["legacy_id"])
    op.create_index("ix_payments_migration_batch_id", "payments", ["migration_batch_id"])

    # --- refunds (architecture only) ---
    op.create_table(
        "refunds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="Pending"),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_refunds_clinic_id", "refunds", ["clinic_id"])
    op.create_index("ix_refunds_payment_id", "refunds", ["payment_id"])
    op.create_index("ix_refunds_legacy_id", "refunds", ["legacy_id"])
    op.create_index("ix_refunds_migration_batch_id", "refunds", ["migration_batch_id"])


def downgrade() -> None:
    op.drop_index("ix_refunds_migration_batch_id", table_name="refunds")
    op.drop_index("ix_refunds_legacy_id", table_name="refunds")
    op.drop_index("ix_refunds_payment_id", table_name="refunds")
    op.drop_index("ix_refunds_clinic_id", table_name="refunds")
    op.drop_table("refunds")

    op.drop_index("ix_payments_migration_batch_id", table_name="payments")
    op.drop_index("ix_payments_legacy_id", table_name="payments")
    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_invoice_id", table_name="payments")
    op.drop_index("ix_payments_clinic_id", table_name="payments")
    op.drop_table("payments")

    op.drop_index("ix_discounts_migration_batch_id", table_name="discounts")
    op.drop_index("ix_discounts_legacy_id", table_name="discounts")
    op.drop_index("ix_discounts_invoice_id", table_name="discounts")
    op.drop_index("ix_discounts_clinic_id", table_name="discounts")
    op.drop_table("discounts")

    op.drop_index("ix_invoice_items_migration_batch_id", table_name="invoice_items")
    op.drop_index("ix_invoice_items_legacy_id", table_name="invoice_items")
    op.drop_index("ix_invoice_items_invoice_id", table_name="invoice_items")
    op.drop_index("ix_invoice_items_clinic_id", table_name="invoice_items")
    op.drop_table("invoice_items")

    op.drop_index("ix_invoices_migration_batch_id", table_name="invoices")
    op.drop_index("ix_invoices_legacy_id", table_name="invoices")
    op.drop_index("ix_invoices_status", table_name="invoices")
    op.drop_index("ix_invoices_invoice_date", table_name="invoices")
    op.drop_index("ix_invoices_doctor_id", table_name="invoices")
    op.drop_index("ix_invoices_patient_id", table_name="invoices")
    op.drop_index("ix_invoices_branch_id", table_name="invoices")
    op.drop_index("ix_invoices_visit_id", table_name="invoices")
    op.drop_index("ix_invoices_clinic_id", table_name="invoices")
    op.drop_table("invoices")

    op.drop_index("ix_invoice_counters_clinic_id", table_name="invoice_counters")
    op.drop_table("invoice_counters")

    op.execute("DROP TYPE IF EXISTS payment_status")
    op.execute("DROP TYPE IF EXISTS payment_method")
    op.execute("DROP TYPE IF EXISTS discount_calculation_type")
    op.execute("DROP TYPE IF EXISTS discount_type")
    op.execute("DROP TYPE IF EXISTS invoice_item_type")
    op.execute("DROP TYPE IF EXISTS invoice_status")
