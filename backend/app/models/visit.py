"""Visit (Encounter) Management (Phase 6).

`Visit` is the central transaction every future clinical/billing module
hangs off of. A Visit is created automatically as part of `Queue` creation
(see `services/queue_service.py::create_queue` and
`services/visit_service.py::create_visit_for_queue`) - the receptionist
generates a queue ticket, and that action transactionally creates the
linked Visit and sets `queue.visit_id`. `POST /visits` also exists for
direct/testing use, but the real-world trigger is the Queue flow described
in the product's Reception workflow diagram.

`VisitTimelineEvent` is an append-only, visit-scoped, human-readable
timeline (distinct from but complementary to the generic `audit_logs`
table - the timeline is what the Visit Details page renders).
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
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


class VisitType(str, enum.Enum):
    WALK_IN = "WalkIn"
    APPOINTMENT = "Appointment"
    FOLLOW_UP = "FollowUp"
    EMERGENCY = "Emergency"
    TELECONSULTATION = "Teleconsultation"
    HOME_SERVICE = "HomeService"


class VisitStatus(str, enum.Enum):
    REGISTERED = "Registered"
    WAITING = "Waiting"
    CALLED = "Called"
    IN_CONSULTATION = "InConsultation"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    NO_SHOW = "NoShow"
    # Phase 21 (Vitals-before-Queue): a "draft" Visit created by Reception
    # for Consultation/Follow-up services BEFORE a Queue ticket exists, so
    # vitals can be captured first. Never reached via a status transition
    # from another state - it is the initial status set at creation time by
    # `VisitService.create_draft_visit_for_pre_queue` (mirroring how
    # REGISTERED is the initial status for the queue-first path), and its
    # only legal forward transition is into WAITING (once
    # `QueueService.create_queue` attaches a Queue ticket to this same
    # Visit row) or CANCELLED (receptionist abandons the draft). See
    # `services/queue_service.py::create_queue` for the DRAFT_VITALS ->
    # WAITING transition and every place `VisitStatus` is pattern-matched
    # (grepped clean at the time this was added: `doctor_workspace_service.py`
    # STATUS_TO_QUEUE map has no DRAFT_VITALS entry by design - a draft visit
    # has no linked Queue ticket yet, so there is nothing to sync; TV Display
    # reads off the `queues` table, not Visit status, so a draft (unqueued)
    # visit is naturally invisible there with no code change needed).
    DRAFT_VITALS = "DraftVitals"


# Mirrors `models.queue.QueuePriority` - kept as a distinct enum (rather than
# importing the queue one directly into this table's column) so Visit stays
# decoupled from Queue's schema; values are identical by design.
class VisitPriority(str, enum.Enum):
    NORMAL = "Normal"
    SENIOR_CITIZEN = "SeniorCitizen"
    PWD = "PWD"
    PREGNANT = "Pregnant"
    EMERGENCY = "Emergency"
    VIP = "VIP"


class VisitTimelineEventType(str, enum.Enum):
    REGISTERED = "Registered"
    CHECKED_IN = "CheckedIn"
    QUEUED = "Queued"
    CALLED = "Called"
    CONSULTATION_STARTED = "ConsultationStarted"
    CONSULTATION_FINISHED = "ConsultationFinished"
    CHECKED_OUT = "CheckedOut"
    STATUS_CHANGED = "StatusChanged"
    CANCELLED = "Cancelled"
    NOTE = "Note"
    # Phase 8 - Clinical Consultation events, recorded on the same
    # visit-scoped timeline (per spec: consultation events are recorded on
    # the Visit's timeline, so `GET /consultations/{id}/timeline` reuses
    # this table/endpoint rather than a parallel one).
    CONSULTATION_OPENED = "ConsultationOpened"
    SOAP_SAVED = "SoapSaved"
    DIAGNOSIS_ADDED = "DiagnosisAdded"
    CONSULTATION_COMPLETED = "ConsultationCompleted"
    CONSULTATION_SIGNED = "ConsultationSigned"
    # Phase 9 - Clinical Orders & Prescriptions events, recorded on the same
    # visit-scoped timeline for the same reason as the Phase 8 events above.
    ORDER_CREATED = "OrderCreated"
    PROCEDURE_CREATED = "ProcedureCreated"
    REFERRAL_CREATED = "ReferralCreated"
    PRESCRIPTION_CREATED = "PrescriptionCreated"
    # Phase 10 - Laboratory Management events. "Ordered" is intentionally
    # NOT re-recorded here - Phase 9's ORDER_CREATED already covers the
    # doctor's initial order creation and re-emitting a near-duplicate event
    # the instant the Laboratory workflow record is attached would just
    # double up the timeline for no new information.
    LAB_SPECIMEN_COLLECTED = "LabSpecimenCollected"
    LAB_PROCESSING_STARTED = "LabProcessingStarted"
    LAB_RESULTS_ENTERED = "LabResultsEntered"
    LAB_RESULTS_RELEASED = "LabResultsReleased"
    LAB_ORDER_CANCELLED = "LabOrderCancelled"
    # Phase 11 - Appointment Management. Emitted onto the same visit-scoped
    # timeline once an Appointment check-in creates this Visit (mirrors how
    # `QUEUED`/`CHECKED_IN` already work for walk-ins).
    APPOINTMENT_CHECKED_IN = "AppointmentCheckedIn"


# Legal forward transitions for a visit. Cancel/NoShow allowed from
# non-terminal states; terminal states accept no further transitions.
VISIT_STATUS_TRANSITIONS: dict[VisitStatus, set[VisitStatus]] = {
    VisitStatus.DRAFT_VITALS: {VisitStatus.WAITING, VisitStatus.CANCELLED},
    VisitStatus.REGISTERED: {VisitStatus.WAITING, VisitStatus.CANCELLED, VisitStatus.NO_SHOW},
    VisitStatus.WAITING: {VisitStatus.CALLED, VisitStatus.CANCELLED, VisitStatus.NO_SHOW},
    VisitStatus.CALLED: {VisitStatus.IN_CONSULTATION, VisitStatus.WAITING, VisitStatus.CANCELLED, VisitStatus.NO_SHOW},
    VisitStatus.IN_CONSULTATION: {VisitStatus.COMPLETED, VisitStatus.CANCELLED},
    VisitStatus.COMPLETED: set(),
    VisitStatus.CANCELLED: set(),
    VisitStatus.NO_SHOW: {VisitStatus.WAITING},
}


class Visit(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    """A single patient encounter/visit record."""

    __tablename__ = "visits"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    queue_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("queues.id", ondelete="SET NULL"), nullable=True, index=True
    )
    doctor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="SET NULL"), nullable=True, index=True
    )

    visit_number: Mapped[str] = mapped_column(String(30), nullable=False)
    visit_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    visit_type: Mapped[VisitType] = mapped_column(
        SAEnum(VisitType, name="visit_type", values_callable=_enum_values),
        nullable=False,
        default=VisitType.WALK_IN,
        server_default=VisitType.WALK_IN.value,
    )
    status: Mapped[VisitStatus] = mapped_column(
        SAEnum(VisitStatus, name="visit_status", values_callable=_enum_values),
        nullable=False,
        default=VisitStatus.REGISTERED,
        server_default=VisitStatus.REGISTERED.value,
        index=True,
    )
    priority: Mapped[VisitPriority] = mapped_column(
        SAEnum(VisitPriority, name="visit_priority", values_callable=_enum_values),
        nullable=False,
        default=VisitPriority.NORMAL,
        server_default=VisitPriority.NORMAL.value,
    )

    arrival_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_in_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    called_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consultation_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consultation_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_out_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    patient: Mapped["Patient"] = relationship()
    doctor: Mapped["Doctor | None"] = relationship()
    department: Mapped["Department | None"] = relationship()
    service: Mapped["ClinicService | None"] = relationship()
    branch: Mapped["Branch"] = relationship()
    queue: Mapped["Queue | None"] = relationship(foreign_keys=[queue_id])

    __table_args__ = (
        Index("ix_visits_clinic_branch_date_status", "clinic_id", "branch_id", "visit_date", "status"),
        Index("ix_visits_clinic_date_patient", "clinic_id", "visit_date", "patient_id"),
        UniqueConstraint("clinic_id", "visit_number", name="uq_visit_clinic_visit_number"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Visit id={self.id} visit_number={self.visit_number!r} status={self.status!r}>"


class VisitTimelineEvent(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Append-only, human-readable timeline of events for a Visit."""

    __tablename__ = "visit_timeline_events"

    visit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[VisitTimelineEventType] = mapped_column(
        SAEnum(VisitTimelineEventType, name="visit_timeline_event_type", values_callable=_enum_values),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<VisitTimelineEvent visit_id={self.visit_id} event_type={self.event_type!r}>"
