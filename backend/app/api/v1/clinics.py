"""Clinic CRUD endpoints (foundation stubs)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, require_config_manage_role
from app.models.user import User
from app.repositories.clinic_repository import ClinicRepository
from app.schemas.clinic import ClinicCreate, ClinicRead, ClinicUpdate

router = APIRouter(prefix="/clinics", tags=["clinics"])


@router.get("/{clinic_id}", response_model=ClinicRead)
async def get_clinic(
    clinic_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> ClinicRead:
    repo = ClinicRepository(db)
    clinic = await repo.get_by_id(clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinic not found")
    return clinic


@router.post("", response_model=ClinicRead, status_code=status.HTTP_201_CREATED)
async def create_clinic(payload: ClinicCreate, db: AsyncSession = Depends(get_db)) -> ClinicRead:
    repo = ClinicRepository(db)
    existing = await repo.get_by_slug(payload.slug)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Clinic slug already in use")
    clinic = await repo.create(**payload.model_dump())
    await db.commit()
    return clinic


@router.patch("/{clinic_id}", response_model=ClinicRead)
async def update_clinic(
    clinic_id: UUID,
    payload: ClinicUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_manage_role),
) -> ClinicRead:
    repo = ClinicRepository(db)
    clinic = await repo.get_by_id(clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinic not found")
    updates = payload.model_dump(exclude_unset=True)
    clinic = await repo.update(clinic, **updates)
    await db.commit()
    return clinic


@router.delete("/{clinic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_clinic(
    clinic_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_manage_role),
) -> None:
    repo = ClinicRepository(db)
    clinic = await repo.get_by_id(clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinic not found")
    await repo.delete(clinic, soft=True)
    await db.commit()
