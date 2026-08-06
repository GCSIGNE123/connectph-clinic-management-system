"""User CRUD endpoints, tenant-scoped, restricted to Owner/Administrator roles."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_clinic_context, require_user_management_role
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    AdminResetPasswordRequest,
    UserCreate,
    UserListResponse,
    UserRead,
    UserUpdate,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserListResponse)
async def list_users(
    q: str | None = Query(default=None, description="Search by name, email, or username."),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_user_management_role),
) -> UserListResponse:
    service = UserService(db)
    items, total = await service.search_users(clinic_id=clinic_id, query=q, limit=limit, offset=offset)
    return UserListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_user_management_role),
) -> User:
    repo = UserRepository(db)
    user = await repo.get_by_id_and_clinic(user_id, clinic_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user_management_role),
) -> User:
    service = UserService(db)
    return await service.create_user(payload, clinic_id=clinic_id, actor=current_user)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user_management_role),
) -> User:
    service = UserService(db)
    return await service.update_user(user_id, payload, clinic_id=clinic_id, actor=current_user)


@router.post("/{user_id}/disable", response_model=UserRead)
async def disable_user(
    user_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user_management_role),
) -> User:
    service = UserService(db)
    return await service.disable_user(user_id, clinic_id=clinic_id, actor=current_user)


@router.post("/{user_id}/enable", response_model=UserRead)
async def enable_user(
    user_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user_management_role),
) -> User:
    service = UserService(db)
    return await service.enable_user(user_id, clinic_id=clinic_id, actor=current_user)


@router.post("/{user_id}/reset-password", status_code=status.HTTP_200_OK)
async def admin_reset_password(
    user_id: UUID,
    payload: AdminResetPasswordRequest,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user_management_role),
) -> dict[str, str]:
    service = UserService(db)
    await service.admin_reset_password(user_id, payload.new_password, clinic_id=clinic_id, actor=current_user)
    return {"detail": "Password has been reset."}


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_user_management_role),
) -> None:
    repo = UserRepository(db)
    user = await repo.get_by_id_and_clinic(user_id, clinic_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await repo.delete(user, soft=True)
    await db.commit()
