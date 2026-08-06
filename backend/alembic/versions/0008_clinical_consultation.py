"""Clinical Consultation / SOAP (Phase 8).

Adds:
- `consultations` - one clinical encounter document per Visit (see
  `app/models/consultation.py` for the "latest wins" / no-hard-unique
  design decision, and the reuse of `visit_locks` for locking instead of a
  second lock table).
- `soap_notes` - one-to-one with `consultations`, upserted in place on
  every autosave.
- `diagnoses` - Primary/Secondary, Working/Final, ICD-10 fields
  architecture-only (no search UI).
- `consultation_attachments` - real upload path for Clinical
  Images/PDF/Referral Letters (Lab Requests intentionally excluded - stays
  a placeholder, no upload path).
- `patients.emergency_contact_name` / `patients.emergency_contact_phone` -
  additive nullable columns, closing the Phase 7 TODO.
- New `visit_timeline_event_type` enum values for consultation events
  (consultation events are recorded on the existing Visit timeline, not a
  parallel one).

Revision ID: 0008_clinical_consultation
Revises: 0007_doctor_workspace
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_clinical_consultation"
down_revision: str | None = "0007_doctor_workspace"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # --- extend visit_timeline_event_type with consultation events ---
    for value in ("ConsultationOpened", "SoapSaved", "DiagnosisAdded", "ConsultationCompleted", "ConsultationSigned"):
        op.execute(f"ALTER TYPE visit_timeline_event_type ADD VALUE IF NOT EXISTS '{value}'")

    consultation_status_enum = postgresql.ENUM(
        "Draft", "InProgress", "Completed", "Signed", name="consultation_status", create_type=False,
    )
    consultation_status_enum.create(bind, checkfirst=True)

    diagnosis_type_enum = postgresql.ENUM("Primary", "Secondary", name="diagnosis_type", create_type=False)
    diagnosis_type_enum.create(bind, checkfirst=True)

    diagnosis_status_enum = postgresql.ENUM("Working", "Final", name="diagnosis_status", create_type=False)
    diagnosis_status_enum.create(bind, checkfirst=True)

    attachment_type_enum = postgresql.ENUM(
        "ClinicalImage", "PDF", "ReferralLetter", name="consultation_attachment_type", create_type=False,
    )
    attachment_type_enum.create(bind, checkfirst=True)

    # --- patients.emergency_contact_* (additive nullable) ---
    op.add_column("patients", sa.Column("emergency_contact_name", sa.String(length=150), nullable=True))
    op.add_column("patients", sa.Column("emergency_contact_phone", sa.String(length=20), nullable=True))

    # --- consultations ---
    op.create_table(
        "consultations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("legacy_id", sa.String(length=64), nullable=True),
        sa.Column("legacy_meta", postgresql.JSONB(), nullable=True),
        sa.Column("legacy_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legacy_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("migration_batch_id", sa.String(length=64), nullable=True),
        sa.Column("migration_source", sa.String(length=100), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", consultation_status_enum, nullable=False, server_default="Draft"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_consultations_clinic_id", "consultations", ["clinic_id"])
    op.create_index("ix_consultations_visit_id", "consultations", ["visit_id"])
    op.create_index("ix_consultations_branch_id", "consultations", ["branch_id"])
    op.create_index("ix_consultations_doctor_id", "consultations", ["doctor_id"])
    op.create_index("ix_consultations_patient_id", "consultations", ["patient_id"])
    op.create_index("ix_consultations_status", "consultations", ["status"])
    op.create_index("ix_consultations_legacy_id", "consultations", ["legacy_id"])
    op.create_index("ix_consultations_migration_batch_id", "consultations", ["migration_batch_id"])

    # --- soap_notes ---
    op.create_table(
        "soap_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("legacy_id", sa.String(length=64), nullable=True),
        sa.Column("legacy_meta", postgresql.JSONB(), nullable=True),
        sa.Column("legacy_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legacy_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("migration_batch_id", sa.String(length=64), nullable=True),
        sa.Column("migration_source", sa.String(length=100), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consultation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("chief_complaint", sa.Text(), nullable=True),
        sa.Column("history_of_present_illness", sa.Text(), nullable=True),
        sa.Column("past_medical_history", sa.Text(), nullable=True),
        sa.Column("family_history", sa.Text(), nullable=True),
        sa.Column("social_history", sa.Text(), nullable=True),
        sa.Column("review_of_systems", sa.Text(), nullable=True),
        sa.Column("subjective_notes", sa.Text(), nullable=True),
        sa.Column("blood_pressure", sa.Text(), nullable=True),
        sa.Column("pulse_rate", sa.Integer(), nullable=True),
        sa.Column("respiratory_rate", sa.Integer(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("height_cm", sa.Float(), nullable=True),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("bmi", sa.Float(), nullable=True),
        sa.Column("oxygen_saturation", sa.Float(), nullable=True),
        sa.Column("physical_examination", sa.Text(), nullable=True),
        sa.Column("clinical_findings", sa.Text(), nullable=True),
        sa.Column("clinical_impression", sa.Text(), nullable=True),
        sa.Column("differential_diagnosis", sa.Text(), nullable=True),
        sa.Column("assessment_notes", sa.Text(), nullable=True),
        sa.Column("treatment_plan", sa.Text(), nullable=True),
        sa.Column("patient_instructions", sa.Text(), nullable=True),
        sa.Column("followup_recommendation", sa.Text(), nullable=True),
        sa.Column("referral_notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_soap_notes_clinic_id", "soap_notes", ["clinic_id"])
    op.create_index("ix_soap_notes_consultation_id", "soap_notes", ["consultation_id"])
    op.create_index("ix_soap_notes_legacy_id", "soap_notes", ["legacy_id"])
    op.create_index("ix_soap_notes_migration_batch_id", "soap_notes", ["migration_batch_id"])

    # --- diagnoses ---
    op.create_table(
        "diagnoses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("legacy_id", sa.String(length=64), nullable=True),
        sa.Column("legacy_meta", postgresql.JSONB(), nullable=True),
        sa.Column("legacy_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legacy_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("migration_batch_id", sa.String(length=64), nullable=True),
        sa.Column("migration_source", sa.String(length=100), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consultation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("diagnosis_type", diagnosis_type_enum, nullable=False),
        sa.Column("status", diagnosis_status_enum, nullable=False, server_default="Working"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("icd10_code", sa.String(length=20), nullable=True),
        sa.Column("icd10_description", sa.String(length=255), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_diagnoses_clinic_id", "diagnoses", ["clinic_id"])
    op.create_index("ix_diagnoses_consultation_id", "diagnoses", ["consultation_id"])
    op.create_index("ix_diagnoses_legacy_id", "diagnoses", ["legacy_id"])
    op.create_index("ix_diagnoses_migration_batch_id", "diagnoses", ["migration_batch_id"])

    # --- consultation_attachments ---
    op.create_table(
        "consultation_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("legacy_id", sa.String(length=64), nullable=True),
        sa.Column("legacy_meta", postgresql.JSONB(), nullable=True),
        sa.Column("legacy_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legacy_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("migration_batch_id", sa.String(length=64), nullable=True),
        sa.Column("migration_source", sa.String(length=100), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consultation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attachment_type", attachment_type_enum, nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_url", sa.String(length=500), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_consultation_attachments_clinic_id", "consultation_attachments", ["clinic_id"])
    op.create_index("ix_consultation_attachments_consultation_id", "consultation_attachments", ["consultation_id"])
    op.create_index("ix_consultation_attachments_legacy_id", "consultation_attachments", ["legacy_id"])
    op.create_index("ix_consultation_attachments_migration_batch_id", "consultation_attachments", ["migration_batch_id"])


def downgrade() -> None:
    op.drop_index("ix_consultation_attachments_migration_batch_id", table_name="consultation_attachments")
    op.drop_index("ix_consultation_attachments_legacy_id", table_name="consultation_attachments")
    op.drop_index("ix_consultation_attachments_consultation_id", table_name="consultation_attachments")
    op.drop_index("ix_consultation_attachments_clinic_id", table_name="consultation_attachments")
    op.drop_table("consultation_attachments")

    op.drop_index("ix_diagnoses_migration_batch_id", table_name="diagnoses")
    op.drop_index("ix_diagnoses_legacy_id", table_name="diagnoses")
    op.drop_index("ix_diagnoses_consultation_id", table_name="diagnoses")
    op.drop_index("ix_diagnoses_clinic_id", table_name="diagnoses")
    op.drop_table("diagnoses")

    op.drop_index("ix_soap_notes_migration_batch_id", table_name="soap_notes")
    op.drop_index("ix_soap_notes_legacy_id", table_name="soap_notes")
    op.drop_index("ix_soap_notes_consultation_id", table_name="soap_notes")
    op.drop_index("ix_soap_notes_clinic_id", table_name="soap_notes")
    op.drop_table("soap_notes")

    op.drop_index("ix_consultations_migration_batch_id", table_name="consultations")
    op.drop_index("ix_consultations_legacy_id", table_name="consultations")
    op.drop_index("ix_consultations_status", table_name="consultations")
    op.drop_index("ix_consultations_patient_id", table_name="consultations")
    op.drop_index("ix_consultations_doctor_id", table_name="consultations")
    op.drop_index("ix_consultations_branch_id", table_name="consultations")
    op.drop_index("ix_consultations_visit_id", table_name="consultations")
    op.drop_index("ix_consultations_clinic_id", table_name="consultations")
    op.drop_table("consultations")

    op.drop_column("patients", "emergency_contact_phone")
    op.drop_column("patients", "emergency_contact_name")

    op.execute("DROP TYPE IF EXISTS consultation_attachment_type")
    op.execute("DROP TYPE IF EXISTS diagnosis_status")
    op.execute("DROP TYPE IF EXISTS diagnosis_type")
    op.execute("DROP TYPE IF EXISTS consultation_status")
    # Note: new visit_timeline_event_type enum values are not removed on
    # downgrade (Postgres does not support dropping enum values).
