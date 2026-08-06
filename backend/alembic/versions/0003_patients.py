"""Patient management: master patients table with tenant/branch scoping,
soft-delete, patient_number generation support (via system_settings), and
indexes to support fast search/filter/sort at 100k+ rows per clinic.

Revision ID: 0003_patients
Revises: 0002_auth_user_management
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_patients"
down_revision: str | None = "0002_auth_user_management"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    gender_enum = postgresql.ENUM("Male", "Female", "Other", name="patient_gender", create_type=False)
    civil_status_enum = postgresql.ENUM(
        "Single", "Married", "Widowed", "Separated", "Divorced", name="patient_civil_status", create_type=False
    )
    blood_type_enum = postgresql.ENUM(
        "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "Unknown", name="patient_blood_type", create_type=False
    )
    patient_status_enum = postgresql.ENUM("Active", "Archived", name="patient_status", create_type=False)

    bind = op.get_bind()
    gender_enum.create(bind, checkfirst=True)
    civil_status_enum.create(bind, checkfirst=True)
    blood_type_enum.create(bind, checkfirst=True)
    patient_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "patients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legacy_id", sa.String(length=64), nullable=True),
        sa.Column("legacy_meta", postgresql.JSONB(), nullable=True),
        sa.Column("legacy_patient_id", sa.String(length=64), nullable=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="SET NULL"), nullable=True),
        sa.Column("patient_number", sa.String(length=30), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("middle_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("suffix", sa.String(length=20), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=False),
        sa.Column("gender", gender_enum, nullable=False),
        sa.Column("civil_status", civil_status_enum, nullable=False),
        sa.Column("nationality", sa.String(length=100), nullable=False, server_default="Filipino"),
        sa.Column("address_line", sa.String(length=255), nullable=True),
        sa.Column("barangay", sa.String(length=150), nullable=True),
        sa.Column("city", sa.String(length=150), nullable=True),
        sa.Column("province", sa.String(length=150), nullable=True),
        sa.Column("zip_code", sa.String(length=20), nullable=True),
        sa.Column("mobile_number", sa.String(length=20), nullable=False),
        sa.Column("telephone_number", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("occupation", sa.String(length=150), nullable=True),
        sa.Column("employer", sa.String(length=150), nullable=True),
        sa.Column("blood_type", blood_type_enum, nullable=True),
        sa.Column("allergies", sa.Text(), nullable=True),
        sa.Column("medical_notes", sa.Text(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("photo_url", sa.String(length=500), nullable=True),
        sa.Column("qr_code", sa.String(length=255), nullable=True),
        sa.Column(
            "status", patient_status_enum, nullable=False, server_default="Active",
        ),
        sa.Column("date_registered", sa.Date(), nullable=False),
        sa.Column("last_visit", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("clinic_id", "patient_number", name="uq_patient_clinic_patient_number"),
        sa.UniqueConstraint("qr_code", name="uq_patients_qr_code"),
    )

    op.create_index("ix_patients_clinic_id", "patients", ["clinic_id"])
    op.create_index("ix_patients_branch_id", "patients", ["branch_id"])
    op.create_index("ix_patients_legacy_id", "patients", ["legacy_id"])
    op.create_index("ix_patients_legacy_patient_id", "patients", ["legacy_patient_id"])
    op.create_index("ix_patients_status", "patients", ["status"])
    op.create_index("ix_patients_birth_date", "patients", ["birth_date"])
    op.create_index(
        "ix_patients_clinic_lastname_firstname", "patients", ["clinic_id", "last_name", "first_name"]
    )
    op.create_index("ix_patients_clinic_mobile", "patients", ["clinic_id", "mobile_number"])
    op.create_index("ix_patients_clinic_birthdate", "patients", ["clinic_id", "birth_date"])


def downgrade() -> None:
    op.drop_index("ix_patients_clinic_birthdate", table_name="patients")
    op.drop_index("ix_patients_clinic_mobile", table_name="patients")
    op.drop_index("ix_patients_clinic_lastname_firstname", table_name="patients")
    op.drop_index("ix_patients_status", table_name="patients")
    op.drop_index("ix_patients_birth_date", table_name="patients")
    op.drop_index("ix_patients_legacy_patient_id", table_name="patients")
    op.drop_index("ix_patients_legacy_id", table_name="patients")
    op.drop_index("ix_patients_branch_id", table_name="patients")
    op.drop_index("ix_patients_clinic_id", table_name="patients")
    op.drop_table("patients")

    op.execute("DROP TYPE IF EXISTS patient_status")
    op.execute("DROP TYPE IF EXISTS patient_blood_type")
    op.execute("DROP TYPE IF EXISTS patient_civil_status")
    op.execute("DROP TYPE IF EXISTS patient_gender")
