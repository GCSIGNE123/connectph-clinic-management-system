"""TV Display Information/Advertisement Panel content (Post-RC1).

Adds `tv_info_content` - clinic-wide, admin-configurable content rotated in
the right half of the TV Display's new 50/50 queue+info layout. Deliberately
a new table rather than an extension of `tv_announcements`; see
`app/models/tv_info_content.py` module docstring for the full rationale.

Revision ID: 0027_tv_info_content
Revises: 0026_queue_setting_room_label
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_tv_info_content"
down_revision: str | None = "0026_queue_setting_room_label"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    tv_info_content_type = sa.Enum(
        "ServicePricing",
        "DoctorInfo",
        "HealthTip",
        "PreventiveReminder",
        "Announcement",
        "Promotion",
        "Motivational",
        name="tv_info_content_type",
    )

    op.create_table(
        "tv_info_content",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("content_type", tv_info_content_type, nullable=False, server_default="Announcement"),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legacy_id", sa.String(64), nullable=True),
        sa.Column("legacy_meta", postgresql.JSONB(), nullable=True),
        sa.Column("legacy_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legacy_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("migration_batch_id", sa.String(64), nullable=True),
        sa.Column("migration_source", sa.String(100), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tv_info_content_legacy_id", "tv_info_content", ["legacy_id"])
    op.create_index("ix_tv_info_content_migration_batch_id", "tv_info_content", ["migration_batch_id"])


def downgrade() -> None:
    op.drop_table("tv_info_content")
    bind = op.get_bind()
    postgresql.ENUM(name="tv_info_content_type").drop(bind, checkfirst=True)
