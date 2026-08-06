"""Holiday calendar CRUD endpoints, tenant-scoped and role-gated."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_db,
    require_clinic_context,
    require_config_manage_role,
    require_config_view_role,
)
from app.models.user import User
from app.schemas.holiday import (
    HolidayCreate,
    HolidayListResponse,
    HolidayRead,
    HolidaySearchParams,
    HolidayUpdate,
)
from app.services.holiday_service import HolidayService

router = APIRouter(prefix="/holidays", tags=["holidays"])


@router.get("", response_model=HolidayListResponse)
async def list_holidays(
    year: int | None = Query(default=None),
    branch_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> HolidayListResponse:
    params = HolidaySearchParams(year=year, branch_id=branch_id, limit=limit, offset=offset)
    service = HolidayService(db)
    items, total = await service.search(clinic_id, params)
    return HolidayListResponse(items=[HolidayRead.model_validate(i) for i in items], total=total, limit=limit, offset=offset)


@router.get("/{holiday_id}", response_model=HolidayRead)
async def get_holiday(
    holiday_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> HolidayRead:
    service = HolidayService(db)
    return await service.get(holiday_id, clinic_id)


@router.post("", response_model=HolidayRead, status_code=201)
async def create_holiday(
    payload: HolidayCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> HolidayRead:
    service = HolidayService(db)
    return await service.create(payload, clinic_id=clinic_id, actor=current_user)


@router.put("/{holiday_id}", response_model=HolidayRead)
async def update_holiday(
    holiday_id: UUID,
    payload: HolidayUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> HolidayRead:
    service = HolidayService(db)
    return await service.update(holiday_id, payload, clinic_id=clinic_id, actor=current_user)


@router.delete("/{holiday_id}", status_code=204)
async def delete_holiday(
    holiday_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> None:
    service = HolidayService(db)
    await service.delete(holiday_id, clinic_id=clinic_id, actor=current_user)


@router.post("/{holiday_id}/restore", response_model=HolidayRead)
async def restore_holiday(
    holiday_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> HolidayRead:
    service = HolidayService(db)
    return await service.restore(holiday_id, clinic_id=clinic_id, actor=current_user)
