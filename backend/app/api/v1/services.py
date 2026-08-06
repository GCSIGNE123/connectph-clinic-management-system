"""Services catalog CRUD endpoints, tenant-scoped and role-gated."""

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
from app.schemas.clinic_service import (
    ClinicServiceCreate,
    ClinicServiceListResponse,
    ClinicServiceRead,
    ClinicServiceSearchParams,
    ClinicServiceUpdate,
)
from app.services.clinic_service_catalog_service import ClinicServiceCatalogService

router = APIRouter(prefix="/services", tags=["services"])


@router.get("", response_model=ClinicServiceListResponse)
async def list_services(
    q: str | None = Query(default=None),
    department_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> ClinicServiceListResponse:
    params = ClinicServiceSearchParams(q=q, department_id=department_id, status=status_filter, limit=limit, offset=offset)
    service = ClinicServiceCatalogService(db)
    items, total = await service.search(clinic_id, params)
    return ClinicServiceListResponse(
        items=[ClinicServiceRead.model_validate(i) for i in items], total=total, limit=limit, offset=offset
    )


@router.get("/{service_id}", response_model=ClinicServiceRead)
async def get_service(
    service_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> ClinicServiceRead:
    service = ClinicServiceCatalogService(db)
    return await service.get(service_id, clinic_id)


@router.post("", response_model=ClinicServiceRead, status_code=201)
async def create_service(
    payload: ClinicServiceCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> ClinicServiceRead:
    service = ClinicServiceCatalogService(db)
    return await service.create(payload, clinic_id=clinic_id, actor=current_user)


@router.put("/{service_id}", response_model=ClinicServiceRead)
async def update_service(
    service_id: UUID,
    payload: ClinicServiceUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> ClinicServiceRead:
    service = ClinicServiceCatalogService(db)
    return await service.update(service_id, payload, clinic_id=clinic_id, actor=current_user)


@router.delete("/{service_id}", status_code=204)
async def delete_service(
    service_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> None:
    service = ClinicServiceCatalogService(db)
    await service.delete(service_id, clinic_id=clinic_id, actor=current_user)


@router.post("/{service_id}/restore", response_model=ClinicServiceRead)
async def restore_service(
    service_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> ClinicServiceRead:
    service = ClinicServiceCatalogService(db)
    return await service.restore(service_id, clinic_id=clinic_id, actor=current_user)


@router.post("/seed-defaults", response_model=ClinicServiceListResponse)
async def seed_default_services(
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> ClinicServiceListResponse:
    service = ClinicServiceCatalogService(db)
    items = await service.seed_defaults(clinic_id, actor=current_user)
    return ClinicServiceListResponse(
        items=[ClinicServiceRead.model_validate(i) for i in items], total=len(items), limit=len(items), offset=0
    )
