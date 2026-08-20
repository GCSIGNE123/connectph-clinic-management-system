"""Medicine Inventory: Medicine catalog CRUD + nested MedicineBatch CRUD
(Phase 1), plus the nested MedicineStockMovement ledger (Phase 2) -
tenant-scoped and role-gated (see `core/dependencies.py`)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_db,
    require_clinic_context,
    require_inventory_manage_role,
    require_inventory_view_role,
)
from app.models.user import User
from app.schemas.medicine import (
    MedicineBatchCreate,
    MedicineBatchListResponse,
    MedicineBatchRead,
    MedicineBatchUpdate,
    MedicineCreate,
    MedicineListResponse,
    MedicineRead,
    MedicineSearchParams,
    MedicineStockMovementCreate,
    MedicineStockMovementListResponse,
    MedicineStockMovementRead,
    MedicineUpdate,
)
from app.services.medicine_service import MedicineService

router = APIRouter(prefix="/medicines", tags=["medicines"])


@router.get("", response_model=MedicineListResponse)
async def list_medicines(
    q: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_inventory_view_role),
) -> MedicineListResponse:
    params = MedicineSearchParams(q=q, is_active=is_active, limit=limit, offset=offset)
    service = MedicineService(db)
    items, total = await service.search(clinic_id, params)
    return MedicineListResponse(
        items=[MedicineRead.model_validate(i) for i in items], total=total, limit=limit, offset=offset
    )


@router.get("/{medicine_id}", response_model=MedicineRead)
async def get_medicine(
    medicine_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_inventory_view_role),
) -> MedicineRead:
    service = MedicineService(db)
    return await service.get(medicine_id, clinic_id)


@router.post("", response_model=MedicineRead, status_code=201)
async def create_medicine(
    payload: MedicineCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_inventory_manage_role),
) -> MedicineRead:
    service = MedicineService(db)
    return await service.create(payload, clinic_id=clinic_id, actor=current_user)


@router.put("/{medicine_id}", response_model=MedicineRead)
async def update_medicine(
    medicine_id: UUID,
    payload: MedicineUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_inventory_manage_role),
) -> MedicineRead:
    service = MedicineService(db)
    return await service.update(medicine_id, payload, clinic_id=clinic_id, actor=current_user)


@router.delete("/{medicine_id}", status_code=204)
async def delete_medicine(
    medicine_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_inventory_manage_role),
) -> None:
    service = MedicineService(db)
    await service.delete(medicine_id, clinic_id=clinic_id, actor=current_user)


@router.get("/{medicine_id}/batches", response_model=MedicineBatchListResponse)
async def list_medicine_batches(
    medicine_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_inventory_view_role),
) -> MedicineBatchListResponse:
    service = MedicineService(db)
    batches = await service.list_batches(medicine_id, clinic_id=clinic_id)
    return MedicineBatchListResponse(items=[MedicineBatchRead.model_validate(b) for b in batches], total=len(batches))


@router.post("/{medicine_id}/batches", response_model=MedicineBatchRead, status_code=201)
async def create_medicine_batch(
    medicine_id: UUID,
    payload: MedicineBatchCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_inventory_manage_role),
) -> MedicineBatchRead:
    service = MedicineService(db)
    return await service.create_batch(medicine_id, payload, clinic_id=clinic_id, actor=current_user)


@router.put("/{medicine_id}/batches/{batch_id}", response_model=MedicineBatchRead)
async def update_medicine_batch(
    medicine_id: UUID,
    batch_id: UUID,
    payload: MedicineBatchUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_inventory_manage_role),
) -> MedicineBatchRead:
    service = MedicineService(db)
    return await service.update_batch(medicine_id, batch_id, payload, clinic_id=clinic_id, actor=current_user)


@router.get("/{medicine_id}/batches/{batch_id}/movements", response_model=MedicineStockMovementListResponse)
async def list_batch_movements(
    medicine_id: UUID,
    batch_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_inventory_view_role),
) -> MedicineStockMovementListResponse:
    service = MedicineService(db)
    movements = await service.list_movements(medicine_id, batch_id, clinic_id=clinic_id)
    return MedicineStockMovementListResponse(
        items=[MedicineStockMovementRead.model_validate(m) for m in movements], total=len(movements)
    )


@router.post("/{medicine_id}/batches/{batch_id}/movements", response_model=MedicineStockMovementRead, status_code=201)
async def create_batch_movement(
    medicine_id: UUID,
    batch_id: UUID,
    payload: MedicineStockMovementCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_inventory_manage_role),
) -> MedicineStockMovementRead:
    service = MedicineService(db)
    movement = await service.create_movement(medicine_id, batch_id, payload, clinic_id=clinic_id, actor=current_user)
    return MedicineStockMovementRead.model_validate(movement)
