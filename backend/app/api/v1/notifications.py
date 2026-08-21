"""Phase 3 notification endpoints - tenant-scoped, role-gated
(`INVENTORY_NOTIFICATION_ROLES`), and per-user read state enforced entirely
server-side (see `NotificationService`)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_clinic_context, require_inventory_notification_role
from app.models.user import User
from app.schemas.notification import (
    NotificationListResponse,
    NotificationMarkAllReadResponse,
    NotificationRead,
    NotificationUnreadCountResponse,
)
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_inventory_notification_role),
) -> NotificationListResponse:
    service = NotificationService(db)
    items, total = await service.list_for_user(clinic_id=clinic_id, user=current_user, limit=limit, offset=offset)
    return NotificationListResponse(items=[NotificationRead(**i) for i in items], total=total)


@router.get("/unread-count", response_model=NotificationUnreadCountResponse)
async def get_unread_count(
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_inventory_notification_role),
) -> NotificationUnreadCountResponse:
    service = NotificationService(db)
    count = await service.unread_count(clinic_id=clinic_id, user=current_user)
    return NotificationUnreadCountResponse(unread_count=count)


@router.post("/{notification_id}/read", status_code=204)
async def mark_notification_read(
    notification_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_inventory_notification_role),
) -> None:
    service = NotificationService(db)
    await service.mark_read(notification_id, clinic_id=clinic_id, user=current_user)


@router.post("/read-all", response_model=NotificationMarkAllReadResponse)
async def mark_all_notifications_read(
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_inventory_notification_role),
) -> NotificationMarkAllReadResponse:
    service = NotificationService(db)
    count = await service.mark_all_read(clinic_id=clinic_id, user=current_user)
    return NotificationMarkAllReadResponse(marked_count=count)
