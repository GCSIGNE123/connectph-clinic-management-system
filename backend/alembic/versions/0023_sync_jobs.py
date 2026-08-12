"""Cloud Backup sync queue (Post-RC1 Phase 2 Milestone 2)

Adds `sync_jobs`: the persistent local->cloud upload queue drained by
`app/services/sync_worker_service.py`. Purely additive/new table - no
existing table/column is touched, so this migration is a no-op for every
row that already exists in any other table.

Revision ID: 0023_sync_jobs
Revises: 0022_pre_queue_vitals
Create Date: 2026-08-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0023_sync_jobs"
down_revision: Union[str, None] = "0022_pre_queue_vitals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sync_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=20), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sync_jobs_clinic_id", "sync_jobs", ["clinic_id"])
    op.create_index("ix_sync_jobs_entity_type", "sync_jobs", ["entity_type"])
    op.create_index("ix_sync_jobs_record_id", "sync_jobs", ["record_id"])
    op.create_index("ix_sync_jobs_status", "sync_jobs", ["status"])
    op.create_index("ix_sync_jobs_next_retry_at", "sync_jobs", ["next_retry_at"])
    # Worker's primary query: oldest-pending-first, ready to (re)try now.
    op.create_index(
        "ix_sync_jobs_status_created_at",
        "sync_jobs",
        ["status", "created_at"],
    )

    # `synced_records`: the table a CLOUD-hosted instance of this same
    # codebase (pointed at CLOUD_DATABASE_URL) stores incoming backup
    # uploads into. Created in every environment's migration history (same
    # codebase runs both sides) but only ever written to when this instance
    # is actually acting as the cloud endpoint. No FK to clinics.id - see
    # app/models/synced_record.py docstring for why.
    op.create_table(
        "synced_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=20), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("clinic_id", "entity_type", "record_id", name="uq_synced_records_clinic_entity_record"),
    )
    op.create_index("ix_synced_records_clinic_id", "synced_records", ["clinic_id"])
    op.create_index("ix_synced_records_entity_type", "synced_records", ["entity_type"])
    op.create_index("ix_synced_records_record_id", "synced_records", ["record_id"])


def downgrade() -> None:
    op.drop_index("ix_synced_records_record_id", table_name="synced_records")
    op.drop_index("ix_synced_records_entity_type", table_name="synced_records")
    op.drop_index("ix_synced_records_clinic_id", table_name="synced_records")
    op.drop_table("synced_records")
    op.drop_index("ix_sync_jobs_status_created_at", table_name="sync_jobs")
    op.drop_index("ix_sync_jobs_next_retry_at", table_name="sync_jobs")
    op.drop_index("ix_sync_jobs_status", table_name="sync_jobs")
    op.drop_index("ix_sync_jobs_record_id", table_name="sync_jobs")
    op.drop_index("ix_sync_jobs_entity_type", table_name="sync_jobs")
    op.drop_index("ix_sync_jobs_clinic_id", table_name="sync_jobs")
    op.drop_table("sync_jobs")
