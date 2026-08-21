"""Medicine Inventory Phase 3: Expiry Alerts & Notifications.

Purely additive - no existing table/column/migration (0032a-0038) is
touched. Adds:

- Four clinic-configurable warning-day threshold columns on `clinics`
  (`medicine_expiry_warning_days_tier1..4`, defaults 90/60/30/7 - existing
  clinics get sensible defaults with no data backfill needed), same
  named-column-on-Clinic pattern as `require_head_circumference`.
- `medicine_batches.last_alerted_expiry_tier` (Integer, default 0) - the
  Phase 3 dedup state, see `models/medicine.py`'s `EXPIRY_TIER_*` docstring.
- `notifications`: role-targeted system alerts (NOT a reuse of
  `internal_messages`).
- `notification_recipients`: per-user read receipts (presence = read),
  unique on (notification_id, user_id).

Revision ID: 0039_medicine_expiry_notify
Revises: 0038_medicine_stock_movement
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0039_medicine_expiry_notify"
down_revision: str | None = "0038_medicine_stock_movement"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clinics", sa.Column("medicine_expiry_warning_days_tier1", sa.Integer(), nullable=False, server_default="90"))
    op.add_column("clinics", sa.Column("medicine_expiry_warning_days_tier2", sa.Integer(), nullable=False, server_default="60"))
    op.add_column("clinics", sa.Column("medicine_expiry_warning_days_tier3", sa.Integer(), nullable=False, server_default="30"))
    op.add_column("clinics", sa.Column("medicine_expiry_warning_days_tier4", sa.Integer(), nullable=False, server_default="7"))

    op.add_column("medicine_batches", sa.Column("last_alerted_expiry_tier", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("target_role", sa.String(length=50), nullable=True),
        sa.Column("recipient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("entity_type", sa.String(length=50), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notifications_clinic_id", "notifications", ["clinic_id"])
    op.create_index("ix_notifications_type", "notifications", ["type"])
    op.create_index("ix_notifications_target_role", "notifications", ["target_role"])
    op.create_index("ix_notifications_recipient_id", "notifications", ["recipient_id"])
    op.create_index("ix_notifications_entity_id", "notifications", ["entity_id"])

    op.create_table(
        "notification_recipients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("notification_id", "user_id", name="uq_notification_recipient"),
    )
    op.create_index("ix_notification_recipients_clinic_id", "notification_recipients", ["clinic_id"])
    op.create_index("ix_notification_recipients_notification_id", "notification_recipients", ["notification_id"])
    op.create_index("ix_notification_recipients_user_id", "notification_recipients", ["user_id"])


def downgrade() -> None:
    op.drop_table("notification_recipients")
    op.drop_table("notifications")
    op.drop_column("medicine_batches", "last_alerted_expiry_tier")
    op.drop_column("clinics", "medicine_expiry_warning_days_tier4")
    op.drop_column("clinics", "medicine_expiry_warning_days_tier3")
    op.drop_column("clinics", "medicine_expiry_warning_days_tier2")
    op.drop_column("clinics", "medicine_expiry_warning_days_tier1")
