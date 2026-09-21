"""Add laboratory_orders.order_item_id; drop order_id's uniqueness (BUG fix)

BUG (2026-09): a Doctor's Clinical Order can carry multiple lab
`OrderItem`s in one submission (`OrderCreate.items: list[...]`, already
supported end-to-end by the schema/API), but
`LaboratoryService.create_from_order` only ever read `order.items[0]` -
every item after the first silently never became a `LaboratoryOrder`, so
it never reached the worklist or billing. Fixed in
`app/services/laboratory_service.py` (now fans out to every item), which
requires this schema change: previously `laboratory_orders.order_id` was
UNIQUE (one `LaboratoryOrder` per `Order`, 1:1); now a single `Order` can
legitimately produce several `LaboratoryOrder` rows (one per `OrderItem`),
so `order_id` can no longer be unique on its own. Uniqueness moves to the
new `order_item_id` column instead - each `OrderItem` still produces at
most one `LaboratoryOrder` (idempotency, unchanged in spirit from before,
just scoped one level finer).

Additive and backward-compatible:
- `order_item_id` is nullable. Every existing `laboratory_orders` row
  (created before this column existed, or created via the walk-in
  `create_from_queue_ticket` path which has no `Order`/`OrderItem` at
  all) keeps `order_item_id = NULL` and remains fully valid/readable -
  nothing is backfilled or rewritten here.
- `order_id` itself, its FK, and its existing (non-unique)
  `ix_laboratory_orders_order_id` index are all left exactly as-is; only
  the UNIQUE constraint on it is dropped.
- No data is deleted or modified. No existing `laboratory_orders`,
  `orders`, or `order_items` row is touched.

Revision ID: 0044_laboratory_order_item_fk
Revises: 0043_laboratory_countersigning_med_tech
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0044_laboratory_order_item_fk"
down_revision: str | None = "0043_laboratory_countersigning_med_tech"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Drop the old 1:1 constraint. The plain (non-unique) index and the
    #    FK to orders.id are untouched - only uniqueness goes away.
    op.drop_constraint("laboratory_orders_order_id_key", "laboratory_orders", type_="unique")

    # 2. New nullable FK to the specific OrderItem this LaboratoryOrder was
    #    created from. ON DELETE CASCADE mirrors order_id's own FK above -
    #    an OrderItem is never deleted independently of its parent Order in
    #    this app (OrderItem only ever goes away via Order's own
    #    cascade="all, delete-orphan"), so this only ever fires alongside
    #    the existing order_id cascade.
    op.add_column(
        "laboratory_orders",
        sa.Column("order_item_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "laboratory_orders_order_item_id_fkey", "laboratory_orders", "order_items",
        ["order_item_id"], ["id"], ondelete="CASCADE",
    )
    # 3. A single unique index both enforces "at most one LaboratoryOrder
    #    per OrderItem" and serves as the lookup index for it (Postgres can
    #    use a unique index for both purposes - no separate plain index
    #    needed, unlike order_id's two-object legacy setup above).
    op.create_index(
        "ix_laboratory_orders_order_item_id", "laboratory_orders", ["order_item_id"], unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_laboratory_orders_order_item_id", table_name="laboratory_orders")
    op.drop_constraint("laboratory_orders_order_item_id_fkey", "laboratory_orders", type_="foreignkey")
    op.drop_column("laboratory_orders", "order_item_id")
    # Irreversible if any Order now has more than one LaboratoryOrder (the
    # very thing this migration exists to allow) - restoring the old
    # unique constraint would violate on those rows. Consolidate/delete
    # the extra rows manually before downgrading if that's ever needed.
    op.create_unique_constraint("laboratory_orders_order_id_key", "laboratory_orders", ["order_id"])
