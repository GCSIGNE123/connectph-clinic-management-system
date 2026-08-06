"""Consultation Room CRUD endpoints, tenant-scoped and role-gated."""

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
from app.schemas.consultation_room import (
    ConsultationRoomCreate,
    ConsultationRoomListResponse,
    ConsultationRoomRead,
    ConsultationRoomSearchParams,
    ConsultationRoomUpdate,
)
from app.services.consultation_room_service import ConsultationRoomService

router = APIRouter(prefix="/consultation-rooms", tags=["consultation-rooms"])


@router.get("", response_model=ConsultationRoomListResponse)
async def list_consultation_rooms(
    q: str | None = Query(default=None),
    department_id: UUID | None = Query(default=None),
    branch_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> ConsultationRoomListResponse:
    params = ConsultationRoomSearchParams(
        q=q, department_id=department_id, branch_id=branch_id, status=status_filter, limit=limit, offset=offset
    )
    service = ConsultationRoomService(db)
    items, total = await service.search(clinic_id, params)
    return ConsultationRoomListResponse(
        items=[ConsultationRoomRead.model_validate(i) for i in items], total=total, limit=limit, offset=offset
    )


@router.get("/{room_id}", response_model=ConsultationRoomRead)
async def get_consultation_room(
    room_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> ConsultationRoomRead:
    service = ConsultationRoomService(db)
    return await service.get(room_id, clinic_id)


@router.post("", response_model=ConsultationRoomRead, status_code=201)
async def create_consultation_room(
    payload: ConsultationRoomCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> ConsultationRoomRead:
    service = ConsultationRoomService(db)
    return await service.create(payload, clinic_id=clinic_id, actor=current_user)


@router.put("/{room_id}", response_model=ConsultationRoomRead)
async def update_consultation_room(
    room_id: UUID,
    payload: ConsultationRoomUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> ConsultationRoomRead:
    service = ConsultationRoomService(db)
    return await service.update(room_id, payload, clinic_id=clinic_id, actor=current_user)


@router.delete("/{room_id}", status_code=204)
async def delete_consultation_room(
    room_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> None:
    service = ConsultationRoomService(db)
    await service.delete(room_id, clinic_id=clinic_id, actor=current_user)


@router.post("/{room_id}/restore", response_model=ConsultationRoomRead)
async def restore_consultation_room(
    room_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> ConsultationRoomRead:
    service = ConsultationRoomService(db)
    return await service.restore(room_id, clinic_id=clinic_id, actor=current_user)
