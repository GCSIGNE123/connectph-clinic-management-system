"""Branch CRUD endpoints, tenant-scoped and role-gated."""

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
from app.schemas.branch import BranchCreate, BranchListResponse, BranchRead, BranchSearchParams, BranchUpdate
from app.services.branch_service import BranchService

router = APIRouter(prefix="/branches", tags=["branches"])


@router.get("", response_model=BranchListResponse)
async def list_branches(
    q: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> BranchListResponse:
    params = BranchSearchParams(q=q, status=status_filter, limit=limit, offset=offset)
    service = BranchService(db)
    items, total = await service.search(clinic_id, params)
    return BranchListResponse(items=[BranchRead.model_validate(i) for i in items], total=total, limit=limit, offset=offset)


@router.get("/{branch_id}", response_model=BranchRead)
async def get_branch(
    branch_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> BranchRead:
    service = BranchService(db)
    return await service.get(branch_id, clinic_id)


@router.post("", response_model=BranchRead, status_code=201)
async def create_branch(
    payload: BranchCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> BranchRead:
    service = BranchService(db)
    return await service.create(payload, clinic_id=clinic_id, actor=current_user)


@router.put("/{branch_id}", response_model=BranchRead)
async def update_branch(
    branch_id: UUID,
    payload: BranchUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> BranchRead:
    service = BranchService(db)
    return await service.update(branch_id, payload, clinic_id=clinic_id, actor=current_user)


@router.delete("/{branch_id}", status_code=204)
async def delete_branch(
    branch_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> None:
    service = BranchService(db)
    await service.delete(branch_id, clinic_id=clinic_id, actor=current_user)


@router.post("/{branch_id}/restore", response_model=BranchRead)
async def restore_branch(
    branch_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> BranchRead:
    service = BranchService(db)
    return await service.restore(branch_id, clinic_id=clinic_id, actor=current_user)
