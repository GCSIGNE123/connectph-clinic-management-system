"""Appointment Management (Phase 11).

`Appointment` is the booking record. Checking an appointment in reuses the
existing Phase 5/6 `QueueService.create_queue()` flow (which already
atomically creates a linked `Visit`) rather than reimplementing queue/visit
creation - see `services/appointment_service.py::check_in_appointment`.

`TimeSlot` (the "available slots" concept from the spec) is deliberately
NOT a persisted table here - it is computed on demand by
`services/time_slot_service.py` from `DoctorSchedule` + existing
`appointments` + `holidays` + `DoctorScheduleBlock` rows, and returned as a
plain schema (`schemas/appointment.py::TimeSlotOut`). Persisting slots would
go stale the instant the source data changes (a schedule edit, a new
booking, a same-day block) and there is no feature yet (e.g. a slot-hold
reservation) that requires a durable slot row. See docs/DATABASE.md.
"""

import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, Time as SATime, UniqueConstraint, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class AppointmentType(str, enum.Enum):
    NEW_CONSULTATION = "NewConsultation"
    FOLLOW_UP = "FollowUp"
    ANNUAL_PHYSICAL = "AnnualPhysical"
    TELECONSULTATION = "Teleconsultation"
    VACCINATION = "Vaccination"
    PROCEDURE = "Procedure"
    LABORATORY = "Laboratory"
    CUSTOM = "Custom"


class AppointmentStatus(str, enum.Enum):
    BOOKED = "Booked"
    CONFIRMED = "Confirmed"
    CHECKED_IN = "CheckedIn"
    WAITING = "Waiting"
    IN_CONSULTATION = "InConsultation"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    NO_SHOW = "NoShow"
    RESCHEDULED = "Rescheduled"


# Terminal statuses are excluded from the double-booking uniqueness check
# (a cancelled/rescheduled/no-show slot frees up the doctor's time).
NON_BLOCKING_APPOINTMENT_STATUSES = (
    AppointmentStatus.CANCELLED,
    AppointmentStatus.RESCHEDULED,
    AppointmentStatus.NO_SHOW,
)

APPOINTMENT_STATUS_TRANSITIONS: dict[AppointmentStatus, set[AppointmentStatus]] = {
    AppointmentStatus.BOOKED: {AppointmentStatus.CONFIRMED, AppointmentStatus.CHECKED_IN, AppointmentStatus.CANCELLED, AppointmentStatus.RESCHEDULED, AppointmentStatus.NO_SHOW},
    AppointmentStatus.CONFIRMED: {AppointmentStatus.CHECKED_IN, AppointmentStatus.CANCELLED, AppointmentStatus.RESCHEDULED, AppointmentStatus.NO_SHOW},
    AppointmentStatus.CHECKED_IN: {AppointmentStatus.WAITING, AppointmentStatus.IN_CONSULTATION, AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED},
    AppointmentStatus.WAITING: {AppointmentStatus.IN_CONSULTATION, AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED},
    AppointmentStatus.IN_CONSULTATION: {AppointmentStatus.COMPLETED},
    AppointmentStatus.COMPLETED: set(),
    AppointmentStatus.CANCELLED: set(),
    AppointmentStatus.NO_SHOW: {AppointmentStatus.BOOKED},
    AppointmentStatus.RESCHEDULED: set(),
}


class AppointmentBookingSource(str, enum.Enum):
    STAFF = "Staff"
    PATIENT = "Patient"


class DoctorScheduleBlockType(str, enum.Enum):
    VACATION = "Vacation"
    BLOCKED = "Blocked"


class DoctorScheduleBlock(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, LegacyMixin, Base):
    """A single-date vacation/blocked-out day for a doctor - no appointments
    may be booked or offered as an available slot on this date."""

    __tablename__ = "doctor_schedule_blocks"

    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    block_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    block_type: Mapped[DoctorScheduleBlockType] = mapped_column(
        SAEnum(DoctorScheduleBlockType, name="doctor_schedule_block_type", values_callable=_enum_values),
        nullable=False, default=DoctorScheduleBlockType.BLOCKED, server_default=DoctorScheduleBlockType.BLOCKED.value,
    )
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    doctor: Mapped["Doctor"] = relationship()

    __table_args__ = (
        UniqueConstraint("clinic_id", "doctor_id", "block_date", name="uq_doctor_schedule_block_doctor_date"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DoctorScheduleBlock doctor_id={self.doctor_id} date={self.block_date} type={self.block_type!r}>"


class AppointmentCounter(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Concurrency-safe daily counter backing `AppointmentNumberGenerator`,
    mirroring `QueueCounter`."""

    __tablename__ = "appointment_counters"

    counter_date: Mapped[date] = mapped_column(Date, nullable=False)
    next_number: Mapped[int] = mapped_column(default=1, server_default="1")

    __table_args__ = (
        UniqueConstraint("clinic_id", "counter_date", name="uq_appointment_counter_clinic_date"),
    )


class Appointment(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "appointments"

    appointment_number: Mapped[str] = mapped_column(String(30), nullable=False)

    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="SET NULL"), nullable=True, index=True
    )

    appointment_type: Mapped[AppointmentType] = mapped_column(
        SAEnum(AppointmentType, name="appointment_type", values_callable=_enum_values),
        nullable=False, default=AppointmentType.NEW_CONSULTATION,
    )
    appointment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(SATime, nullable=False)
    end_time: Mapped[time] = mapped_column(SATime, nullable=False)

    status: Mapped[AppointmentStatus] = mapped_column(
        SAEnum(AppointmentStatus, name="appointment_status", values_callable=_enum_values),
        nullable=False, default=AppointmentStatus.BOOKED, server_default=AppointmentStatus.BOOKED.value, index=True,
    )

    # Phase 11: set by `AppointmentService.check_in_appointment`, which calls
    # into the existing `QueueService.create_queue()` (Phase 5/6) so a real
    # Queue ticket + linked Visit are created the same way a walk-in would.
    queue_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("queues.id", ondelete="SET NULL"), nullable=True, index=True
    )
    visit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id", ondelete="SET NULL"), nullable=True, index=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Phase 19: distinguishes patient self-service bookings from
    # staff-created ones. Same table, same engine - just a provenance flag.
    booking_source: Mapped[AppointmentBookingSource] = mapped_column(
        SAEnum(AppointmentBookingSource, name="appointment_booking_source", values_callable=_enum_values),
        nullable=False, default=AppointmentBookingSource.STAFF, server_default=AppointmentBookingSource.STAFF.value, index=True,
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    patient: Mapped["Patient"] = relationship()
    doctor: Mapped["Doctor"] = relationship()
    department: Mapped["Department | None"] = relationship()
    service: Mapped["ClinicService | None"] = relationship()
    branch: Mapped["Branch"] = relationship()
    queue: Mapped["Queue | None"] = relationship(foreign_keys=[queue_id])
    visit: Mapped["Visit | None"] = relationship(foreign_keys=[visit_id])

    __table_args__ = (
        UniqueConstraint("clinic_id", "appointment_number", name="uq_appointment_clinic_number"),
        Index("ix_appointments_clinic_doctor_date", "clinic_id", "doctor_id", "appointment_date"),
        Index("ix_appointments_clinic_patient_date", "clinic_id", "patient_id", "appointment_date"),
        # Partial unique index preventing exact double-booking (same doctor +
        # date + start_time), excluding terminal non-blocking statuses. This
        # is the REAL DB-level race-condition guarantee for concurrent
        # bookings (see `services/appointment_service.py`). It is created in
        # production/dev via raw SQL in migration 0012
        # (`uq_appointments_doctor_slot_active`) since Postgres partial-index
        # `WHERE` syntax isn't expressible via `UniqueConstraint`. It is ALSO
        # declared here (same name, `Index(..., postgresql_where=...)` is
        # supported by SQLAlchemy) so that `Base.metadata.create_all()` -
        # which is how the test database schema is built (see
        # `app/tests/conftest.py`'s `engine` fixture) - creates it too.
        # Without this, tests would run against a schema silently missing
        # the constraint they're asserting on (found while writing Phase
        # 19's concurrency test - see docs/BUGS.md).
        Index(
            "uq_appointments_doctor_slot_active", "clinic_id", "doctor_id", "appointment_date", "start_time",
            unique=True,
            postgresql_where=text("is_deleted = false AND status NOT IN ('Cancelled', 'Rescheduled', 'NoShow')"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Appointment id={self.id} number={self.appointment_number!r} status={self.status!r}>"


class AppointmentReminderChannel(str, enum.Enum):
    EMAIL = "Email"
    SMS = "SMS"
    PUSH = "Push"
    WHATSAPP = "WhatsApp"


class AppointmentReminderStatus(str, enum.Enum):
    PENDING = "Pending"
    SENT = "Sent"
    FAILED = "Failed"


class AppointmentReminder(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, LegacyMixin, Base):
    """Architecture-only: records that a reminder *should* go out. No actual
    SMS/Email/Push sending is implemented in this phase - a future
    notification-worker phase would poll `status=Pending` rows here."""

    __tablename__ = "appointment_reminders"

    appointment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[AppointmentReminderChannel] = mapped_column(
        SAEnum(AppointmentReminderChannel, name="appointment_reminder_channel", values_callable=_enum_values), nullable=False
    )
    status: Mapped[AppointmentReminderStatus] = mapped_column(
        SAEnum(AppointmentReminderStatus, name="appointment_reminder_status", values_callable=_enum_values),
        nullable=False, default=AppointmentReminderStatus.PENDING, server_default=AppointmentReminderStatus.PENDING.value,
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    appointment: Mapped["Appointment"] = relationship()


class AppointmentNote(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "appointment_notes"

    appointment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    appointment: Mapped["Appointment"] = relationship()


class AppointmentHistoryAction(str, enum.Enum):
    CREATED = "Created"
    CONFIRMED = "Confirmed"
    RESCHEDULED = "Rescheduled"
    CANCELLED = "Cancelled"
    CHECKED_IN = "CheckedIn"
    COMPLETED = "Completed"
    NO_SHOW = "NoShow"


class AppointmentHistory(UUIDPrimaryKeyMixin, TenantMixin, LegacyMixin, Base):
    """Domain-specific audit trail for the Appointment Details page, mirroring
    `queue_status_history`/`visit_timeline_events`. Also mirrored into the
    generic `audit_logs` table via `AuditService` from the service layer."""

    __tablename__ = "appointment_history"

    appointment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[AppointmentHistoryAction] = mapped_column(
        SAEnum(AppointmentHistoryAction, name="appointment_history_action", values_callable=_enum_values), nullable=False
    )
    from_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    appointment: Mapped["Appointment"] = relationship()


class WaitlistStatus(str, enum.Enum):
    WAITING = "Waiting"
    OFFERED = "Offered"
    BOOKED = "Booked"
    EXPIRED = "Expired"
    CANCELLED = "Cancelled"


class WaitlistEntry(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    """When a doctor's day is fully booked, a patient can be waitlisted for
    that doctor/date-range. On cancellation of any appointment for that
    doctor, `WaitlistService.offer_next_slot` flips the oldest matching
    entry to `Offered` with the freed slot recorded - a real, queryable
    state change that a future notification phase would consume to alert
    the patient (actual sending is out of scope for this phase)."""

    __tablename__ = "waitlist_entries"

    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    doctor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[WaitlistStatus] = mapped_column(
        SAEnum(WaitlistStatus, name="waitlist_status", values_callable=_enum_values),
        nullable=False, default=WaitlistStatus.WAITING, server_default=WaitlistStatus.WAITING.value,
    )
    offered_slot_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    offered_slot_start_time: Mapped[time | None] = mapped_column(SATime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    patient: Mapped["Patient"] = relationship()
    doctor: Mapped["Doctor"] = relationship()
    branch: Mapped["Branch"] = relationship()
