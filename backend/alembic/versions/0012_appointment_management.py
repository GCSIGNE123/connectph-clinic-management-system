"""Appointment Management (Phase 11).

Adds:
- `appointments` - the booking record. Check-in is handled at the service
  layer by calling the existing `QueueService.create_queue()` (Phase 5/6),
  which already atomically creates a linked Visit; `appointment.queue_id`/
  `visit_id` are just FKs set once that returns. A partial unique index
  prevents exact double-booking (same doctor+date+start_time) while
  excluding Cancelled/Rescheduled/NoShow rows, which free up the slot.
- `doctor_schedules` (Phase 4) is extended IN PLACE (not duplicated) with
  lunch break / slot duration / daily cap / recurring-override columns -
  see `models/doctor.py` for the rationale.
- `doctor_schedule_blocks` - single-date vacation/blocked days per doctor.
- `appointment_reminders` - architecture-only (no SMS/Email/Push sending).
- `appointment_notes` - free-text notes distinct from reschedule reasons.
- `appointment_history` - domain-specific audit trail for Appointment Details.
- `appointment_counters` - concurrency-safe daily counter for appointment
  numbers, mirroring `queue_counters`.
- `waitlist_entries` - architecture-level "offer next slot on cancellation".

`TimeSlot` is NOT a persisted table - it's computed on demand by
`services/time_slot_service.py`. See docs/DATABASE.md.

All new tables get the legacy-migration mixin fields per spec.

Revision ID: 0012_appointment_management
Revises: 0011_laboratory_management
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_appointment_management"
down_revision: str | None = "0011_laboratory_management"
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
    bind = op.get_bind()

    # Extend the existing `visit_timeline_event_type` enum with this phase's
    # single new event. Standalone autocommit block, same reasoning as 0011.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE visit_timeline_event_type ADD VALUE IF NOT EXISTS 'AppointmentCheckedIn'")

    # --- Extend doctor_schedules (Phase 4) in place ---
    op.add_column("doctor_schedules", sa.Column("lunch_break_start", sa.Time(), nullable=True))
    op.add_column("doctor_schedules", sa.Column("lunch_break_end", sa.Time(), nullable=True))
    op.add_column("doctor_schedules", sa.Column("slot_duration_minutes", sa.Integer(), nullable=False, server_default="15"))
    op.add_column("doctor_schedules", sa.Column("max_patients_per_day", sa.Integer(), nullable=True))
    op.add_column("doctor_schedules", sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("doctor_schedules", sa.Column("effective_from", sa.Date(), nullable=True))
    op.add_column("doctor_schedules", sa.Column("effective_to", sa.Date(), nullable=True))
    op.add_column("doctor_schedules", sa.Column("legacy_id", sa.String(length=64), nullable=True))
    op.add_column("doctor_schedules", sa.Column("legacy_meta", postgresql.JSONB(), nullable=True))
    op.add_column("doctor_schedules", sa.Column("legacy_created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("doctor_schedules", sa.Column("legacy_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("doctor_schedules", sa.Column("migration_batch_id", sa.String(length=64), nullable=True))
    op.add_column("doctor_schedules", sa.Column("migration_source", sa.String(length=100), nullable=True))
    op.add_column("doctor_schedules", sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_doctor_schedules_legacy_id", "doctor_schedules", ["legacy_id"])
    op.create_index("ix_doctor_schedules_migration_batch_id", "doctor_schedules", ["migration_batch_id"])

    # --- doctor_schedule_blocks ---
    doctor_schedule_block_type = postgresql.ENUM("Vacation", "Blocked", name="doctor_schedule_block_type", create_type=False)
    doctor_schedule_block_type.create(bind, checkfirst=True)

    op.create_table(
        "doctor_schedule_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("block_date", sa.Date(), nullable=False),
        sa.Column("block_type", doctor_schedule_block_type, nullable=False, server_default="Blocked"),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("clinic_id", "doctor_id", "block_date", name="uq_doctor_schedule_block_doctor_date"),
    )
    op.create_index("ix_doctor_schedule_blocks_clinic_id", "doctor_schedule_blocks", ["clinic_id"])
    op.create_index("ix_doctor_schedule_blocks_doctor_id", "doctor_schedule_blocks", ["doctor_id"])
    op.create_index("ix_doctor_schedule_blocks_block_date", "doctor_schedule_blocks", ["block_date"])

    # --- appointment_counters ---
    op.create_table(
        "appointment_counters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("counter_date", sa.Date(), nullable=False),
        sa.Column("next_number", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("clinic_id", "counter_date", name="uq_appointment_counter_clinic_date"),
    )
    op.create_index("ix_appointment_counters_clinic_id", "appointment_counters", ["clinic_id"])

    # --- appointments ---
    appointment_type = postgresql.ENUM(
        "NewConsultation", "FollowUp", "AnnualPhysical", "Teleconsultation", "Vaccination",
        "Procedure", "Laboratory", "Custom", name="appointment_type", create_type=False,
    )
    appointment_type.create(bind, checkfirst=True)
    appointment_status = postgresql.ENUM(
        "Booked", "Confirmed", "CheckedIn", "Waiting", "InConsultation", "Completed",
        "Cancelled", "NoShow", "Rescheduled", name="appointment_status", create_type=False,
    )
    appointment_status.create(bind, checkfirst=True)

    op.create_table(
        "appointments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("appointment_number", sa.String(length=30), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("services.id", ondelete="SET NULL"), nullable=True),
        sa.Column("appointment_type", appointment_type, nullable=False, server_default="NewConsultation"),
        sa.Column("appointment_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("status", appointment_status, nullable=False, server_default="Booked"),
        sa.Column("queue_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("queues.id", ondelete="SET NULL"), nullable=True),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visits.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("clinic_id", "appointment_number", name="uq_appointment_clinic_number"),
    )
    op.create_index("ix_appointments_clinic_id", "appointments", ["clinic_id"])
    op.create_index("ix_appointments_branch_id", "appointments", ["branch_id"])
    op.create_index("ix_appointments_patient_id", "appointments", ["patient_id"])
    op.create_index("ix_appointments_doctor_id", "appointments", ["doctor_id"])
    op.create_index("ix_appointments_department_id", "appointments", ["department_id"])
    op.create_index("ix_appointments_service_id", "appointments", ["service_id"])
    op.create_index("ix_appointments_appointment_date", "appointments", ["appointment_date"])
    op.create_index("ix_appointments_queue_id", "appointments", ["queue_id"])
    op.create_index("ix_appointments_visit_id", "appointments", ["visit_id"])
    op.create_index("ix_appointments_legacy_id", "appointments", ["legacy_id"])
    op.create_index("ix_appointments_migration_batch_id", "appointments", ["migration_batch_id"])
    op.create_index("ix_appointments_clinic_doctor_date", "appointments", ["clinic_id", "doctor_id", "appointment_date"])
    op.create_index("ix_appointments_clinic_patient_date", "appointments", ["clinic_id", "patient_id", "appointment_date"])

    # Partial unique index: prevents exact double-booking (same doctor +
    # date + start_time) while excluding terminal non-blocking statuses.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_appointments_doctor_slot_active
        ON appointments (clinic_id, doctor_id, appointment_date, start_time)
        WHERE is_deleted = false AND status NOT IN ('Cancelled', 'Rescheduled', 'NoShow')
        """
    )

    # --- appointment_reminders ---
    reminder_channel = postgresql.ENUM("Email", "SMS", "Push", "WhatsApp", name="appointment_reminder_channel", create_type=False)
    reminder_channel.create(bind, checkfirst=True)
    reminder_status = postgresql.ENUM("Pending", "Sent", "Failed", name="appointment_reminder_status", create_type=False)
    reminder_status.create(bind, checkfirst=True)

    op.create_table(
        "appointment_reminders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", reminder_channel, nullable=False),
        sa.Column("status", reminder_status, nullable=False, server_default="Pending"),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_appointment_reminders_clinic_id", "appointment_reminders", ["clinic_id"])
    op.create_index("ix_appointment_reminders_appointment_id", "appointment_reminders", ["appointment_id"])

    # --- appointment_notes ---
    op.create_table(
        "appointment_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_appointment_notes_clinic_id", "appointment_notes", ["clinic_id"])
    op.create_index("ix_appointment_notes_appointment_id", "appointment_notes", ["appointment_id"])

    # --- appointment_history ---
    history_action = postgresql.ENUM(
        "Created", "Confirmed", "Rescheduled", "Cancelled", "CheckedIn", "Completed", "NoShow",
        name="appointment_history_action", create_type=False,
    )
    history_action.create(bind, checkfirst=True)

    op.create_table(
        "appointment_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", history_action, nullable=False),
        sa.Column("from_value", sa.Text(), nullable=True),
        sa.Column("to_value", sa.Text(), nullable=True),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_appointment_history_clinic_id", "appointment_history", ["clinic_id"])
    op.create_index("ix_appointment_history_appointment_id", "appointment_history", ["appointment_id"])

    # --- waitlist_entries ---
    waitlist_status = postgresql.ENUM("Waiting", "Offered", "Booked", "Expired", "Cancelled", name="waitlist_status", create_type=False)
    waitlist_status.create(bind, checkfirst=True)

    op.create_table(
        "waitlist_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        *_legacy_columns(),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("status", waitlist_status, nullable=False, server_default="Waiting"),
        sa.Column("offered_slot_date", sa.Date(), nullable=True),
        sa.Column("offered_slot_start_time", sa.Time(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_waitlist_entries_clinic_id", "waitlist_entries", ["clinic_id"])
    op.create_index("ix_waitlist_entries_patient_id", "waitlist_entries", ["patient_id"])
    op.create_index("ix_waitlist_entries_doctor_id", "waitlist_entries", ["doctor_id"])


def downgrade() -> None:
    op.drop_index("ix_waitlist_entries_doctor_id", table_name="waitlist_entries")
    op.drop_index("ix_waitlist_entries_patient_id", table_name="waitlist_entries")
    op.drop_index("ix_waitlist_entries_clinic_id", table_name="waitlist_entries")
    op.drop_table("waitlist_entries")
    op.execute("DROP TYPE IF EXISTS waitlist_status")

    op.drop_index("ix_appointment_history_appointment_id", table_name="appointment_history")
    op.drop_index("ix_appointment_history_clinic_id", table_name="appointment_history")
    op.drop_table("appointment_history")
    op.execute("DROP TYPE IF EXISTS appointment_history_action")

    op.drop_index("ix_appointment_notes_appointment_id", table_name="appointment_notes")
    op.drop_index("ix_appointment_notes_clinic_id", table_name="appointment_notes")
    op.drop_table("appointment_notes")

    op.drop_index("ix_appointment_reminders_appointment_id", table_name="appointment_reminders")
    op.drop_index("ix_appointment_reminders_clinic_id", table_name="appointment_reminders")
    op.drop_table("appointment_reminders")
    op.execute("DROP TYPE IF EXISTS appointment_reminder_status")
    op.execute("DROP TYPE IF EXISTS appointment_reminder_channel")

    op.execute("DROP INDEX IF EXISTS uq_appointments_doctor_slot_active")
    op.drop_index("ix_appointments_clinic_patient_date", table_name="appointments")
    op.drop_index("ix_appointments_clinic_doctor_date", table_name="appointments")
    op.drop_index("ix_appointments_migration_batch_id", table_name="appointments")
    op.drop_index("ix_appointments_legacy_id", table_name="appointments")
    op.drop_index("ix_appointments_visit_id", table_name="appointments")
    op.drop_index("ix_appointments_queue_id", table_name="appointments")
    op.drop_index("ix_appointments_appointment_date", table_name="appointments")
    op.drop_index("ix_appointments_service_id", table_name="appointments")
    op.drop_index("ix_appointments_department_id", table_name="appointments")
    op.drop_index("ix_appointments_doctor_id", table_name="appointments")
    op.drop_index("ix_appointments_patient_id", table_name="appointments")
    op.drop_index("ix_appointments_branch_id", table_name="appointments")
    op.drop_index("ix_appointments_clinic_id", table_name="appointments")
    op.drop_table("appointments")
    op.execute("DROP TYPE IF EXISTS appointment_status")
    op.execute("DROP TYPE IF EXISTS appointment_type")

    op.drop_index("ix_appointment_counters_clinic_id", table_name="appointment_counters")
    op.drop_table("appointment_counters")

    op.drop_index("ix_doctor_schedule_blocks_block_date", table_name="doctor_schedule_blocks")
    op.drop_index("ix_doctor_schedule_blocks_doctor_id", table_name="doctor_schedule_blocks")
    op.drop_index("ix_doctor_schedule_blocks_clinic_id", table_name="doctor_schedule_blocks")
    op.drop_table("doctor_schedule_blocks")
    op.execute("DROP TYPE IF EXISTS doctor_schedule_block_type")

    op.drop_index("ix_doctor_schedules_migration_batch_id", table_name="doctor_schedules")
    op.drop_index("ix_doctor_schedules_legacy_id", table_name="doctor_schedules")
    op.drop_column("doctor_schedules", "imported_at")
    op.drop_column("doctor_schedules", "migration_source")
    op.drop_column("doctor_schedules", "migration_batch_id")
    op.drop_column("doctor_schedules", "legacy_updated_at")
    op.drop_column("doctor_schedules", "legacy_created_at")
    op.drop_column("doctor_schedules", "legacy_meta")
    op.drop_column("doctor_schedules", "legacy_id")
    op.drop_column("doctor_schedules", "effective_to")
    op.drop_column("doctor_schedules", "effective_from")
    op.drop_column("doctor_schedules", "is_recurring")
    op.drop_column("doctor_schedules", "max_patients_per_day")
    op.drop_column("doctor_schedules", "slot_duration_minutes")
    op.drop_column("doctor_schedules", "lunch_break_end")
    op.drop_column("doctor_schedules", "lunch_break_start")
