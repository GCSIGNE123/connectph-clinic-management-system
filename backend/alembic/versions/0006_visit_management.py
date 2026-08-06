"""Visit (Encounter) Management (Phase 6).

Creates `visits`, `visit_timeline_events`, `visit_counters`. Adds a nullable
`queues.visit_id` FK back to `visits`.

Creation-order decision (documented per Phase 6 spec): creating a Queue
ticket (`POST /queues`) transactionally creates its linked Visit internally
(`VisitService.create_visit_for_queue`, called from
`QueueService.create_queue`), then `queue.visit_id` is set on the same
queue row. Both `visits.queue_id` and `queues.visit_id` are nullable FKs
to avoid a chicken-and-egg constraint: the visits table is created first
(referencing the pre-existing `queues` table via a nullable FK), then
`queues.visit_id` is added as a second, equally nullable, additive column.

Revision ID: 0006_visit_management
Revises: 0005_reception_queue
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_visit_management"
down_revision: str | None = "0005_reception_queue"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    visit_type_enum = postgresql.ENUM(
        "WalkIn", "Appointment", "FollowUp", "Emergency", "Teleconsultation", "HomeService",
        name="visit_type", create_type=False,
    )
    visit_type_enum.create(bind, checkfirst=True)
    visit_status_enum = postgresql.ENUM(
        "Registered", "Waiting", "Called", "InConsultation", "Completed", "Cancelled", "NoShow",
        name="visit_status", create_type=False,
    )
    visit_status_enum.create(bind, checkfirst=True)
    visit_priority_enum = postgresql.ENUM(
        "Normal", "SeniorCitizen", "PWD", "Pregnant", "Emergency", "VIP",
        name="visit_priority", create_type=False,
    )
    visit_priority_enum.create(bind, checkfirst=True)
    visit_timeline_event_type_enum = postgresql.ENUM(
        "Registered", "CheckedIn", "Queued", "Called", "ConsultationStarted", "ConsultationFinished",
        "CheckedOut", "StatusChanged", "Cancelled", "Note",
        name="visit_timeline_event_type", create_type=False,
    )
    visit_timeline_event_type_enum.create(bind, checkfirst=True)

    # --- visits ---
    op.create_table(
        "visits",
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
        sa.Column("queue_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("queues.id", ondelete="SET NULL"), nullable=True),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("services.id", ondelete="SET NULL"), nullable=True),
        sa.Column("visit_number", sa.String(length=30), nullable=False),
        sa.Column("visit_date", sa.Date(), nullable=False),
        sa.Column("visit_type", visit_type_enum, nullable=False, server_default="WalkIn"),
        sa.Column("status", visit_status_enum, nullable=False, server_default="Registered"),
        sa.Column("priority", visit_priority_enum, nullable=False, server_default="Normal"),
        sa.Column("arrival_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_in_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("called_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consultation_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consultation_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_out_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("clinic_id", "visit_number", name="uq_visit_clinic_visit_number"),
    )
    op.create_index("ix_visits_clinic_id", "visits", ["clinic_id"])
    op.create_index("ix_visits_branch_id", "visits", ["branch_id"])
    op.create_index("ix_visits_patient_id", "visits", ["patient_id"])
    op.create_index("ix_visits_queue_id", "visits", ["queue_id"])
    op.create_index("ix_visits_doctor_id", "visits", ["doctor_id"])
    op.create_index("ix_visits_department_id", "visits", ["department_id"])
    op.create_index("ix_visits_service_id", "visits", ["service_id"])
    op.create_index("ix_visits_status", "visits", ["status"])
    op.create_index("ix_visits_visit_date", "visits", ["visit_date"])
    op.create_index("ix_visits_legacy_id", "visits", ["legacy_id"])
    op.create_index("ix_visits_migration_batch_id", "visits", ["migration_batch_id"])
    op.create_index("ix_visits_clinic_branch_date_status", "visits", ["clinic_id", "branch_id", "visit_date", "status"])
    op.create_index("ix_visits_clinic_date_patient", "visits", ["clinic_id", "visit_date", "patient_id"])

    # --- queues.visit_id (additive, nullable - backward compatible) ---
    op.add_column(
        "queues",
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visits.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_queues_visit_id", "queues", ["visit_id"])

    # --- visit_timeline_events ---
    op.create_table(
        "visit_timeline_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", visit_timeline_event_type_enum, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("event_metadata", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_visit_timeline_events_clinic_id", "visit_timeline_events", ["clinic_id"])
    op.create_index("ix_visit_timeline_events_visit_id", "visit_timeline_events", ["visit_id"])

    # --- visit_counters ---
    op.create_table(
        "visit_counters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("counter_date", sa.Date(), nullable=False),
        sa.Column("next_number", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("clinic_id", "branch_id", "counter_date", name="uq_visit_counter_clinic_branch_date"),
    )
    op.create_index("ix_visit_counters_clinic_id", "visit_counters", ["clinic_id"])
    op.create_index("ix_visit_counters_branch_id", "visit_counters", ["branch_id"])


def downgrade() -> None:
    op.drop_index("ix_visit_counters_branch_id", table_name="visit_counters")
    op.drop_index("ix_visit_counters_clinic_id", table_name="visit_counters")
    op.drop_table("visit_counters")

    op.drop_index("ix_visit_timeline_events_visit_id", table_name="visit_timeline_events")
    op.drop_index("ix_visit_timeline_events_clinic_id", table_name="visit_timeline_events")
    op.drop_table("visit_timeline_events")

    op.drop_index("ix_queues_visit_id", table_name="queues")
    op.drop_column("queues", "visit_id")

    op.drop_index("ix_visits_clinic_date_patient", table_name="visits")
    op.drop_index("ix_visits_clinic_branch_date_status", table_name="visits")
    op.drop_index("ix_visits_migration_batch_id", table_name="visits")
    op.drop_index("ix_visits_legacy_id", table_name="visits")
    op.drop_index("ix_visits_visit_date", table_name="visits")
    op.drop_index("ix_visits_status", table_name="visits")
    op.drop_index("ix_visits_service_id", table_name="visits")
    op.drop_index("ix_visits_department_id", table_name="visits")
    op.drop_index("ix_visits_doctor_id", table_name="visits")
    op.drop_index("ix_visits_queue_id", table_name="visits")
    op.drop_index("ix_visits_patient_id", table_name="visits")
    op.drop_index("ix_visits_branch_id", table_name="visits")
    op.drop_index("ix_visits_clinic_id", table_name="visits")
    op.drop_table("visits")

    op.execute("DROP TYPE IF EXISTS visit_timeline_event_type")
    op.execute("DROP TYPE IF EXISTS visit_priority")
    op.execute("DROP TYPE IF EXISTS visit_status")
    op.execute("DROP TYPE IF EXISTS visit_type")
