"""Phase 16: Production Hardening - additive indexes only

Evidence-based additions from a real Step-1 analysis session (EXPLAIN ANALYZE
against the live dev database, `connectph_clinic`, plus a grep of every FK
column across `app/models/*.py` cross-referenced against each repository's
actual filter predicates):

- `laboratory_orders.branch_id` and `.doctor_id` had no index at all (every
  other FK column on this table did) - `LaboratoryRepository` filters by
  branch and doctor on the visit/patient laboratory-history endpoints.
- `invoices` had single-column indexes on `clinic_id` and `status`
  separately (`ix_invoices_clinic_id`, `ix_invoices_status`) but
  `InvoiceRepository.list_invoices` always filters `clinic_id` AND
  optionally `status`/`invoice_date` together (`app/repositories/
  invoice_repository.py` lines ~113-126) - a composite index lets Postgres
  satisfy the tenant+status / tenant+date filter with a single index scan
  instead of an index scan on one column plus a row-by-row filter on the
  other. Confirmed live: `EXPLAIN ANALYZE` on
  `SELECT * FROM invoices WHERE clinic_id = :c AND status = 'PendingPayment'
  ORDER BY invoice_date DESC LIMIT 20` used `Index Scan using
  ix_invoices_status` then applied `clinic_id` as a row filter - a composite
  `(clinic_id, status)` index removes that extra filter step.

Honest scope note: the real dev database has ~20 rows in `visits`/`queues`,
2 in `invoices`, 0-11 in `laboratory_orders` - too small for the query
planner to prefer an index scan over a sequential scan regardless of which
indexes exist (confirmed live - `visits`/`queues` list queries both chose
`Seq Scan` even with existing indexes available, correctly, since a seq
scan on 20 rows is cheaper). These indexes are added because they are
correct for a production-scale dataset and cost is negligible on a table
this size, not because a measurable speedup was observed on this demo
dataset - see `docs/DATABASE.md`'s Phase 16 section for the full writeup.

Revision ID: 0016_hardening_indexes
Revises: 0015_saas_administration
Create Date: 2026-07-27

Note: the revision id is shortened to `0016_hardening_indexes` (22 chars),
not the full descriptive filename - `alembic_version.version_num` is
`VARCHAR(32)` and the full filename-derived id (`0016_production_
hardening_indexes`, 34 chars) overflows it, reproducing the exact issue
documented in Phase 9's migration-slot note in `docs/TESTING.md`. Only the
filename stays descriptive.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0016_hardening_indexes"
down_revision: Union[str, None] = "0015_saas_administration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # laboratory_orders: branch_id/doctor_id were missing an index entirely
    # (every sibling FK column on this table already had one).
    op.create_index(
        "ix_laboratory_orders_branch_id", "laboratory_orders", ["branch_id"], unique=False
    )
    op.create_index(
        "ix_laboratory_orders_doctor_id", "laboratory_orders", ["doctor_id"], unique=False
    )
    # Composite (clinic_id, status) - laboratory worklist screens filter by
    # clinic + status together (e.g. "all Requested orders for this clinic").
    op.create_index(
        "ix_laboratory_orders_clinic_status", "laboratory_orders", ["clinic_id", "status"], unique=False
    )

    # invoices: list endpoint always filters clinic_id + optional status,
    # and separately clinic_id + date range, together - composite indexes
    # let Postgres satisfy both predicates in a single index scan at scale.
    op.create_index(
        "ix_invoices_clinic_status", "invoices", ["clinic_id", "status"], unique=False
    )
    op.create_index(
        "ix_invoices_clinic_invoice_date", "invoices", ["clinic_id", "invoice_date"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_invoices_clinic_invoice_date", table_name="invoices")
    op.drop_index("ix_invoices_clinic_status", table_name="invoices")
    op.drop_index("ix_laboratory_orders_clinic_status", table_name="laboratory_orders")
    op.drop_index("ix_laboratory_orders_doctor_id", table_name="laboratory_orders")
    op.drop_index("ix_laboratory_orders_branch_id", table_name="laboratory_orders")
