"""Reception & Queue Management (Phase 5).

Extends the shared `LegacyMixin` (clinics, patients, users - the three
existing tables that use it) with additive nullable provenance columns.
Adds `queue_settings.department_id` (nullable per-department override).
Creates `queues`, `queue_status_history`, `queue_counters`.

Revision ID: 0005_reception_queue
Revises: 0004_clinic_configuration
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_reception_queue"
down_revision: str | None = "0004_clinic_configuration"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

LEGACY_MIXIN_TABLES = ["clinics", "patients", "users"]


def upgrade() -> None:
    bind = op.get_bind()

    # --- Extend LegacyMixin on all tables that currently use it ---
    for table in LEGACY_MIXIN_TABLES:
        op.add_column(table, sa.Column("legacy_created_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column("legacy_updated_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column("migration_batch_id", sa.String(length=64), nullable=True))
        op.add_column(table, sa.Column("migration_source", sa.String(length=100), nullable=True))
        op.add_column(table, sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True))
        op.create_index(f"ix_{table}_migration_batch_id", table, ["migration_batch_id"])

    # --- queue_settings: nullable per-department override ---
    op.add_column(
        "queue_settings",
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departments.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ix_queue_settings_department_id", "queue_settings", ["department_id"])
    op.drop_constraint("uq_queue_setting_clinic_branch", "queue_settings", type_="unique")
    op.create_unique_constraint(
        "uq_queue_setting_clinic_branch_department", "queue_settings", ["clinic_id", "branch_id", "department_id"]
    )

    queue_priority_enum = postgresql.ENUM(
        "Normal", "SeniorCitizen", "PWD", "Pregnant", "Emergency", "VIP", name="queue_priority", create_type=False
    )
    queue_priority_enum.create(bind, checkfirst=True)
    queue_status_enum = postgresql.ENUM(
        "Waiting", "Called", "Serving", "Completed", "Skipped", "Cancelled", "NoShow",
        name="queue_status", create_type=False,
    )
    queue_status_enum.create(bind, checkfirst=True)

    # --- queues ---
    op.create_table(
        "queues",
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
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("services.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("queue_number", sa.String(length=20), nullable=False),
        sa.Column("queue_prefix", sa.String(length=10), nullable=False),
        sa.Column("queue_date", sa.Date(), nullable=False),
        sa.Column("priority", queue_priority_enum, nullable=False, server_default="Normal"),
        sa.Column("status", queue_status_enum, nullable=False, server_default="Waiting"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("called_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("serving_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint(
            "clinic_id", "branch_id", "queue_date", "queue_prefix", "queue_number",
            name="uq_queue_clinic_branch_date_prefix_number",
        ),
    )
    op.create_index("ix_queues_clinic_id", "queues", ["clinic_id"])
    op.create_index("ix_queues_branch_id", "queues", ["branch_id"])
    op.create_index("ix_queues_patient_id", "queues", ["patient_id"])
    op.create_index("ix_queues_department_id", "queues", ["department_id"])
    op.create_index("ix_queues_doctor_id", "queues", ["doctor_id"])
    op.create_index("ix_queues_service_id", "queues", ["service_id"])
    op.create_index("ix_queues_status", "queues", ["status"])
    op.create_index("ix_queues_queue_date", "queues", ["queue_date"])
    op.create_index("ix_queues_legacy_id", "queues", ["legacy_id"])
    op.create_index("ix_queues_migration_batch_id", "queues", ["migration_batch_id"])
    op.create_index(
        "ix_queues_clinic_branch_date_status", "queues", ["clinic_id", "branch_id", "queue_date", "status"]
    )
    op.create_index("ix_queues_clinic_date_patient", "queues", ["clinic_id", "queue_date", "patient_id"])

    # Partial unique index: at most one *active* (Waiting/Called/Serving)
    # queue ticket per (clinic, patient, department, day). Postgres partial
    # unique indexes can't be expressed via a plain UniqueConstraint, hence
    # raw DDL here.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_queues_active_patient_department_day
        ON queues (clinic_id, patient_id, department_id, queue_date)
        WHERE is_deleted = false AND status IN ('Waiting', 'Called', 'Serving')
        """
    )

    # --- queue_status_history ---
    op.create_table(
        "queue_status_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("queue_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("queues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status", queue_status_enum, nullable=True),
        sa.Column("to_status", queue_status_enum, nullable=False),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_queue_status_history_clinic_id", "queue_status_history", ["clinic_id"])
    op.create_index("ix_queue_status_history_queue_id", "queue_status_history", ["queue_id"])

    # --- queue_counters ---
    op.create_table(
        "queue_counters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("queue_prefix", sa.String(length=10), nullable=False),
        sa.Column("counter_date", sa.Date(), nullable=False),
        sa.Column("next_number", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint(
            "clinic_id", "branch_id", "queue_prefix", "counter_date",
            name="uq_queue_counter_clinic_branch_prefix_date",
        ),
    )
    op.create_index("ix_queue_counters_clinic_id", "queue_counters", ["clinic_id"])
    op.create_index("ix_queue_counters_branch_id", "queue_counters", ["branch_id"])


def downgrade() -> None:
    op.drop_index("ix_queue_counters_branch_id", table_name="queue_counters")
    op.drop_index("ix_queue_counters_clinic_id", table_name="queue_counters")
    op.drop_table("queue_counters")

    op.drop_index("ix_queue_status_history_queue_id", table_name="queue_status_history")
    op.drop_index("ix_queue_status_history_clinic_id", table_name="queue_status_history")
    op.drop_table("queue_status_history")

    op.execute("DROP INDEX IF EXISTS uq_queues_active_patient_department_day")
    op.drop_index("ix_queues_clinic_date_patient", table_name="queues")
    op.drop_index("ix_queues_clinic_branch_date_status", table_name="queues")
    op.drop_index("ix_queues_migration_batch_id", table_name="queues")
    op.drop_index("ix_queues_legacy_id", table_name="queues")
    op.drop_index("ix_queues_queue_date", table_name="queues")
    op.drop_index("ix_queues_status", table_name="queues")
    op.drop_index("ix_queues_service_id", table_name="queues")
    op.drop_index("ix_queues_doctor_id", table_name="queues")
    op.drop_index("ix_queues_department_id", table_name="queues")
    op.drop_index("ix_queues_patient_id", table_name="queues")
    op.drop_index("ix_queues_branch_id", table_name="queues")
    op.drop_index("ix_queues_clinic_id", table_name="queues")
    op.drop_table("queues")

    op.execute("DROP TYPE IF EXISTS queue_status")
    op.execute("DROP TYPE IF EXISTS queue_priority")

    op.drop_constraint("uq_queue_setting_clinic_branch_department", "queue_settings", type_="unique")
    op.create_unique_constraint("uq_queue_setting_clinic_branch", "queue_settings", ["clinic_id", "branch_id"])
    op.drop_index("ix_queue_settings_department_id", table_name="queue_settings")
    op.drop_column("queue_settings", "department_id")

    for table in reversed(LEGACY_MIXIN_TABLES):
        op.drop_index(f"ix_{table}_migration_batch_id", table_name=table)
        op.drop_column(table, "imported_at")
        op.drop_column(table, "migration_source")
        op.drop_column(table, "migration_batch_id")
        op.drop_column(table, "legacy_updated_at")
        op.drop_column(table, "legacy_created_at")
