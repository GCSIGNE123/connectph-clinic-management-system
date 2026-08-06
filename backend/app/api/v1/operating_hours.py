"""Operating hours endpoints - weekly schedule CRUD per branch."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_db,
    require_clinic_context,
    require_config_manage_role,
    require_config_view_role,
)
from app.models.user import User
from app.schemas.operating_hours import (
    OperatingHoursCreate,
    OperatingHoursListResponse,
    OperatingHoursRead,
    OperatingHoursUpdate,
)
from app.services.operating_hours_service import OperatingHoursService

router = APIRouter(prefix="/operating-hours", tags=["operating-hours"])


@router.get("/branch/{branch_id}", response_model=OperatingHoursListResponse)
async def list_operating_hours(
    branch_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> OperatingHoursListResponse:
    service = OperatingHoursService(db)
    items = await service.list_for_branch(clinic_id, branch_id)
    return OperatingHoursListResponse(items=[OperatingHoursRead.model_validate(i) for i in items], total=len(items))


@router.put("", response_model=OperatingHoursRead)
async def upsert_operating_hours(
    payload: OperatingHoursCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> OperatingHoursRead:
    """Create-or-update the entry for `payload.branch_id` + `payload.day_of_week`."""
    service = OperatingHoursService(db)
    return await service.upsert(payload, clinic_id=clinic_id, actor=current_user)


@router.patch("/{entry_id}", response_model=OperatingHoursRead)
async def update_operating_hours(
    entry_id: UUID,
    payload: OperatingHoursUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> OperatingHoursRead:
    service = OperatingHoursService(db)
    return await service.update(entry_id, payload, clinic_id=clinic_id, actor=current_user)


@router.delete("/{entry_id}", status_code=204)
async def delete_operating_hours(
    entry_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> None:
    service = OperatingHoursService(db)
    await service.delete(entry_id, clinic_id=clinic_id, actor=current_user)
