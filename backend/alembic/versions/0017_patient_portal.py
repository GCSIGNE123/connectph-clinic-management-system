"""Phase 18: Patient Portal (patient-principal auth layer)

Adds a THIRD, structurally separate auth model alongside clinic-staff
`users` (Phase 1) and platform-admin `platform_admin_users` (Phase 15):

    patient_accounts                - one-to-one login-credential record per Patient
    patient_password_reset_tokens   - patient-portal-only reset tokens
    patient_notification_preferences- simple settings row per patient
    patient_notifications           - read-only in-app notification feed

Also adds `patient_visible` (default false - safer default, clinic staff
must explicitly opt records in) to `diagnoses` and `consultation_attachments`
so the Patient Portal's Medical Records view can filter to only
clinician-approved-for-sharing rows.

Revision ID: 0017_patient_portal
Revises: 0016_hardening_indexes
Create Date: 2026-07-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017_patient_portal"
down_revision: Union[str, None] = "0016_hardening_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "patient_accounts",
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("auth_method", sa.String(length=30), server_default="password", nullable=False),
        sa.Column("is_email_verified", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("patient_id"),
    )
    op.create_index(op.f("ix_patient_accounts_patient_id"), "patient_accounts", ["patient_id"], unique=True)
    op.create_index(op.f("ix_patient_accounts_clinic_id"), "patient_accounts", ["clinic_id"], unique=False)

    op.create_table(
        "patient_password_reset_tokens",
        sa.Column("patient_account_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["patient_account_id"], ["patient_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_patient_password_reset_tokens_patient_account_id"),
        "patient_password_reset_tokens", ["patient_account_id"], unique=False,
    )
    op.create_index(
        op.f("ix_patient_password_reset_tokens_token_hash"), "patient_password_reset_tokens", ["token_hash"], unique=True
    )

    op.create_table(
        "patient_notification_preferences",
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("appointment_reminders", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("lab_result_alerts", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("billing_notices", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("clinic_announcements", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "preferred_channel",
            sa.Enum("InApp", "Email", "SMS", "Push", name="patient_notification_channel"),
            server_default="InApp",
            nullable=False,
        ),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("patient_id"),
    )
    op.create_index(
        op.f("ix_patient_notification_preferences_patient_id"),
        "patient_notification_preferences", ["patient_id"], unique=True,
    )

    op.create_table(
        "patient_notifications",
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column(
            "notification_type",
            sa.Enum(
                "AppointmentReminder", "LabResultReleased", "BillingNotice", "ClinicAnnouncement",
                name="patient_notification_type",
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("is_read", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_patient_notifications_patient_id"), "patient_notifications", ["patient_id"], unique=False)
    op.create_index(op.f("ix_patient_notifications_clinic_id"), "patient_notifications", ["clinic_id"], unique=False)

    # --- Patient-visibility opt-in flags (safer default: false) ---
    op.add_column("diagnoses", sa.Column("patient_visible", sa.Boolean(), server_default="false", nullable=False))
    op.add_column(
        "consultation_attachments", sa.Column("patient_visible", sa.Boolean(), server_default="false", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("consultation_attachments", "patient_visible")
    op.drop_column("diagnoses", "patient_visible")

    op.drop_index(op.f("ix_patient_notifications_clinic_id"), table_name="patient_notifications")
    op.drop_index(op.f("ix_patient_notifications_patient_id"), table_name="patient_notifications")
    op.drop_table("patient_notifications")
    op.execute("DROP TYPE IF EXISTS patient_notification_type")

    op.drop_index(
        op.f("ix_patient_notification_preferences_patient_id"), table_name="patient_notification_preferences"
    )
    op.drop_table("patient_notification_preferences")
    op.execute("DROP TYPE IF EXISTS patient_notification_channel")

    op.drop_index(op.f("ix_patient_password_reset_tokens_token_hash"), table_name="patient_password_reset_tokens")
    op.drop_index(
        op.f("ix_patient_password_reset_tokens_patient_account_id"), table_name="patient_password_reset_tokens"
    )
    op.drop_table("patient_password_reset_tokens")

    op.drop_index(op.f("ix_patient_accounts_clinic_id"), table_name="patient_accounts")
    op.drop_index(op.f("ix_patient_accounts_patient_id"), table_name="patient_accounts")
    op.drop_table("patient_accounts")
