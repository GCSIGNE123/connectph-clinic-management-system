"""Queue configuration endpoints (pure configuration - no ticket/queue logic)."""

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
from app.schemas.queue_setting import (
    PriorityTypeCreate,
    PriorityTypeListResponse,
    PriorityTypeRead,
    PriorityTypeUpdate,
    QueueSettingCreate,
    QueueSettingListResponse,
    QueueSettingRead,
    QueueSettingUpdate,
)
from app.services.queue_setting_service import QueueSettingService

router = APIRouter(prefix="/queue-settings", tags=["queue-settings"])


@router.get("", response_model=QueueSettingListResponse)
async def list_queue_settings(
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> QueueSettingListResponse:
    service = QueueSettingService(db)
    items = await service.list_for_clinic(clinic_id)
    return QueueSettingListResponse(items=[QueueSettingRead.model_validate(i) for i in items], total=len(items))


@router.put("", response_model=QueueSettingRead)
async def upsert_queue_setting(
    payload: QueueSettingCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> QueueSettingRead:
    """Create-or-update the queue setting for `payload.branch_id` (null = clinic-wide)."""
    service = QueueSettingService(db)
    return await service.upsert(payload, clinic_id=clinic_id, actor=current_user)


@router.patch("/{setting_id}", response_model=QueueSettingRead)
async def update_queue_setting(
    setting_id: UUID,
    payload: QueueSettingUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> QueueSettingRead:
    service = QueueSettingService(db)
    return await service.update(setting_id, payload, clinic_id=clinic_id, actor=current_user)


# --- Priority types ---


@router.get("/priority-types", response_model=PriorityTypeListResponse)
async def list_priority_types(
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> PriorityTypeListResponse:
    service = QueueSettingService(db)
    items = await service.list_priority_types(clinic_id)
    return PriorityTypeListResponse(items=[PriorityTypeRead.model_validate(i) for i in items], total=len(items))


@router.post("/priority-types", response_model=PriorityTypeRead, status_code=201)
async def create_priority_type(
    payload: PriorityTypeCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> PriorityTypeRead:
    service = QueueSettingService(db)
    return await service.create_priority_type(payload, clinic_id=clinic_id, actor=current_user)


@router.put("/priority-types/{priority_type_id}", response_model=PriorityTypeRead)
async def update_priority_type(
    priority_type_id: UUID,
    payload: PriorityTypeUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> PriorityTypeRead:
    service = QueueSettingService(db)
    return await service.update_priority_type(priority_type_id, payload, clinic_id=clinic_id, actor=current_user)


@router.delete("/priority-types/{priority_type_id}", status_code=204)
async def delete_priority_type(
    priority_type_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> None:
    service = QueueSettingService(db)
    await service.delete_priority_type(priority_type_id, clinic_id=clinic_id, actor=current_user)


@router.post("/priority-types/seed-defaults", response_model=PriorityTypeListResponse)
async def seed_default_priority_types(
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> PriorityTypeListResponse:
    service = QueueSettingService(db)
    items = await service.seed_default_priority_types(clinic_id, actor=current_user)
    return PriorityTypeListResponse(items=[PriorityTypeRead.model_validate(i) for i in items], total=len(items))
