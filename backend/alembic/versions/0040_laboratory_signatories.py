"""Laboratory Report Signatories (Round 6): Med Tech In Charge + Pathologist.

Greenfield/additive - no existing column/table's semantics change.

1. New `pathologists` table - clinic master data (name, license_number,
   signature_url, is_active), same UUID/timestamp/soft-delete/tenant/
   legacy-migration column shape as every other Phase 4 master-data catalog
   table (see `medicines` in 0037). Deliberately NOT a `User`/login account
   - pathologists are selected from this configured list at Laboratory
   release time, the same way a Doctor record or Laboratory template is
   master data.

2. `users.license_number` / `users.signature_url` - a Laboratory-role
   user's own professional number and e-signature (meaningful only for that
   role, same "nullable, only meaningful for one role" convention as the
   existing `users.doctor_id`). The Med Tech In Charge on a Laboratory
   Report is the authenticated Laboratory user who releases the results
   (`laboratory_orders.released_by`, already existed - no new identity
   concept introduced), so their signature lives on their own account.

3. `laboratory_orders` additions:
   - `pathologist_id` (nullable FK -> pathologists.id, SET NULL on delete) -
     the Pathologist selected as part of the release workflow. Kept for
     traceability/UI convenience only; report rendering never re-joins it.
   - `med_tech_name_snapshot` / `med_tech_license_snapshot` /
     `med_tech_signature_snapshot_url`
   - `pathologist_name_snapshot` / `pathologist_license_snapshot` /
     `pathologist_signature_snapshot_url`
   All six captured ONCE, at `release_results()`, from whatever was true
   at that moment - same "snapshot, never re-resolve" convention the
   existing Doctor E-Signature feature already uses for Prescription/
   Referral/Medical Certificate (see migration 0036 and
   `MedicalCertificateService.issue`). A later edit to the Pathologist's or
   releasing user's current signature/name, or a later change of which
   Pathologist is selected for NEW releases, must never alter an
   already-released report.

Revision ID: 0040_laboratory_signatories
Revises: 0039_medicine_expiry_notify
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0040_laboratory_signatories"
down_revision: str | None = "0039_medicine_expiry_notify"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


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
    op.create_table(
        "pathologists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("license_number", sa.String(length=50), nullable=True),
        sa.Column("signature_url", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pathologists_clinic_id", "pathologists", ["clinic_id"])
    op.create_index("ix_pathologists_legacy_id", "pathologists", ["legacy_id"])
    op.create_index("ix_pathologists_migration_batch_id", "pathologists", ["migration_batch_id"])

    op.add_column("users", sa.Column("license_number", sa.String(length=50), nullable=True))
    op.add_column("users", sa.Column("signature_url", sa.String(length=500), nullable=True))

    op.add_column(
        "laboratory_orders",
        sa.Column("pathologist_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pathologists.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_laboratory_orders_pathologist_id", "laboratory_orders", ["pathologist_id"])
    op.add_column("laboratory_orders", sa.Column("med_tech_name_snapshot", sa.String(length=255), nullable=True))
    op.add_column("laboratory_orders", sa.Column("med_tech_license_snapshot", sa.String(length=50), nullable=True))
    op.add_column("laboratory_orders", sa.Column("med_tech_signature_snapshot_url", sa.String(length=500), nullable=True))
    op.add_column("laboratory_orders", sa.Column("pathologist_name_snapshot", sa.String(length=255), nullable=True))
    op.add_column("laboratory_orders", sa.Column("pathologist_license_snapshot", sa.String(length=50), nullable=True))
    op.add_column("laboratory_orders", sa.Column("pathologist_signature_snapshot_url", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("laboratory_orders", "pathologist_signature_snapshot_url")
    op.drop_column("laboratory_orders", "pathologist_license_snapshot")
    op.drop_column("laboratory_orders", "pathologist_name_snapshot")
    op.drop_column("laboratory_orders", "med_tech_signature_snapshot_url")
    op.drop_column("laboratory_orders", "med_tech_license_snapshot")
    op.drop_column("laboratory_orders", "med_tech_name_snapshot")
    op.drop_index("ix_laboratory_orders_pathologist_id", table_name="laboratory_orders")
    op.drop_column("laboratory_orders", "pathologist_id")

    op.drop_column("users", "signature_url")
    op.drop_column("users", "license_number")

    op.drop_index("ix_pathologists_migration_batch_id", table_name="pathologists")
    op.drop_index("ix_pathologists_legacy_id", table_name="pathologists")
    op.drop_index("ix_pathologists_clinic_id", table_name="pathologists")
    op.drop_table("pathologists")
