"""Reception & Queue Management (Phase 5) - execution records.

`Queue` is an actual daily queue ticket (as opposed to `QueueSetting`, which
is pure configuration). `QueueStatusHistory` is an append-only audit trail of
status transitions. `QueueCounter` backs `QueueNumberGenerator` - a dedicated
table (rather than reusing the `system_settings` JSONB-counter pattern from
`PatientNumberGenerator`/`DoctorCodeGenerator`) because the counter here has
a composite natural key (clinic, branch, prefix, date) that resets daily,
which is awkward to express as a single JSONB blob key.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import (
    LegacyMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class QueuePriority(str, enum.Enum):
    NORMAL = "Normal"
    SENIOR_CITIZEN = "SeniorCitizen"
    PWD = "PWD"
    PREGNANT = "Pregnant"
    EMERGENCY = "Emergency"
    VIP = "VIP"


class QueueStatus(str, enum.Enum):
    WAITING = "Waiting"
    CALLED = "Called"
    SERVING = "Serving"
    COMPLETED = "Completed"
    SKIPPED = "Skipped"
    CANCELLED = "Cancelled"
    NO_SHOW = "NoShow"


class VisitClassification(str, enum.Enum):
    """Phase 2.7 (YAKAP Patient Classification): the PER-ENCOUNTER
    classification of this specific queue ticket - deliberately NOT a queue
    prefix (A/B/L/R numbering is completely unaffected) and NOT the same
    thing as `Patient.is_yakap_beneficiary` (the patient's standing
    beneficiary status). Pre-filled from the patient's beneficiary flag at
    ticket-creation time but independently editable - a YAKAP beneficiary's
    visit is not necessarily always processed as a YAKAP encounter."""

    YAKAP = "Yakap"
    REGULAR = "Regular"


# Statuses considered "active" for duplicate-detection and live-dashboard purposes.
ACTIVE_QUEUE_STATUSES = (QueueStatus.WAITING, QueueStatus.CALLED, QueueStatus.SERVING)

# Legal forward transitions for a queue ticket. Cancel is allowed from any
# non-terminal state; terminal states (Completed/Skipped/Cancelled/NoShow)
# accept no further transitions.
QUEUE_STATUS_TRANSITIONS: dict[QueueStatus, set[QueueStatus]] = {
    QueueStatus.WAITING: {QueueStatus.CALLED, QueueStatus.CANCELLED, QueueStatus.SKIPPED, QueueStatus.NO_SHOW},
    # Called -> Completed (direct, no Serving in between) is legal because a
    # Laboratory-only queue ticket is Called but never enters a doctor
    # consultation - there is no "Serving" moment for it to pass through.
    # LaboratoryService syncs a ticket straight to Completed when its
    # LaboratoryOrder is Released - see laboratory_service.py's
    # `_sync_queue_on_release`. The Doctor/Consultation path is unaffected:
    # it always reaches Completed via Serving already (IN_CONSULTATION maps
    # to Serving before COMPLETED does - see doctor_workspace_service.py's
    # `_VISIT_TO_QUEUE_STATUS`), so this is a purely additive extra edge,
    # not a change to how consultation tickets already transition.
    QueueStatus.CALLED: {
        QueueStatus.SERVING, QueueStatus.SKIPPED, QueueStatus.NO_SHOW, QueueStatus.CANCELLED,
        QueueStatus.WAITING, QueueStatus.COMPLETED,
    },
    QueueStatus.SERVING: {QueueStatus.COMPLETED, QueueStatus.CANCELLED},
    QueueStatus.COMPLETED: set(),
    QueueStatus.SKIPPED: {QueueStatus.WAITING},
    QueueStatus.CANCELLED: set(),
    QueueStatus.NO_SHOW: {QueueStatus.WAITING},
}


class Queue(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    """A single queue ticket for a patient's visit on a given day."""

    __tablename__ = "queues"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Phase 6: set once queue creation transactionally creates the linked
    # Visit (see `services/queue_service.py::create_queue` and
    # `services/visit_service.py::create_visit_for_queue`).
    visit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id", ondelete="SET NULL"), nullable=True, index=True
    )

    queue_number: Mapped[str] = mapped_column(String(20), nullable=False)
    queue_prefix: Mapped[str] = mapped_column(String(10), nullable=False)
    queue_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    priority: Mapped[QueuePriority] = mapped_column(
        SAEnum(QueuePriority, name="queue_priority", values_callable=_enum_values),
        nullable=False,
        default=QueuePriority.NORMAL,
        server_default=QueuePriority.NORMAL.value,
    )
    status: Mapped[QueueStatus] = mapped_column(
        SAEnum(QueueStatus, name="queue_status", values_callable=_enum_values),
        nullable=False,
        default=QueueStatus.WAITING,
        server_default=QueueStatus.WAITING.value,
        index=True,
    )
    visit_classification: Mapped[VisitClassification] = mapped_column(
        SAEnum(VisitClassification, name="visit_classification", values_callable=_enum_values),
        nullable=False,
        default=VisitClassification.REGULAR,
        server_default=VisitClassification.REGULAR.value,
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    serving_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    patient: Mapped["Patient"] = relationship()
    department: Mapped["Department"] = relationship()
    doctor: Mapped["Doctor | None"] = relationship()
    service: Mapped["ClinicService"] = relationship()
    branch: Mapped["Branch"] = relationship()
    visit: Mapped["Visit | None"] = relationship(foreign_keys=[visit_id])

    __table_args__ = (
        Index("ix_queues_clinic_branch_date_status", "clinic_id", "branch_id", "queue_date", "status"),
        Index("ix_queues_clinic_date_patient", "clinic_id", "queue_date", "patient_id"),
        # Postgres partial unique index (created directly in the migration)
        # prevents duplicate *active* tickets for the same patient+department
        # on the same day; see 0005_reception_queue.py.
        UniqueConstraint(
            "clinic_id", "branch_id", "queue_date", "queue_prefix", "queue_number",
            name="uq_queue_clinic_branch_date_prefix_number",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Queue id={self.id} queue_number={self.queue_number!r} status={self.status!r}>"


class QueueStatusHistory(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Append-only log of status transitions for a queue ticket."""

    __tablename__ = "queue_status_history"

    queue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("queues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[QueueStatus | None] = mapped_column(
        SAEnum(QueueStatus, name="queue_status", values_callable=_enum_values, create_type=False), nullable=True
    )
    to_status: Mapped[QueueStatus] = mapped_column(
        SAEnum(QueueStatus, name="queue_status", values_callable=_enum_values, create_type=False), nullable=False
    )
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<QueueStatusHistory queue_id={self.queue_id} to_status={self.to_status!r}>"


class QueueCounter(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Concurrency-safe daily counter backing `QueueNumberGenerator`.

    One row per (clinic, branch, queue_prefix, counter_date). Selected with
    `SELECT ... FOR UPDATE` inside the caller's transaction so concurrent
    queue-creation requests for the same bucket serialize on this row.
    """

    __tablename__ = "queue_counters"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    queue_prefix: Mapped[str] = mapped_column(String(10), nullable=False)
    counter_date: Mapped[date] = mapped_column(Date, nullable=False)
    next_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    __table_args__ = (
        UniqueConstraint(
            "clinic_id", "branch_id", "queue_prefix", "counter_date",
            name="uq_queue_counter_clinic_branch_prefix_date",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<QueueCounter clinic_id={self.clinic_id} prefix={self.queue_prefix!r} next={self.next_number}>"
