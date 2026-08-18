"""Medical Certificates.

Adds:
- `medical_certificate_type` / `medical_certificate_status` enums.
- `medical_certificates` table - standalone table (not an `orders` row),
  following the exact same precedent `referrals`/`prescriptions` already
  set. Lifecycle Draft -> Issued -> Cancelled (see
  `services/medical_certificate_service.py`). `superseded_by_id` is a
  self-referencing FK used only by the Cancel+Reissue correction workflow -
  nullable, SET NULL on delete of the replacement.
- New `visit_timeline_event_type` enum values `CertificateIssued`/
  `CertificateCancelled`, same `ALTER TYPE ... ADD VALUE IF NOT EXISTS`
  pattern already used by `0009_clinical_orders_prescriptions.py` for its
  own new timeline event values.

Revision ID: 0035_medical_certificates
Revises: 0034_laboratory_order_id_nullable
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035_medical_certificates"
down_revision: str | None = "0034_laboratory_order_id_nullable"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _legacy_columns():
    # Return fresh Column objects each call - SQLAlchemy Column instances
    # cannot be reused across multiple Table definitions.
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

    for value in ("CertificateIssued", "CertificateCancelled"):
        op.execute(f"ALTER TYPE visit_timeline_event_type ADD VALUE IF NOT EXISTS '{value}'")

    certificate_type_enum = postgresql.ENUM(
        "MedicalCertificate", "FitToWork", "SickLeave", "Custom",
        name="medical_certificate_type", create_type=False,
    )
    certificate_type_enum.create(bind, checkfirst=True)

    certificate_status_enum = postgresql.ENUM(
        "Draft", "Issued", "Cancelled", name="medical_certificate_status", create_type=False,
    )
    certificate_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "medical_certificates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("consultation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("certificate_number", sa.String(length=40), nullable=True),
        sa.Column("certificate_type", certificate_type_enum, nullable=False),
        sa.Column("status", certificate_status_enum, nullable=False, server_default="Draft"),
        sa.Column("findings", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("rest_days", sa.Integer(), nullable=True),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_reason", sa.Text(), nullable=True),
        sa.Column("cancelled_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    # Self-referencing FK added separately (the table must exist first).
    op.create_foreign_key(
        "fk_medical_certificates_superseded_by_id", "medical_certificates",
        "medical_certificates", ["superseded_by_id"], ["id"], ondelete="SET NULL",
    )

    op.create_index("ix_medical_certificates_clinic_id", "medical_certificates", ["clinic_id"])
    op.create_index("ix_medical_certificates_consultation_id", "medical_certificates", ["consultation_id"])
    op.create_index("ix_medical_certificates_visit_id", "medical_certificates", ["visit_id"])
    op.create_index("ix_medical_certificates_branch_id", "medical_certificates", ["branch_id"])
    op.create_index("ix_medical_certificates_patient_id", "medical_certificates", ["patient_id"])
    op.create_index("ix_medical_certificates_doctor_id", "medical_certificates", ["doctor_id"])
    op.create_index("ix_medical_certificates_certificate_number", "medical_certificates", ["certificate_number"])
    op.create_index("ix_medical_certificates_legacy_id", "medical_certificates", ["legacy_id"])
    op.create_index("ix_medical_certificates_migration_batch_id", "medical_certificates", ["migration_batch_id"])
    # Unique only among non-null numbers (Drafts have none) - a plain unique
    # constraint would otherwise reject a second NULL just fine in Postgres
    # (NULLs are distinct for uniqueness purposes), so this is actually
    # already safe as a plain constraint; kept explicit for clarity.
    op.create_unique_constraint(
        "uq_medical_certificates_clinic_certificate_number", "medical_certificates", ["clinic_id", "certificate_number"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_medical_certificates_clinic_certificate_number", "medical_certificates", type_="unique")
    op.drop_index("ix_medical_certificates_migration_batch_id", table_name="medical_certificates")
    op.drop_index("ix_medical_certificates_legacy_id", table_name="medical_certificates")
    op.drop_index("ix_medical_certificates_certificate_number", table_name="medical_certificates")
    op.drop_index("ix_medical_certificates_doctor_id", table_name="medical_certificates")
    op.drop_index("ix_medical_certificates_patient_id", table_name="medical_certificates")
    op.drop_index("ix_medical_certificates_branch_id", table_name="medical_certificates")
    op.drop_index("ix_medical_certificates_visit_id", table_name="medical_certificates")
    op.drop_index("ix_medical_certificates_clinic_id", table_name="medical_certificates")
    op.drop_constraint("fk_medical_certificates_superseded_by_id", "medical_certificates", type_="foreignkey")
    op.drop_table("medical_certificates")

    bind = op.get_bind()
    postgresql.ENUM(name="medical_certificate_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="medical_certificate_type").drop(bind, checkfirst=True)

    # No downgrade for the visit_timeline_event_type ADD VALUE above -
    # Postgres cannot remove enum values, matching the same documented
    # limitation already accepted by 0009_clinical_orders_prescriptions.py.
