"""Department CRUD endpoints, tenant-scoped and role-gated."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import TTL_DEPARTMENTS_SECONDS, cache_get, cache_invalidate_prefix, cache_set
from app.core.dependencies import (
    get_db,
    require_clinic_context,
    require_config_manage_role,
    require_config_view_role,
)
from app.models.user import User
from app.schemas.department import (
    DepartmentCreate,
    DepartmentListResponse,
    DepartmentRead,
    DepartmentSearchParams,
    DepartmentUpdate,
)
from app.services.department_service import DepartmentService

router = APIRouter(prefix="/departments", tags=["departments"])


def _departments_cache_prefix(clinic_id: UUID) -> str:
    return f"departments:{clinic_id}:"


@router.get("", response_model=DepartmentListResponse)
async def list_departments(
    q: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> DepartmentListResponse:
    # Phase 16: departments change rarely (an admin edit) but this list is
    # read on nearly every reception/queue screen load, so it's a genuine
    # caching candidate - cache key includes every filter param so different
    # searches/pages never collide, TTL'd short (60s) AND invalidated
    # immediately on create/update/delete below (never just "wait out the
    # TTL"), so an edit is reflected on the very next request, not up to a
    # minute later.
    cache_key = f"{_departments_cache_prefix(clinic_id)}{q}:{status_filter}:{limit}:{offset}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    params = DepartmentSearchParams(q=q, status=status_filter, limit=limit, offset=offset)
    service = DepartmentService(db)
    items, total = await service.search(clinic_id, params)
    result = DepartmentListResponse(
        items=[DepartmentRead.model_validate(i) for i in items], total=total, limit=limit, offset=offset
    )
    cache_set(cache_key, result, ttl_seconds=TTL_DEPARTMENTS_SECONDS)
    return result


@router.get("/{department_id}", response_model=DepartmentRead)
async def get_department(
    department_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> DepartmentRead:
    service = DepartmentService(db)
    return await service.get(department_id, clinic_id)


@router.post("", response_model=DepartmentRead, status_code=201)
async def create_department(
    payload: DepartmentCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> DepartmentRead:
    service = DepartmentService(db)
    result = await service.create(payload, clinic_id=clinic_id, actor=current_user)
    cache_invalidate_prefix(_departments_cache_prefix(clinic_id))
    return result


@router.put("/{department_id}", response_model=DepartmentRead)
async def update_department(
    department_id: UUID,
    payload: DepartmentUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> DepartmentRead:
    service = DepartmentService(db)
    result = await service.update(department_id, payload, clinic_id=clinic_id, actor=current_user)
    cache_invalidate_prefix(_departments_cache_prefix(clinic_id))
    return result


@router.delete("/{department_id}", status_code=204)
async def delete_department(
    department_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> None:
    service = DepartmentService(db)
    await service.delete(department_id, clinic_id=clinic_id, actor=current_user)
    cache_invalidate_prefix(_departments_cache_prefix(clinic_id))


@router.post("/{department_id}/restore", response_model=DepartmentRead)
async def restore_department(
    department_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> DepartmentRead:
    service = DepartmentService(db)
    result = await service.restore(department_id, clinic_id=clinic_id, actor=current_user)
    cache_invalidate_prefix(_departments_cache_prefix(clinic_id))
    return result


@router.post("/seed-defaults", response_model=DepartmentListResponse)
async def seed_default_departments(
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> DepartmentListResponse:
    """Optional convenience for brand-new clinics - seeds the standard
    department set (General Medicine, Pediatrics, ...). 409s if the clinic
    already has departments."""
    service = DepartmentService(db)
    items = await service.seed_defaults(clinic_id, actor=current_user)
    cache_invalidate_prefix(_departments_cache_prefix(clinic_id))
    return DepartmentListResponse(
        items=[DepartmentRead.model_validate(i) for i in items], total=len(items), limit=len(items), offset=0
    )
