"""Patient Self-Service Appointment Booking (Phase 19).

Every route here is gated by `get_current_patient`, and every write is
scoped to `current.id` (== `current.patient.id`) taken from the verified
JWT - never from a request body/query param. This module does NOT
reimplement the appointment engine: it calls straight into the same
`AppointmentService` / `TimeSlotService` / `AppointmentRepository` that
`app/api/v1/appointments.py` (staff-facing) uses, so a patient-booked
appointment is a plain row in the same `appointments` table, validated by
the same slot/hours/break/holiday/blocked-date/max-daily rules, and subject
to the same DB-level double-booking guarantee (the partial unique index
`uq_appointments_doctor_slot_active` from migration 0012 - see
`services/appointment_service.py` for the full race-condition writeup).

Reference-data endpoints (branches/departments/doctors) are thin,
patient-safe read-only projections - NOT copies of the staff endpoints in
`branches.py`/`departments.py`/`doctors.py`, which are gated by
`require_config_view_role` (clinic staff only) and return richer
staff-internal fields. No such patient-readable equivalents existed before
this phase (checked prior to writing these).
"""

from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentPatient, get_current_patient, get_db
from app.models.branch import Branch
from app.models.department import Department
from app.models.doctor import Doctor, DoctorStatus
from app.schemas.appointment import AppointmentCreate, AppointmentReschedule
from app.schemas.patient_portal import (
    PatientAppointmentCancelRequest,
    PatientAppointmentCreateRequest,
    PatientAppointmentDetailResponse,
    PatientAppointmentRescheduleRequest,
    PatientAvailableDatesResponse,
    PatientAvailableSlotsResponse,
    PatientBranchOption,
    PatientDepartmentOption,
    PatientDoctorOption,
    PatientTimeSlot,
)
from app.services.appointment_service import AppointmentService
from app.services.time_slot_service import TimeSlotService

router = APIRouter(prefix="/appointments", tags=["patient-portal-appointments"])

MAX_AVAILABILITY_RANGE_DAYS = 60


# --------------------------------------------------------------------------
# Reference data (patient-safe reads)
# --------------------------------------------------------------------------


@router.get("/branches", response_model=list[PatientBranchOption])
async def list_branches(current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)):
    stmt = select(Branch).where(
        Branch.clinic_id == current.clinic_id, Branch.is_deleted.is_(False), Branch.is_active.is_(True)
    ).order_by(Branch.name)
    rows = (await db.execute(stmt)).scalars().all()
    return [PatientBranchOption(id=b.id, name=b.name, address=b.address) for b in rows]


@router.get("/departments", response_model=list[PatientDepartmentOption])
async def list_departments(current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)):
    stmt = select(Department).where(
        Department.clinic_id == current.clinic_id, Department.is_deleted.is_(False), Department.status == "Active"
    ).order_by(Department.name)
    rows = (await db.execute(stmt)).scalars().all()
    return [PatientDepartmentOption(id=d.id, name=d.name) for d in rows]


@router.get("/doctors", response_model=list[PatientDoctorOption])
async def list_doctors(
    branch_id: UUID | None = Query(default=None),
    department_id: UUID | None = Query(default=None),
    current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db),
):
    # `Doctor.branch_id`/`department_id` are nullable - a NULL means the
    # doctor isn't tied to one specific branch/department (they can be
    # booked regardless), matching how the slot engine itself works (
    # `TimeSlotService` never looks at these fields, only `doctor_id` +
    # date). Filtering on strict equality alone (as the staff-side
    # `DoctorRepository.search` does - same pre-existing gap there, see
    # docs/BUGS.md) would incorrectly hide every doctor with no
    # branch/department assignment from patients trying to book, which is
    # the common case in this codebase's own seed data. `OR IS NULL` fixes
    # that for the patient-facing picker.
    filters = [Doctor.clinic_id == current.clinic_id, Doctor.is_deleted.is_(False), Doctor.status == DoctorStatus.ACTIVE]
    if branch_id is not None:
        filters.append(or_(Doctor.branch_id == branch_id, Doctor.branch_id.is_(None)))
    if department_id is not None:
        filters.append(or_(Doctor.department_id == department_id, Doctor.department_id.is_(None)))
    stmt = select(Doctor).where(*filters).order_by(Doctor.last_name, Doctor.first_name)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        PatientDoctorOption(
            id=doc.id, full_name=doc.full_name, specialization=doc.specialization,
            department_id=doc.department_id, branch_id=doc.branch_id,
        )
        for doc in rows
    ]


# --------------------------------------------------------------------------
# Availability
# --------------------------------------------------------------------------


@router.get("/availability", response_model=PatientAvailableDatesResponse)
async def get_available_dates(
    doctor_id: UUID = Query(...),
    branch_id: UUID | None = Query(default=None),
    date_from: date = Query(...),
    date_to: date = Query(...),
    current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db),
):
    if date_to < date_from:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="date_to must be on or after date_from.")
    if (date_to - date_from).days > MAX_AVAILABILITY_RANGE_DAYS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Range cannot exceed {MAX_AVAILABILITY_RANGE_DAYS} days.")

    doctor = (await db.execute(
        select(Doctor).where(Doctor.id == doctor_id, Doctor.clinic_id == current.clinic_id, Doctor.is_deleted.is_(False))
    )).scalar_one_or_none()
    if doctor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    slot_service = TimeSlotService(db)
    available_dates: list[date] = []
    cursor = max(date_from, date.today())
    while cursor <= date_to:
        slots = await slot_service.get_available_slots(
            clinic_id=current.clinic_id, doctor_id=doctor_id, branch_id=branch_id, on_date=cursor
        )
        if any(s.is_available for s in slots):
            available_dates.append(cursor)
        cursor += timedelta(days=1)
    return PatientAvailableDatesResponse(doctor_id=doctor_id, dates=available_dates)


@router.get("/availability/{on_date}", response_model=PatientAvailableSlotsResponse)
async def get_available_slots_for_date(
    on_date: date,
    doctor_id: UUID = Query(...),
    branch_id: UUID | None = Query(default=None),
    current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db),
):
    doctor = (await db.execute(
        select(Doctor).where(Doctor.id == doctor_id, Doctor.clinic_id == current.clinic_id, Doctor.is_deleted.is_(False))
    )).scalar_one_or_none()
    if doctor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    slot_service = TimeSlotService(db)
    slots = await slot_service.get_available_slots(
        clinic_id=current.clinic_id, doctor_id=doctor_id, branch_id=branch_id, on_date=on_date
    )
    return PatientAvailableSlotsResponse(
        doctor_id=doctor_id, date=on_date,
        slots=[PatientTimeSlot(start_time=s.start_time, end_time=s.end_time) for s in slots if s.is_available],
    )


# --------------------------------------------------------------------------
# Booking / reschedule / cancel
# --------------------------------------------------------------------------


def _to_detail(detail) -> PatientAppointmentDetailResponse:
    return PatientAppointmentDetailResponse(
        id=detail.id, appointment_number=detail.appointment_number, appointment_type=detail.appointment_type.value,
        appointment_date=detail.appointment_date, start_time=detail.start_time, end_time=detail.end_time,
        status=detail.status.value, doctor_name=detail.doctor_name, department_name=detail.department_name,
        branch_name=detail.branch_name, notes=detail.notes,
    )


@router.post("", response_model=PatientAppointmentDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    payload: PatientAppointmentCreateRequest,
    current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db),
):
    service = AppointmentService(db)
    create_payload = AppointmentCreate(
        patient_id=current.id, branch_id=payload.branch_id, doctor_id=payload.doctor_id,
        department_id=payload.department_id, service_id=payload.service_id,
        appointment_type=payload.appointment_type, appointment_date=payload.appointment_date,
        start_time=payload.start_time, notes=payload.notes,
    )
    detail = await service.create_patient_appointment(create_payload, clinic_id=current.clinic_id, patient_id=current.id)
    return _to_detail(detail)


@router.patch("/{appointment_id}/reschedule", response_model=PatientAppointmentDetailResponse)
async def reschedule_appointment(
    appointment_id: UUID, payload: PatientAppointmentRescheduleRequest,
    current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db),
):
    service = AppointmentService(db)
    reschedule_payload = AppointmentReschedule(
        appointment_date=payload.appointment_date, start_time=payload.start_time, reason=payload.reason,
    )
    detail = await service.reschedule_patient_appointment(
        appointment_id, reschedule_payload, clinic_id=current.clinic_id, patient_id=current.id
    )
    return _to_detail(detail)


@router.post("/{appointment_id}/cancel", response_model=PatientAppointmentDetailResponse)
async def cancel_appointment(
    appointment_id: UUID, payload: PatientAppointmentCancelRequest,
    current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db),
):
    service = AppointmentService(db)
    detail = await service.cancel_patient_appointment(
        appointment_id, payload.reason, clinic_id=current.clinic_id, patient_id=current.id
    )
    return _to_detail(detail)
