"""Clinic Configuration & Master Data (Phase 4).

Extends `clinics` with settings/branding fields and `branches` with
code/contact/manager/status fields. Adds: departments, doctors,
doctor_schedules, consultation_rooms, services, queue_settings,
priority_types, operating_hours, holidays.

Revision ID: 0004_clinic_configuration
Revises: 0003_patients
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_clinic_configuration"
down_revision: str | None = "0003_patients"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    doctor_status_enum = postgresql.ENUM("Active", "Inactive", "On Leave", name="doctor_status", create_type=False)
    doctor_status_enum.create(bind, checkfirst=True)

    # --- Extend clinics (settings + branding) ---
    op.add_column("clinics", sa.Column("short_name", sa.String(length=100), nullable=True))
    op.add_column("clinics", sa.Column("province", sa.String(length=150), nullable=True))
    op.add_column("clinics", sa.Column("city", sa.String(length=150), nullable=True))
    op.add_column("clinics", sa.Column("barangay", sa.String(length=150), nullable=True))
    op.add_column("clinics", sa.Column("zip_code", sa.String(length=20), nullable=True))
    op.add_column("clinics", sa.Column("telephone", sa.String(length=50), nullable=True))
    op.add_column("clinics", sa.Column("mobile", sa.String(length=50), nullable=True))
    op.add_column("clinics", sa.Column("website", sa.String(length=255), nullable=True))
    op.add_column("clinics", sa.Column("tin", sa.String(length=50), nullable=True))
    op.add_column("clinics", sa.Column("license_number", sa.String(length=100), nullable=True))
    op.add_column("clinics", sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Asia/Manila"))
    op.add_column("clinics", sa.Column("language", sa.String(length=10), nullable=False, server_default="en"))
    op.add_column("clinics", sa.Column("currency", sa.String(length=10), nullable=False, server_default="PHP"))
    op.add_column("clinics", sa.Column("date_format", sa.String(length=20), nullable=False, server_default="MM/DD/YYYY"))
    op.add_column("clinics", sa.Column("time_format", sa.String(length=10), nullable=False, server_default="12h"))
    op.add_column("clinics", sa.Column("status", sa.String(length=20), nullable=False, server_default="Active"))
    op.add_column("clinics", sa.Column("logo_url", sa.String(length=500), nullable=True))
    op.add_column("clinics", sa.Column("favicon_url", sa.String(length=500), nullable=True))
    op.add_column("clinics", sa.Column("login_background_url", sa.String(length=500), nullable=True))
    op.add_column("clinics", sa.Column("primary_color", sa.String(length=20), nullable=True))
    op.add_column("clinics", sa.Column("secondary_color", sa.String(length=20), nullable=True))
    op.add_column("clinics", sa.Column("theme", sa.String(length=20), nullable=False, server_default="system"))

    # --- Extend branches ---
    op.add_column("branches", sa.Column("code", sa.String(length=30), nullable=True))
    op.add_column("branches", sa.Column("contact_number", sa.String(length=50), nullable=True))
    op.add_column("branches", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column(
        "branches",
        sa.Column("manager_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("branches", sa.Column("status", sa.String(length=20), nullable=False, server_default="Active"))
    op.create_unique_constraint("uq_branch_clinic_code", "branches", ["clinic_id", "code"])

    # --- Departments ---
    op.create_table(
        "departments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("department_code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="Active"),
        sa.UniqueConstraint("clinic_id", "department_code", name="uq_department_clinic_code"),
    )
    op.create_index("ix_departments_clinic_id", "departments", ["clinic_id"])

    # --- Doctors ---
    op.create_table(
        "doctors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctor_code", sa.String(length=30), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("middle_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("suffix", sa.String(length=20), nullable=True),
        sa.Column("prc_license", sa.String(length=50), nullable=True),
        sa.Column("ptr_number", sa.String(length=50), nullable=True),
        sa.Column("specialization", sa.String(length=150), nullable=True),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="SET NULL"), nullable=True),
        sa.Column("photo_url", sa.String(length=500), nullable=True),
        sa.Column("signature_url", sa.String(length=500), nullable=True),
        sa.Column("contact_number", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("consultation_fee", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", doctor_status_enum, nullable=False, server_default="Active"),
        sa.UniqueConstraint("clinic_id", "doctor_code", name="uq_doctor_clinic_code"),
    )
    op.create_index("ix_doctors_clinic_id", "doctors", ["clinic_id"])
    op.create_index("ix_doctors_department_id", "doctors", ["department_id"])
    op.create_index("ix_doctors_branch_id", "doctors", ["branch_id"])
    op.create_index("ix_doctors_status", "doctors", ["status"])

    # --- Doctor schedules ---
    op.create_table(
        "doctor_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="SET NULL"), nullable=True),
        sa.Column("day_of_week", sa.SmallInteger(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_doctor_schedules_clinic_id", "doctor_schedules", ["clinic_id"])
    op.create_index("ix_doctor_schedules_doctor_id", "doctor_schedules", ["doctor_id"])
    op.create_index("ix_doctor_schedules_branch_id", "doctor_schedules", ["branch_id"])

    # --- Consultation rooms ---
    op.create_table(
        "consultation_rooms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("room_name", sa.String(length=150), nullable=False),
        sa.Column("room_number", sa.String(length=30), nullable=True),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="Active"),
    )
    op.create_index("ix_consultation_rooms_clinic_id", "consultation_rooms", ["clinic_id"])
    op.create_index("ix_consultation_rooms_department_id", "consultation_rooms", ["department_id"])
    op.create_index("ix_consultation_rooms_branch_id", "consultation_rooms", ["branch_id"])

    # --- Services catalog ---
    op.create_table(
        "services",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("service_code", sa.String(length=30), nullable=False),
        sa.Column("service_name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("duration_minutes", sa.SmallInteger(), nullable=True),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="Active"),
        sa.UniqueConstraint("clinic_id", "service_code", name="uq_service_clinic_code"),
    )
    op.create_index("ix_services_clinic_id", "services", ["clinic_id"])
    op.create_index("ix_services_department_id", "services", ["department_id"])

    # --- Queue settings + priority types ---
    op.create_table(
        "queue_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=True),
        sa.Column("queue_prefix", sa.String(length=10), nullable=False, server_default="A"),
        sa.Column("max_daily_queue", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("reset_time", sa.Time(), nullable=False),
        sa.Column("allow_walkins", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("allow_priority_lane", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("clinic_id", "branch_id", name="uq_queue_setting_clinic_branch"),
    )
    op.create_index("ix_queue_settings_clinic_id", "queue_settings", ["clinic_id"])

    op.create_table(
        "priority_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("clinic_id", "code", name="uq_priority_type_clinic_code"),
    )
    op.create_index("ix_priority_types_clinic_id", "priority_types", ["clinic_id"])

    # --- Operating hours ---
    op.create_table(
        "operating_hours",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day_of_week", sa.SmallInteger(), nullable=False),
        sa.Column("opening_time", sa.Time(), nullable=True),
        sa.Column("closing_time", sa.Time(), nullable=True),
        sa.Column("lunch_break_start", sa.Time(), nullable=True),
        sa.Column("lunch_break_end", sa.Time(), nullable=True),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("clinic_id", "branch_id", "day_of_week", name="uq_operating_hours_clinic_branch_day"),
    )
    op.create_index("ix_operating_hours_clinic_id", "operating_hours", ["clinic_id"])
    op.create_index("ix_operating_hours_branch_id", "operating_hours", ["branch_id"])

    # --- Holidays ---
    op.create_table(
        "holidays",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("holiday_name", sa.String(length=150), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_half_day", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ix_holidays_clinic_id", "holidays", ["clinic_id"])
    op.create_index("ix_holidays_branch_id", "holidays", ["branch_id"])
    op.create_index("ix_holidays_date", "holidays", ["date"])


def downgrade() -> None:
    op.drop_index("ix_holidays_date", table_name="holidays")
    op.drop_index("ix_holidays_branch_id", table_name="holidays")
    op.drop_index("ix_holidays_clinic_id", table_name="holidays")
    op.drop_table("holidays")

    op.drop_index("ix_operating_hours_branch_id", table_name="operating_hours")
    op.drop_index("ix_operating_hours_clinic_id", table_name="operating_hours")
    op.drop_table("operating_hours")

    op.drop_index("ix_priority_types_clinic_id", table_name="priority_types")
    op.drop_table("priority_types")

    op.drop_index("ix_queue_settings_clinic_id", table_name="queue_settings")
    op.drop_table("queue_settings")

    op.drop_index("ix_services_department_id", table_name="services")
    op.drop_index("ix_services_clinic_id", table_name="services")
    op.drop_table("services")

    op.drop_index("ix_consultation_rooms_branch_id", table_name="consultation_rooms")
    op.drop_index("ix_consultation_rooms_department_id", table_name="consultation_rooms")
    op.drop_index("ix_consultation_rooms_clinic_id", table_name="consultation_rooms")
    op.drop_table("consultation_rooms")

    op.drop_index("ix_doctor_schedules_branch_id", table_name="doctor_schedules")
    op.drop_index("ix_doctor_schedules_doctor_id", table_name="doctor_schedules")
    op.drop_index("ix_doctor_schedules_clinic_id", table_name="doctor_schedules")
    op.drop_table("doctor_schedules")

    op.drop_index("ix_doctors_status", table_name="doctors")
    op.drop_index("ix_doctors_branch_id", table_name="doctors")
    op.drop_index("ix_doctors_department_id", table_name="doctors")
    op.drop_index("ix_doctors_clinic_id", table_name="doctors")
    op.drop_table("doctors")

    op.drop_index("ix_departments_clinic_id", table_name="departments")
    op.drop_table("departments")

    op.drop_constraint("uq_branch_clinic_code", "branches", type_="unique")
    op.drop_column("branches", "status")
    op.drop_column("branches", "manager_id")
    op.drop_column("branches", "email")
    op.drop_column("branches", "contact_number")
    op.drop_column("branches", "code")

    op.drop_column("clinics", "theme")
    op.drop_column("clinics", "secondary_color")
    op.drop_column("clinics", "primary_color")
    op.drop_column("clinics", "login_background_url")
    op.drop_column("clinics", "favicon_url")
    op.drop_column("clinics", "logo_url")
    op.drop_column("clinics", "status")
    op.drop_column("clinics", "time_format")
    op.drop_column("clinics", "date_format")
    op.drop_column("clinics", "currency")
    op.drop_column("clinics", "language")
    op.drop_column("clinics", "timezone")
    op.drop_column("clinics", "license_number")
    op.drop_column("clinics", "tin")
    op.drop_column("clinics", "website")
    op.drop_column("clinics", "mobile")
    op.drop_column("clinics", "telephone")
    op.drop_column("clinics", "zip_code")
    op.drop_column("clinics", "barangay")
    op.drop_column("clinics", "city")
    op.drop_column("clinics", "province")
    op.drop_column("clinics", "short_name")

    op.execute("DROP TYPE IF EXISTS doctor_status")
