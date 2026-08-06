"""Phase 19: Patient Self-Service Appointment Booking

Adds `booking_source` to `appointments` (Staff / Patient) so reception can
distinguish patient-initiated bookings from staff-initiated ones in search
results and reporting. No new tables: patient-booked appointments are plain
rows in the existing `appointments` table (see `models/appointment.py`),
created via the SAME `AppointmentService`/`AppointmentRepository`/
`TimeSlotService` staff booking already uses.

The double-booking race-condition guarantee already exists as of Phase 11
(migration 0012's partial unique index `uq_appointments_doctor_slot_active`
on (clinic_id, doctor_id, appointment_date, start_time) WHERE is_deleted =
false AND status NOT IN ('Cancelled','Rescheduled','NoShow')). This
migration does not touch that index; it only makes the service layer
translate the resulting Postgres unique-violation into a clean 409 (see
`services/appointment_service.py::create_appointment`), which previously
would have surfaced as a raw 500 if two staff requests ever raced (Phase 11
did not have a concurrent-request test to catch this).

Revision ID: 0018_patient_appointment_booking
Revises: 0017_patient_portal
Create Date: 2026-07-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0018_patient_appointment_booking"
down_revision: Union[str, None] = "0017_patient_portal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    booking_source = sa.Enum("Staff", "Patient", name="appointment_booking_source")
    booking_source.create(bind, checkfirst=True)
    op.add_column(
        "appointments",
        sa.Column("booking_source", booking_source, nullable=False, server_default="Staff"),
    )
    op.create_index("ix_appointments_booking_source", "appointments", ["booking_source"])


def downgrade() -> None:
    op.drop_index("ix_appointments_booking_source", table_name="appointments")
    op.drop_column("appointments", "booking_source")
    sa.Enum(name="appointment_booking_source").drop(op.get_bind(), checkfirst=True)
