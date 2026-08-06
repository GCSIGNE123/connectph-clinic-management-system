"""Read-only endpoint for the fixed set of platform roles.

Roles are global (not clinic-scoped) and seeded once by the initial Alembic
migration (see `app/models/seed.py`). This endpoint exists so the frontend
user-management UI can populate a role picker with real `role_id` values
instead of hardcoding them.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.models.role import Role
from app.models.user import User

router = APIRouter(prefix="/roles", tags=["roles"])


class RoleRead(BaseModel):
    id: UUID
    name: str
    description: str | None = None


class RoleListResponse(BaseModel):
    items: list[RoleRead]


@router.get("", response_model=RoleListResponse)
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> RoleListResponse:
    result = await db.execute(select(Role).order_by(Role.name))
    roles = result.scalars().all()
    return RoleListResponse(items=[RoleRead(id=r.id, name=r.name, description=r.description) for r in roles])
