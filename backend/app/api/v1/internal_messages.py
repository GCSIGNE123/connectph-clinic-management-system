"""Internal staff messaging endpoints (Phase 20, item 14).

Deliberately minimal - any authenticated clinic-staff user (`get_current_user`)
may send/list messages, since the feature is meant for any Receptionist <->
Doctor pair (not role-gated beyond "you're logged into this clinic"); every
query/mutation is further scoped to the caller as sender or recipient in
`InternalMessageService`, so a user still can never read someone else's
conversation.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, require_clinic_context
from app.models.user import User
from app.schemas.internal_message import (
    ConversationUnread,
    InternalMessageCreate,
    InternalMessageListResponse,
    InternalMessageRead,
)
from app.services.internal_message_service import InternalMessageService

router = APIRouter(prefix="/messages", tags=["internal-messages"])


@router.get("/staff-directory")
async def staff_directory(
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Minimal staff picker for the messaging UI - any authenticated clinic
    user may list their own clinic's active staff by id/name/role (no
    email/contact details), since `GET /users` itself is Administrator/Owner
    -only (`require_user_management_role`) and shouldn't be widened just to
    support a recipient dropdown."""
    from app.models.role import Role

    stmt = (
        select(User.id, User.first_name, User.middle_name, User.last_name, Role.name.label("role_name"))
        .join(Role, Role.id == User.role_id)
        .where(User.clinic_id == clinic_id, User.is_deleted.is_(False), User.id != current_user.id)
        .order_by(User.first_name, User.last_name)
    )
    result = await db.execute(stmt)
    return [
        {
            "id": str(row.id),
            "full_name": " ".join(p for p in [row.first_name, row.middle_name, row.last_name] if p),
            "role": row.role_name,
        }
        for row in result.all()
    ]


@router.post("", response_model=InternalMessageRead)
async def send_message(
    payload: InternalMessageCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InternalMessageRead:
    service = InternalMessageService(db)
    return await service.send(
        clinic_id=clinic_id, sender_id=current_user.id, recipient_id=payload.recipient_id, body=payload.body
    )


@router.get("/conversation/{other_user_id}", response_model=InternalMessageListResponse)
async def get_conversation(
    other_user_id: UUID,
    limit: int = 100,
    offset: int = 0,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InternalMessageListResponse:
    service = InternalMessageService(db)
    items, total, unread_count = await service.list_conversation(
        clinic_id=clinic_id, current_user_id=current_user.id, other_user_id=other_user_id, limit=limit, offset=offset
    )
    return InternalMessageListResponse(items=items, total=total, unread_count=unread_count)


@router.get("/unread-by-conversation", response_model=list[ConversationUnread])
async def get_unread_by_conversation(
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ConversationUnread]:
    """Per-conversation unread breakdown (item 6) - powers the notification
    bell's dropdown so clicking one unread conversation doesn't clear
    others'."""
    service = InternalMessageService(db)
    rows = await service.unread_by_conversation(clinic_id=clinic_id, current_user_id=current_user.id)
    return [ConversationUnread(**row) for row in rows]


@router.get("/unread-count")
async def get_unread_count(
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    service = InternalMessageService(db)
    count = await service.unread_count(clinic_id=clinic_id, current_user_id=current_user.id)
    return {"unread_count": count}
