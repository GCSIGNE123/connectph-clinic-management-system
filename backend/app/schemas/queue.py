"""Pydantic schemas for queue tickets, status history, and printable slips."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.queue import QueuePriority, QueueStatus


class QueueCreate(BaseModel):
    patient_id: UUID
    branch_id: UUID
    department_id: UUID
    doctor_id: UUID | None = None
    service_id: UUID
    priority: QueuePriority = QueuePriority.NORMAL
    notes: str | None = Field(default=None, max_length=1000)
    # Phase 21 (Vitals-before-Queue): when set, this Queue ticket is created
    # for an EXISTING `DraftVitals` Visit (created via `POST /visits/pre-queue`)
    # instead of a brand-new Visit being created as a side effect - see
    # `services/queue_service.py::create_queue`. Omitted (None), every
    # existing caller/behavior is completely unchanged.
    visit_id: UUID | None = None


class QueueUpdate(BaseModel):
    """Edit a ticket's routing (doctor/department reassignment) - does not
    touch status, which goes through the dedicated status-transition endpoint."""

    department_id: UUID | None = None
    doctor_id: UUID | None = None
    service_id: UUID | None = None
    priority: QueuePriority | None = None
    notes: str | None = Field(default=None, max_length=1000)


class QueueStatusUpdate(BaseModel):
    status: QueueStatus
    note: str | None = Field(default=None, max_length=500)


class QueueStatusHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    from_status: QueueStatus | None = None
    to_status: QueueStatus
    changed_by: UUID | None = None
    changed_at: datetime
    note: str | None = None


class QueueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    branch_id: UUID
    patient_id: UUID
    department_id: UUID
    doctor_id: UUID | None = None
    service_id: UUID
    # Phase 6: optional additive field - set once queue creation
    # transactionally creates the linked Visit. Existing Phase 5 clients
    # that ignore unknown fields remain unaffected (backward compatible).
    visit_id: UUID | None = None
    queue_number: str
    queue_prefix: str
    queue_date: date
    priority: QueuePriority
    status: QueueStatus
    notes: str | None = None
    called_at: datetime | None = None
    serving_started_at: datetime | None = None
    completed_at: datetime | None = None
    created_by: UUID | None = None
    updated_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class QueueListItem(BaseModel):
    """Slim projection with denormalized display fields for the reception table."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    queue_number: str
    queue_date: date
    priority: QueuePriority
    status: QueueStatus
    branch_id: UUID
    department_id: UUID
    department_name: str | None = None
    doctor_id: UUID | None = None
    doctor_name: str | None = None
    service_id: UUID
    service_name: str | None = None
    patient_id: UUID
    patient_name: str | None = None
    patient_number: str | None = None
    created_at: datetime
    called_at: datetime | None = None
    # Phase 20 (items 4-5): needed so the Reception Queue screen can offer
    # an "Enter Vitals" action per ticket (opens
    # `/visits/{id}/consultation/open-for-reception`) - previously omitted
    # from this slim projection since nothing on the Queue screen needed it
    # before this phase.
    visit_id: UUID | None = None


class QueueDetail(QueueRead):
    history: list[QueueStatusHistoryRead] = Field(default_factory=list)
    patient_name: str | None = None
    patient_number: str | None = None
    department_name: str | None = None
    doctor_name: str | None = None
    service_name: str | None = None
    branch_name: str | None = None
    visit_number: str | None = None


class QueueSearchParams(BaseModel):
    q: str | None = None
    branch_id: UUID | None = None
    department_id: UUID | None = None
    doctor_id: UUID | None = None
    status: QueueStatus | None = None
    priority: QueuePriority | None = None
    queue_date: date | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class QueueListResponse(BaseModel):
    items: list[QueueListItem]
    total: int
    limit: int
    offset: int


class QueueSlip(BaseModel):
    queue_id: UUID
    queue_number: str
    clinic_name: str
    branch_name: str
    patient_name: str
    department_name: str
    doctor_name: str | None = None
    service_name: str
    priority: QueuePriority
    queue_date: date
    created_at: datetime
    qr_token: str
