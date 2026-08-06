"""Doctor CRUD + doctor-schedule sub-routes, tenant-scoped and role-gated."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_db,
    require_clinic_context,
    require_config_manage_role,
    require_config_view_role,
)
from app.models.doctor import DoctorStatus
from app.models.user import User
from app.schemas.doctor import (
    DoctorCreate,
    DoctorListResponse,
    DoctorPhotoUploadResponse,
    DoctorRead,
    DoctorScheduleCreate,
    DoctorScheduleRead,
    DoctorScheduleUpdate,
    DoctorSearchParams,
    DoctorUpdate,
)
from app.services.doctor_service import DoctorService

router = APIRouter(prefix="/doctors", tags=["doctors"])


@router.get("", response_model=DoctorListResponse)
async def list_doctors(
    q: str | None = Query(default=None),
    department_id: UUID | None = Query(default=None),
    branch_id: UUID | None = Query(default=None),
    status_filter: DoctorStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> DoctorListResponse:
    params = DoctorSearchParams(
        q=q, department_id=department_id, branch_id=branch_id, status=status_filter, limit=limit, offset=offset
    )
    service = DoctorService(db)
    items, total = await service.search(clinic_id, params)
    return DoctorListResponse(items=[DoctorRead.model_validate(i) for i in items], total=total, limit=limit, offset=offset)


@router.get("/{doctor_id}", response_model=DoctorRead)
async def get_doctor(
    doctor_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> DoctorRead:
    service = DoctorService(db)
    return await service.get(doctor_id, clinic_id)


@router.post("", response_model=DoctorRead, status_code=201)
async def create_doctor(
    payload: DoctorCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> DoctorRead:
    service = DoctorService(db)
    return await service.create(payload, clinic_id=clinic_id, actor=current_user)


@router.put("/{doctor_id}", response_model=DoctorRead)
async def update_doctor(
    doctor_id: UUID,
    payload: DoctorUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> DoctorRead:
    service = DoctorService(db)
    return await service.update(doctor_id, payload, clinic_id=clinic_id, actor=current_user)


@router.delete("/{doctor_id}", status_code=204)
async def delete_doctor(
    doctor_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> None:
    service = DoctorService(db)
    await service.delete(doctor_id, clinic_id=clinic_id, actor=current_user)


@router.post("/{doctor_id}/restore", response_model=DoctorRead)
async def restore_doctor(
    doctor_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> DoctorRead:
    service = DoctorService(db)
    return await service.restore(doctor_id, clinic_id=clinic_id, actor=current_user)


@router.post("/{doctor_id}/photo", response_model=DoctorPhotoUploadResponse)
async def request_doctor_photo_upload(
    doctor_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> DoctorPhotoUploadResponse:
    service = DoctorService(db)
    result = await service.request_photo_upload_url(doctor_id, clinic_id=clinic_id)
    return DoctorPhotoUploadResponse(**result)


# --- Doctor schedules (availability windows - no slot/booking logic) ---


@router.get("/{doctor_id}/schedules", response_model=list[DoctorScheduleRead])
async def list_doctor_schedules(
    doctor_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> list[DoctorScheduleRead]:
    service = DoctorService(db)
    schedules = await service.list_schedules(doctor_id, clinic_id=clinic_id)
    return [DoctorScheduleRead.model_validate(s) for s in schedules]


@router.post("/{doctor_id}/schedules", response_model=DoctorScheduleRead, status_code=201)
async def add_doctor_schedule(
    doctor_id: UUID,
    payload: DoctorScheduleCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> DoctorScheduleRead:
    service = DoctorService(db)
    return await service.add_schedule(doctor_id, payload, clinic_id=clinic_id, actor=current_user)


@router.put("/{doctor_id}/schedules/{schedule_id}", response_model=DoctorScheduleRead)
async def update_doctor_schedule(
    doctor_id: UUID,
    schedule_id: UUID,
    payload: DoctorScheduleUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> DoctorScheduleRead:
    service = DoctorService(db)
    return await service.update_schedule(doctor_id, schedule_id, payload, clinic_id=clinic_id, actor=current_user)


@router.delete("/{doctor_id}/schedules/{schedule_id}", status_code=204)
async def delete_doctor_schedule(
    doctor_id: UUID,
    schedule_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> None:
    service = DoctorService(db)
    await service.delete_schedule(doctor_id, schedule_id, clinic_id=clinic_id, actor=current_user)
