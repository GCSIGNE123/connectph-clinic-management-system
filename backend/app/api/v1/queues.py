"""Reception queue endpoints: create/list/detail/status-transition/edit/
cancel/slip, tenant-scoped and role-gated. See `core/dependencies.py`
(`QUEUE_*_ROLES`) for the exact role matrix.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_db,
    require_clinic_context,
    require_queue_manage_role,
    require_queue_transition_role,
    require_queue_view_role,
)
from app.models.queue import QueuePriority, QueueStatus
from app.models.user import User
from app.schemas.queue import (
    QueueCreate,
    QueueDetail,
    QueueListResponse,
    QueueSearchParams,
    QueueSlip,
    QueueStatusUpdate,
    QueueUpdate,
)
from app.services.queue_service import QueueService

router = APIRouter(prefix="/queues", tags=["queues"])


@router.get("", response_model=QueueListResponse)
async def list_queues(
    q: str | None = Query(default=None, description="Search queue number or patient name/number/mobile."),
    branch_id: UUID | None = Query(default=None),
    department_id: UUID | None = Query(default=None),
    doctor_id: UUID | None = Query(default=None),
    status_filter: QueueStatus | None = Query(default=None, alias="status"),
    priority: QueuePriority | None = Query(default=None),
    queue_date: date | None = Query(default=None, description="Defaults to today's queue when omitted server-side."),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_queue_view_role),
) -> QueueListResponse:
    params = QueueSearchParams(
        q=q, branch_id=branch_id, department_id=department_id, doctor_id=doctor_id,
        status=status_filter, priority=priority, queue_date=queue_date, limit=limit, offset=offset,
    )
    service = QueueService(db)
    items, total = await service.search(clinic_id=clinic_id, params=params)
    return QueueListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{queue_id}", response_model=QueueDetail)
async def get_queue(
    queue_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_queue_view_role),
) -> QueueDetail:
    service = QueueService(db)
    return await service.get_detail(queue_id, clinic_id=clinic_id)


@router.post("", response_model=QueueDetail, status_code=status.HTTP_201_CREATED)
async def create_queue(
    payload: QueueCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_queue_manage_role),
) -> QueueDetail:
    service = QueueService(db)
    return await service.create_queue(payload, clinic_id=clinic_id, actor=current_user)


@router.patch("/{queue_id}", response_model=QueueDetail)
async def update_queue(
    queue_id: UUID,
    payload: QueueUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_queue_manage_role),
) -> QueueDetail:
    service = QueueService(db)
    return await service.update_queue(queue_id, payload, clinic_id=clinic_id, actor=current_user)


@router.patch("/{queue_id}/status", response_model=QueueDetail)
async def update_queue_status(
    queue_id: UUID,
    payload: QueueStatusUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_queue_transition_role),
) -> QueueDetail:
    service = QueueService(db)
    return await service.change_status(
        queue_id, clinic_id=clinic_id, actor=current_user, new_status=payload.status, note=payload.note
    )


@router.post("/{queue_id}/cancel", response_model=QueueDetail)
async def cancel_queue(
    queue_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_queue_manage_role),
) -> QueueDetail:
    service = QueueService(db)
    return await service.cancel(queue_id, clinic_id=clinic_id, actor=current_user)


@router.get("/{queue_id}/slip", response_model=QueueSlip)
async def get_queue_slip(
    queue_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_queue_view_role),
) -> QueueSlip:
    service = QueueService(db)
    return await service.get_slip(queue_id, clinic_id=clinic_id)
