"""Pydantic schemas for the Doctor Workspace (Phase 7)."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.doctor_activity import DoctorActivityType
from app.models.visit import VisitPriority, VisitStatus, VisitType


class DoctorDashboardStats(BaseModel):
    waiting: int
    called: int
    serving: int
    completed_today: int
    cancelled: int
    no_show: int
    avg_consultation_seconds: float | None = None


class DoctorDashboardResponse(BaseModel):
    today: date
    doctor_id: UUID | None = None
    doctor_name: str | None = None
    branch_name: str | None = None
    department_name: str | None = None
    stats: DoctorDashboardStats


class DoctorQueueItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    visit_id: UUID
    visit_number: str
    queue_id: UUID | None = None
    queue_number: str | None = None
    patient_id: UUID
    patient_name: str
    patient_number: str
    age: int | None = None
    gender: str | None = None
    priority: VisitPriority
    status: VisitStatus
    visit_type: VisitType
    arrival_time: datetime | None = None
    called_time: datetime | None = None
    consultation_start: datetime | None = None
    waiting_seconds: float | None = None
    is_locked: bool = False
    locked_by_name: str | None = None
    locked_by_self: bool = False


class DoctorQueueResponse(BaseModel):
    items: list[DoctorQueueItem]
    total: int


class CancelVisitRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class LockInfo(BaseModel):
    locked: bool
    locked_by: UUID | None = None
    locked_by_name: str | None = None
    locked_at: datetime | None = None
    is_self: bool = False


class DoctorSessionStatus(BaseModel):
    """Client Acceptance Revisions Round 3, item 14: whether a doctor has
    an open "actively receiving patients" session for today."""

    active: bool
    started_at: datetime | None = None


class DoctorActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    doctor_id: UUID
    user_id: UUID
    visit_id: UUID | None
    activity_type: DoctorActivityType
    occurred_at: datetime
    activity_metadata: dict | None = None
