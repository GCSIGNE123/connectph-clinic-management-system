"""Vaccination Administration (Post-RC1)

Adds `vaccination_administrations`: the vaccination workflow's own record
layered 1:1 on top of a Phase 9 `Order` (order_category=Vaccination),
mirroring `laboratory_orders` from migration 0011. Purely additive - no
existing table/column is touched.

Revision ID: 0024_vaccination_administration
Revises: 0023_sync_jobs
Create Date: 2026-08-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0024_vaccination_administration"
down_revision: Union[str, None] = "0023_sync_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
    vaccination_status = postgresql.ENUM(
        "Requested", "Administered", "Cancelled", name="vaccination_status", create_type=False,
    )
    vaccination_status.create(bind, checkfirst=True)

    op.create_table(
        "vaccination_administrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("vaccine_name", sa.String(length=255), nullable=False),
        sa.Column("status", vaccination_status, nullable=False, server_default="Requested"),
        sa.Column("dose", sa.String(length=100), nullable=True),
        sa.Column("lot_number", sa.String(length=100), nullable=True),
        sa.Column("site", sa.String(length=100), nullable=True),
        sa.Column("route", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("administered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("administered_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_vaccination_administrations_clinic_id", "vaccination_administrations", ["clinic_id"])
    op.create_index("ix_vaccination_administrations_order_id", "vaccination_administrations", ["order_id"])
    op.create_index("ix_vaccination_administrations_visit_id", "vaccination_administrations", ["visit_id"])
    op.create_index("ix_vaccination_administrations_patient_id", "vaccination_administrations", ["patient_id"])
    op.create_index("ix_vaccination_administrations_doctor_id", "vaccination_administrations", ["doctor_id"])
    op.create_index("ix_vaccination_administrations_status", "vaccination_administrations", ["status"])
    op.create_index("ix_vaccination_administrations_legacy_id", "vaccination_administrations", ["legacy_id"])
    op.create_index("ix_vaccination_administrations_migration_batch_id", "vaccination_administrations", ["migration_batch_id"])


def downgrade() -> None:
    op.drop_index("ix_vaccination_administrations_migration_batch_id", table_name="vaccination_administrations")
    op.drop_index("ix_vaccination_administrations_legacy_id", table_name="vaccination_administrations")
    op.drop_index("ix_vaccination_administrations_status", table_name="vaccination_administrations")
    op.drop_index("ix_vaccination_administrations_doctor_id", table_name="vaccination_administrations")
    op.drop_index("ix_vaccination_administrations_patient_id", table_name="vaccination_administrations")
    op.drop_index("ix_vaccination_administrations_visit_id", table_name="vaccination_administrations")
    op.drop_index("ix_vaccination_administrations_order_id", table_name="vaccination_administrations")
    op.drop_index("ix_vaccination_administrations_clinic_id", table_name="vaccination_administrations")
    op.drop_table("vaccination_administrations")
    op.execute("DROP TYPE IF EXISTS vaccination_status")
