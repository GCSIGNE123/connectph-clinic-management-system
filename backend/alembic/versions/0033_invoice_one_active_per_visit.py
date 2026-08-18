"""Enforce at most one non-cancelled invoice per visit (Phase 5B, LR2).

Investigation confirmed the business invariant is absolute:
`InvoiceService.create_draft_invoice_for_consultation`'s own docstring
states "returns the existing invoice for this visit if one already
exists (any non-cancelled status)" - i.e. exactly one *active*
(non-Cancelled) invoice per visit is the intended, permanent rule. A
Cancelled invoice does NOT block creating a new one (a legitimate
re-invoice-after-cancellation flow), so this must be a PARTIAL unique
index, not a plain unique constraint on `visit_id` alone.

Until now this invariant was enforced only in application code
(check-then-create in `create_draft_invoice_for_consultation`), a
classic TOCTOU race: two concurrent requests could both pass the
"does an active invoice already exist?" check before either commits,
producing two Draft invoices for one visit. This migration closes that
gap at the database level, using the exact same pattern already
established for `queues` (see `0005_reception_queue.py`'s
`uq_queues_active_patient_department_day` - Postgres partial unique
indexes can't be expressed via a plain `UniqueConstraint`, hence raw
DDL here too).

PRODUCTION SAFETY NOTE (do not skip before running in a real
deployment): if any existing clinic's data already has two or more
non-cancelled invoices for the same visit, this migration's `CREATE
UNIQUE INDEX` will fail. Before applying in production, run:

    SELECT clinic_id, visit_id, COUNT(*)
    FROM invoices
    WHERE is_deleted = false AND status != 'Cancelled'
    GROUP BY clinic_id, visit_id
    HAVING COUNT(*) > 1;

and resolve any duplicates first. This migration was verified against
the disposable local test database only (no production data was ever
inspected or migrated as part of this change).

Revision ID: 0033_invoice_one_active_per_visit
Revises: 0032_lab_template_section
Create Date: 2026-08-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0033_invoice_one_active_per_visit"
down_revision: str | None = "0032_lab_template_section"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX uq_invoices_active_per_visit
        ON invoices (clinic_id, visit_id)
        WHERE is_deleted = false AND status != 'Cancelled'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_invoices_active_per_visit")
