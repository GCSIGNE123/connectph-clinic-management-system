"""TV Queue Display (Phase 13).

Adds:
- `tv_display_configs` - one row per configured display (clinic-wide, or
  narrowed to a branch/department/doctor). Carries visual/behavioral
  settings (theme/font/queue size/animation/refresh interval/logo/colors)
  and the public-access model (`is_public` + unique `public_slug`).
  `tts_enabled`/`tts_template` are architecture-only (text templating, no
  audio synthesis - see `services/tts_service.py`).
- `tv_announcements` - scrolling-ticker content, either clinic-wide
  (`tv_display_config_id IS NULL`) or scoped to one display.

Both tables get the standard legacy-migration mixin fields for consistency
with every other phase's tables, even though display configuration/
announcement rows are unlikely to ever be bulk-imported from the legacy
desktop app - kept for consistency and because it costs nothing (all
additive nullable columns).

Revision ID: 0013_tv_queue_display
Revises: 0012_appointment_management
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_tv_queue_display"
down_revision: str | None = "0012_appointment_management"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    tv_display_theme = sa.Enum(
        "Light", "Dark", "ClinicBranded", name="tv_display_theme"
    )
    tv_display_font_size = sa.Enum(
        "Small", "Medium", "Large", "ExtraLarge", name="tv_display_font_size"
    )
    tv_display_animation_speed = sa.Enum(
        "None", "Slow", "Normal", "Fast", name="tv_display_animation_speed"
    )
    tv_announcement_type = sa.Enum(
        "Welcome", "HealthTip", "Promotion", "Emergency", name="tv_announcement_type"
    )

    op.create_table(
        "tv_display_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("display_name", sa.String(150), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("public_slug", sa.String(64), nullable=True, unique=True),
        sa.Column("theme", tv_display_theme, nullable=False, server_default="ClinicBranded"),
        sa.Column("font_size", tv_display_font_size, nullable=False, server_default="Large"),
        sa.Column("animation_speed", tv_display_animation_speed, nullable=False, server_default="Normal"),
        sa.Column("queue_size", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("refresh_interval_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("logo_url", sa.String(500), nullable=True),
        sa.Column("primary_color", sa.String(20), nullable=True),
        sa.Column("secondary_color", sa.String(20), nullable=True),
        sa.Column("tts_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("tts_template", sa.Text(), nullable=True, server_default="Queue {queue_number}, please proceed to {room}."),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
    op.create_index("ix_tv_display_configs_legacy_id", "tv_display_configs", ["legacy_id"])
    op.create_index("ix_tv_display_configs_migration_batch_id", "tv_display_configs", ["migration_batch_id"])
    op.create_index("ix_tv_display_configs_public_slug", "tv_display_configs", ["public_slug"], unique=True)

    op.create_table(
        "tv_announcements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tv_display_config_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tv_display_configs.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("announcement_type", tv_announcement_type, nullable=False, server_default="Welcome"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("starts_at", sa.Date(), nullable=True),
        sa.Column("ends_at", sa.Date(), nullable=True),
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
    op.create_index("ix_tv_announcements_legacy_id", "tv_announcements", ["legacy_id"])
    op.create_index("ix_tv_announcements_migration_batch_id", "tv_announcements", ["migration_batch_id"])


def downgrade() -> None:
    op.drop_table("tv_announcements")
    op.drop_table("tv_display_configs")
    bind = op.get_bind()
    postgresql.ENUM(name="tv_announcement_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="tv_display_animation_speed").drop(bind, checkfirst=True)
    postgresql.ENUM(name="tv_display_font_size").drop(bind, checkfirst=True)
    postgresql.ENUM(name="tv_display_theme").drop(bind, checkfirst=True)
