"""Appointment Management endpoints (Phase 11).

Role gating (see `core/dependencies.py`): Reception (plus Owner/Administrator)
create/edit/reschedule/cancel/check-in; Doctor completes/no-shows (plus
Owner/Administrator); everyone clinic-relevant can view; doctor schedule
administration is Administrator-only, mirroring Phase 10's template gating.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_current_user,
    get_db,
    require_appointment_complete_role,
    require_appointment_manage_role,
    require_appointment_schedule_manage_role,
    require_appointment_view_role,
    require_clinic_context,
)
from app.models.user import User
from app.schemas.appointment import (
    AppointmentCancel,
    AppointmentCreate,
    AppointmentDetail,
    AppointmentHistoryRead,
    AppointmentListResponse,
    AppointmentNoteCreate,
    AppointmentReschedule,
    AvailableSlotsResponse,
    DoctorScheduleBlockCreate,
    DoctorScheduleOut,
    DoctorScheduleSet,
)
from app.schemas.appointment import AppointmentSearchParams
from app.services.appointment_service import AppointmentService
from app.services.schedule_service import ScheduleService
from app.services.time_slot_service import TimeSlotService

router = APIRouter(prefix="/appointments", tags=["appointments"])
doctors_router = APIRouter(prefix="/doctors", tags=["appointments"])
patients_router = APIRouter(prefix="/patients", tags=["appointments"])


@router.post("", response_model=AppointmentDetail)
async def create_appointment(
    payload: AppointmentCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_appointment_manage_role),
) -> AppointmentDetail:
    return await AppointmentService(db).create_appointment(payload, clinic_id=clinic_id, actor=current_user)


@router.get("", response_model=AppointmentListResponse)
async def search_appointments(
    q: str | None = None,
    branch_id: UUID | None = None,
    department_id: UUID | None = None,
    doctor_id: UUID | None = None,
    status: str | None = None,
    appointment_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 50,
    offset: int = 0,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_appointment_view_role),
) -> AppointmentListResponse:
    params = AppointmentSearchParams(
        q=q, branch_id=branch_id, department_id=department_id, doctor_id=doctor_id,
        status=status, appointment_type=appointment_type, date_from=date_from, date_to=date_to,
        limit=limit, offset=offset,
    )
    items, total = await AppointmentService(db).search(clinic_id=clinic_id, params=params)
    return AppointmentListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/calendar", response_model=AppointmentListResponse)
async def calendar(
    date_from: date,
    date_to: date,
    branch_id: UUID | None = None,
    department_id: UUID | None = None,
    doctor_id: UUID | None = None,
    appointment_type: str | None = None,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_appointment_view_role),
) -> AppointmentListResponse:
    params = AppointmentSearchParams(
        branch_id=branch_id, department_id=department_id, doctor_id=doctor_id,
        appointment_type=appointment_type, date_from=date_from, date_to=date_to, limit=200, offset=0,
    )
    items, total = await AppointmentService(db).search(clinic_id=clinic_id, params=params)
    return AppointmentListResponse(items=items, total=total, limit=200, offset=0)


@router.get("/dashboard/reception")
async def reception_dashboard(
    on_date: date | None = None,
    branch_id: UUID | None = None,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_appointment_view_role),
) -> dict:
    from datetime import UTC, datetime

    from app.models.appointment import AppointmentStatus

    today = on_date or datetime.now(UTC).date()
    params = AppointmentSearchParams(branch_id=branch_id, date_from=today, date_to=today, limit=200, offset=0)
    items, total = await AppointmentService(db).search(clinic_id=clinic_id, params=params)
    return {
        "date": today,
        "total": total,
        "todays_schedule": [i for i in items],
        "no_shows": [i for i in items if i.status == AppointmentStatus.NO_SHOW],
        "checked_in": [i for i in items if i.status in (AppointmentStatus.CHECKED_IN, AppointmentStatus.WAITING)],
        "upcoming": [i for i in items if i.status in (AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED)],
    }


@router.get("/dashboard/doctor")
async def doctor_dashboard(
    doctor_id: UUID,
    on_date: date | None = None,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_appointment_view_role),
) -> dict:
    from datetime import UTC, datetime

    from app.models.appointment import AppointmentStatus

    today = on_date or datetime.now(UTC).date()
    params = AppointmentSearchParams(doctor_id=doctor_id, date_from=today, date_to=today, limit=200, offset=0)
    items, total = await AppointmentService(db).search(clinic_id=clinic_id, params=params)
    return {
        "date": today,
        "total": total,
        "scheduled": [i for i in items if i.status in (AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED)],
        "checked_in": [i for i in items if i.status in (AppointmentStatus.CHECKED_IN, AppointmentStatus.WAITING, AppointmentStatus.IN_CONSULTATION)],
        "completed": [i for i in items if i.status == AppointmentStatus.COMPLETED],
    }


@router.get("/{appointment_id}", response_model=AppointmentDetail)
async def get_appointment(
    appointment_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_appointment_view_role),
) -> AppointmentDetail:
    return await AppointmentService(db).get_detail(appointment_id, clinic_id=clinic_id)


@router.get("/{appointment_id}/history", response_model=list[AppointmentHistoryRead])
async def get_appointment_history(
    appointment_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_appointment_view_role),
) -> list[AppointmentHistoryRead]:
    return await AppointmentService(db).get_history(appointment_id, clinic_id=clinic_id)


@router.post("/{appointment_id}/notes")
async def add_note(
    appointment_id: UUID,
    payload: AppointmentNoteCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_appointment_view_role),
) -> dict:
    await AppointmentService(db).add_note(appointment_id, payload, clinic_id=clinic_id, actor=current_user)
    return {"status": "ok"}


@router.patch("/{appointment_id}/confirm", response_model=AppointmentDetail)
async def confirm_appointment(
    appointment_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_appointment_manage_role),
) -> AppointmentDetail:
    return await AppointmentService(db).confirm_appointment(appointment_id, clinic_id=clinic_id, actor=current_user)


@router.patch("/{appointment_id}/reschedule", response_model=AppointmentDetail)
async def reschedule_appointment(
    appointment_id: UUID,
    payload: AppointmentReschedule,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_appointment_manage_role),
) -> AppointmentDetail:
    return await AppointmentService(db).reschedule_appointment(appointment_id, payload, clinic_id=clinic_id, actor=current_user)


@router.patch("/{appointment_id}/cancel", response_model=AppointmentDetail)
async def cancel_appointment(
    appointment_id: UUID,
    payload: AppointmentCancel,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_appointment_manage_role),
) -> AppointmentDetail:
    return await AppointmentService(db).cancel_appointment(appointment_id, payload.reason, clinic_id=clinic_id, actor=current_user)


@router.post("/{appointment_id}/check-in", response_model=AppointmentDetail)
async def check_in_appointment(
    appointment_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_appointment_manage_role),
) -> AppointmentDetail:
    return await AppointmentService(db).check_in_appointment(appointment_id, clinic_id=clinic_id, actor=current_user)


@router.patch("/{appointment_id}/complete", response_model=AppointmentDetail)
async def complete_appointment(
    appointment_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_appointment_complete_role),
) -> AppointmentDetail:
    return await AppointmentService(db).complete_appointment(appointment_id, clinic_id=clinic_id, actor=current_user)


@router.patch("/{appointment_id}/no-show", response_model=AppointmentDetail)
async def mark_no_show(
    appointment_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_appointment_manage_role),
) -> AppointmentDetail:
    return await AppointmentService(db).mark_no_show(appointment_id, clinic_id=clinic_id, actor=current_user)


# --- Doctor schedule & available slots ---


@doctors_router.get("/{doctor_id}/schedule", response_model=DoctorScheduleOut)
async def get_doctor_schedule(
    doctor_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_appointment_view_role),
) -> DoctorScheduleOut:
    return await ScheduleService(db).get_schedule(doctor_id, clinic_id=clinic_id)


@doctors_router.put("/{doctor_id}/schedule", response_model=DoctorScheduleOut)
async def set_doctor_schedule(
    doctor_id: UUID,
    payload: DoctorScheduleSet,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_appointment_schedule_manage_role),
) -> DoctorScheduleOut:
    return await ScheduleService(db).set_schedule(doctor_id, payload, clinic_id=clinic_id)


@doctors_router.post("/{doctor_id}/schedule/blocks", response_model=DoctorScheduleOut)
async def add_schedule_block(
    doctor_id: UUID,
    payload: DoctorScheduleBlockCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_appointment_schedule_manage_role),
) -> DoctorScheduleOut:
    return await ScheduleService(db).add_block(doctor_id, payload, clinic_id=clinic_id)


@doctors_router.delete("/{doctor_id}/schedule/blocks/{block_id}", response_model=DoctorScheduleOut)
async def remove_schedule_block(
    doctor_id: UUID,
    block_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_appointment_schedule_manage_role),
) -> DoctorScheduleOut:
    return await ScheduleService(db).remove_block(doctor_id, block_id, clinic_id=clinic_id)


@doctors_router.get("/{doctor_id}/available-slots", response_model=AvailableSlotsResponse)
async def get_available_slots(
    doctor_id: UUID,
    date: date,
    branch_id: UUID | None = None,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_appointment_view_role),
) -> AvailableSlotsResponse:
    slots = await TimeSlotService(db).get_available_slots(clinic_id=clinic_id, doctor_id=doctor_id, branch_id=branch_id, on_date=date)
    return AvailableSlotsResponse(doctor_id=doctor_id, date=date, slots=slots)


# --- Patient appointments tab ---


@patients_router.get("/{patient_id}/appointments")
async def list_patient_appointments(
    patient_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_appointment_view_role),
) -> dict:
    from app.models.appointment import AppointmentStatus

    items = await AppointmentService(db).list_for_patient(patient_id, clinic_id=clinic_id)
    return {
        "upcoming": [i for i in items if i.status in (AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED, AppointmentStatus.CHECKED_IN, AppointmentStatus.WAITING, AppointmentStatus.IN_CONSULTATION)],
        "completed": [i for i in items if i.status == AppointmentStatus.COMPLETED],
        "cancelled": [i for i in items if i.status in (AppointmentStatus.CANCELLED, AppointmentStatus.RESCHEDULED)],
        "no_show": [i for i in items if i.status == AppointmentStatus.NO_SHOW],
    }
