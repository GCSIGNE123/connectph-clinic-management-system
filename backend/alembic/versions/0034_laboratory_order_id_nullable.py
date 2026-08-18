"""Allow laboratory_orders.order_id to be null (walk-in lab queue tickets)

A LaboratoryOrder previously always required a Phase 9 `orders` row - the
only creation path was a Doctor placing a Laboratory-category order during
a consultation. A Reception queue ticket created directly for the
Laboratory department (walk-in, no doctor/consultation) had no way to
produce an actual lab order the Laboratory role could see, even though the
queue-print vitals-exemption logic already anticipated "a walk-in lab
order has no consultation/SOAP note" as a real scenario. This makes
`order_id` nullable so `LaboratoryService.create_from_queue_ticket` can
create a LaboratoryOrder with no linked Order at all, matching the queue
ticket's selected service against an active template by name - the same
best-effort name-match `create_from_order` already uses for a doctor's
free-text order item.

Revision ID: 0034_laboratory_order_id_nullable
Revises: 0033_invoice_one_active_per_visit
Create Date: 2026-08-18
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034_laboratory_order_id_nullable"
down_revision: str | None = "0033_invoice_one_active_per_visit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Alembic's own `alembic_version.version_num` column defaults to
    # VARCHAR(32) - this project's revision ids are the descriptive
    # filename stem (e.g. "0033_invoice_one_active_per_visit", 34 chars),
    # already longer than that default in a prior migration. Never caught
    # by tests since the test database bootstraps its schema via
    # `Base.metadata.create_all` (see `app/tests/conftest.py`), bypassing
    # Alembic - and therefore this column - entirely. Widened here,
    # unconditionally, so this migration and every one after it can
    # actually apply on any real database still using the default width.
    op.alter_column("alembic_version", "version_num", type_=postgresql.VARCHAR(255))

    op.alter_column(
        "laboratory_orders", "order_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True,
    )


def downgrade() -> None:
    # Irreversible if any walk-in (order_id IS NULL) laboratory orders exist
    # by the time this runs - those rows would violate the NOT NULL being
    # restored. Delete or backfill them manually before downgrading.
    op.alter_column(
        "laboratory_orders", "order_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False,
    )
