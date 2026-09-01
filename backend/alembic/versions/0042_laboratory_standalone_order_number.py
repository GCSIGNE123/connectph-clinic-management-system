"""Laboratory Report: real Order No. for walk-in (no-doctor) lab orders.

Purely additive: adds one nullable column,
`laboratory_orders.standalone_order_number` (String(40)).

A doctor-referred lab order (created via `LaboratoryService.create_from_
order`) already has a Phase 9 `Order` row to read `order_number` from
(via `order_id`) - unaffected by this migration. A walk-in lab order
(`LaboratoryService.create_from_queue_ticket` - a Reception queue ticket
created directly for Laboratory, no doctor/consultation) has no `Order`
row at all, so its Laboratory Report always printed "Order No. : -".

This column gives that path its own number, generated once at creation
via the same `OrderNumberGenerator` (`ORD-YYYYMMDD-NNNNNN`, one shared
daily counter across both origins) Phase 9 orders already use - see
`LaboratoryService._to_read`'s fallback and `create_from_queue_ticket`.

NULL is correct for every existing doctor-referred row (it uses
`order_id` instead) and is backfilled for existing walk-in rows by a
one-off data script (not part of this migration - see the implementation
report), not a schema-level default.

Revision ID: 0042_laboratory_standalone_order_number
Revises: 0041_doctor_workspace_config
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042_laboratory_standalone_order_number"
down_revision: str | None = "0041_doctor_workspace_config"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("laboratory_orders", sa.Column("standalone_order_number", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("laboratory_orders", "standalone_order_number")
