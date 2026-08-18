"""Pydantic schemas for visits (encounters) and the visit timeline."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.visit import VisitPriority, VisitStatus, VisitTimelineEventType, VisitType


class VisitCreate(BaseModel):
    """Direct/standalone visit creation - mostly for internal/test use.
    The primary real-world trigger is `POST /queues`, which creates a
    linked Visit internally (see `services/queue_service.py`)."""

    patient_id: UUID
    branch_id: UUID
    doctor_id: UUID | None = None
    department_id: UUID | None = None
    service_id: UUID | None = None
    visit_type: VisitType = VisitType.WALK_IN
    priority: VisitPriority = VisitPriority.NORMAL
    remarks: str | None = Field(default=None, max_length=1000)


class VisitPreQueueCreate(BaseModel):
    """Creates a draft Visit (`DraftVitals` status) BEFORE any Queue ticket
    exists, for the two flows that need something to exist prior to queue
    creation:

    - Phase 21 (Vitals-before-Queue): Consultation/Follow-up services, so
      Reception can capture vitals first. `doctor_id` is required for this
      path because `ConsultationService.open_consultation_for_reception`
      - reused unmodified for the vitals step - requires a non-null
      `visit.doctor_id`.
    - Laboratory pay-first workflow: a walk-in Laboratory ticket, so an
      invoice can be created and paid before the queue ticket is raised.
      `doctor_id` is genuinely optional here (see `QueueService`'s Doctor
      rule for Laboratory tickets) - the field itself stays optional at the
      schema level; `VisitService.create_draft_visit_for_pre_queue` is the
      real enforcement point for "Consultation/Follow-up still requires a
      doctor", mirroring how `service_requires_pre_queue_vitals` is already
      enforced in the service layer rather than the schema for `QueueCreate`.
    """

    patient_id: UUID
    branch_id: UUID
    doctor_id: UUID | None = None
    department_id: UUID
    service_id: UUID
    visit_type: VisitType = VisitType.WALK_IN
    priority: VisitPriority = VisitPriority.NORMAL
    remarks: str | None = Field(default=None, max_length=1000)


class VisitUpdate(BaseModel):
    doctor_id: UUID | None = None
    department_id: UUID | None = None
    service_id: UUID | None = None
    priority: VisitPriority | None = None
    remarks: str | None = Field(default=None, max_length=1000)


class VisitStatusUpdate(BaseModel):
    status: VisitStatus
    note: str | None = Field(default=None, max_length=500)


class VisitTimelineEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    visit_id: UUID
    event_type: VisitTimelineEventType
    occurred_at: datetime
    recorded_by: UUID | None = None
    note: str | None = None
    event_metadata: dict | None = None


class VisitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    branch_id: UUID
    patient_id: UUID
    queue_id: UUID | None = None
    doctor_id: UUID | None = None
    department_id: UUID | None = None
    service_id: UUID | None = None
    visit_number: str
    visit_date: date
    visit_type: VisitType
    status: VisitStatus
    priority: VisitPriority
    arrival_time: datetime | None = None
    check_in_time: datetime | None = None
    called_time: datetime | None = None
    consultation_start: datetime | None = None
    consultation_end: datetime | None = None
    check_out_time: datetime | None = None
    remarks: str | None = None
    created_by: UUID | None = None
    updated_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class VisitListItem(BaseModel):
    """Slim projection with denormalized display fields for list/search tables."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    visit_number: str
    visit_date: date
    visit_type: VisitType
    status: VisitStatus
    priority: VisitPriority
    branch_id: UUID
    patient_id: UUID
    patient_name: str | None = None
    patient_number: str | None = None
    doctor_id: UUID | None = None
    doctor_name: str | None = None
    department_id: UUID | None = None
    department_name: str | None = None
    service_id: UUID | None = None
    service_name: str | None = None
    queue_id: UUID | None = None
    queue_number: str | None = None
    created_at: datetime


class VisitDetail(VisitRead):
    patient_name: str | None = None
    patient_number: str | None = None
    doctor_name: str | None = None
    department_name: str | None = None
    service_name: str | None = None
    branch_name: str | None = None
    queue_number: str | None = None
    timeline: list[VisitTimelineEventRead] = Field(default_factory=list)


class VisitSearchParams(BaseModel):
    q: str | None = None
    branch_id: UUID | None = None
    patient_id: UUID | None = None
    doctor_id: UUID | None = None
    department_id: UUID | None = None
    status: VisitStatus | None = None
    visit_type: VisitType | None = None
    date_from: date | None = None
    date_to: date | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class VisitListResponse(BaseModel):
    items: list[VisitListItem]
    total: int
    limit: int
    offset: int
