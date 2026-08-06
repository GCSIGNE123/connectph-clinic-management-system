"""Pydantic schemas for Appointment Management (Phase 11)."""

from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.appointment import (
    AppointmentHistoryAction,
    AppointmentStatus,
    AppointmentType,
    DoctorScheduleBlockType,
    WaitlistStatus,
)


class AppointmentCreate(BaseModel):
    patient_id: UUID
    branch_id: UUID
    doctor_id: UUID
    department_id: UUID | None = None
    service_id: UUID | None = None
    appointment_type: AppointmentType = AppointmentType.NEW_CONSULTATION
    appointment_date: date
    start_time: time
    notes: str | None = Field(default=None, max_length=1000)


class AppointmentReschedule(BaseModel):
    appointment_date: date
    start_time: time
    reason: str | None = Field(default=None, max_length=500)


class AppointmentCancel(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class AppointmentNoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class AppointmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    appointment_number: str
    branch_id: UUID
    patient_id: UUID
    doctor_id: UUID
    department_id: UUID | None = None
    service_id: UUID | None = None
    appointment_type: AppointmentType
    appointment_date: date
    start_time: time
    end_time: time
    status: AppointmentStatus
    queue_id: UUID | None = None
    visit_id: UUID | None = None
    notes: str | None = None
    created_by: UUID | None = None
    updated_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AppointmentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    appointment_number: str
    appointment_date: date
    start_time: time
    end_time: time
    status: AppointmentStatus
    appointment_type: AppointmentType
    patient_id: UUID
    patient_name: str | None = None
    patient_number: str | None = None
    doctor_id: UUID
    doctor_name: str | None = None
    department_name: str | None = None
    branch_id: UUID


class AppointmentHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: AppointmentHistoryAction
    from_value: str | None = None
    to_value: str | None = None
    changed_by: UUID | None = None
    changed_at: datetime
    note: str | None = None


class AppointmentDetail(AppointmentRead):
    patient_name: str | None = None
    patient_number: str | None = None
    doctor_name: str | None = None
    department_name: str | None = None
    service_name: str | None = None
    branch_name: str | None = None
    history: list[AppointmentHistoryRead] = Field(default_factory=list)


class AppointmentSearchParams(BaseModel):
    q: str | None = None
    branch_id: UUID | None = None
    department_id: UUID | None = None
    doctor_id: UUID | None = None
    status: AppointmentStatus | None = None
    appointment_type: AppointmentType | None = None
    date_from: date | None = None
    date_to: date | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class AppointmentListResponse(BaseModel):
    items: list[AppointmentListItem]
    total: int
    limit: int
    offset: int


class TimeSlotOut(BaseModel):
    """A computed (non-persisted) available/blocked slot - see
    `models/appointment.py` module docstring for why `TimeSlot` isn't a table."""

    start_time: time
    end_time: time
    is_available: bool
    reason: str | None = None  # populated when is_available is False


class AvailableSlotsResponse(BaseModel):
    doctor_id: UUID
    date: date
    slots: list[TimeSlotOut]


# --- Doctor schedule ---


class DoctorScheduleDayIn(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    lunch_break_start: time | None = None
    lunch_break_end: time | None = None
    slot_duration_minutes: int = Field(default=15, ge=5, le=240)
    max_patients_per_day: int | None = Field(default=None, ge=1)
    is_active: bool = True
    branch_id: UUID | None = None


class DoctorScheduleSet(BaseModel):
    days: list[DoctorScheduleDayIn]


class DoctorScheduleDayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    day_of_week: int
    start_time: time
    end_time: time
    lunch_break_start: time | None = None
    lunch_break_end: time | None = None
    slot_duration_minutes: int
    max_patients_per_day: int | None = None
    is_active: bool
    branch_id: UUID | None = None


class DoctorScheduleBlockCreate(BaseModel):
    block_date: date
    block_type: DoctorScheduleBlockType = DoctorScheduleBlockType.BLOCKED
    reason: str | None = Field(default=None, max_length=255)


class DoctorScheduleBlockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    block_date: date
    block_type: DoctorScheduleBlockType
    reason: str | None = None


class DoctorScheduleOut(BaseModel):
    doctor_id: UUID
    days: list[DoctorScheduleDayOut]
    blocks: list[DoctorScheduleBlockOut]


# --- Waitlist ---


class WaitlistEntryCreate(BaseModel):
    patient_id: UUID
    doctor_id: UUID
    branch_id: UUID
    date_from: date
    date_to: date
    notes: str | None = Field(default=None, max_length=500)


class WaitlistEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    doctor_id: UUID
    branch_id: UUID
    date_from: date
    date_to: date
    status: WaitlistStatus
    offered_slot_date: date | None = None
    offered_slot_start_time: time | None = None
    notes: str | None = None
