"""Receptionist Shift Management endpoints (Phase 21).

Role gating (see `core/dependencies.py`): Receptionist can start/view/close
their OWN shift (Owner/Administrator can do the same for anyone's shift,
per the general admin-override pattern used elsewhere). Reopening a closed
shift is Owner/Administrator-only - a Receptionist should never be able to
undo their own shift close.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_db,
    require_clinic_context,
    require_shift_manage_role,
    require_shift_reopen_role,
)
from app.models.user import User
from app.schemas.shift import ShiftClose, ShiftCreate, ShiftDetail
from app.services.shift_service import ShiftService

router = APIRouter(prefix="/shifts", tags=["shifts"])


@router.post("", response_model=ShiftDetail, status_code=201)
async def start_shift(
    payload: ShiftCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_shift_manage_role),
) -> ShiftDetail:
    return await ShiftService(db).start_shift(payload, clinic_id=clinic_id, actor=current_user)


@router.get("/current", response_model=ShiftDetail | None)
async def get_current_shift(
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_shift_manage_role),
) -> ShiftDetail | None:
    return await ShiftService(db).get_current(clinic_id=clinic_id, actor=current_user)


@router.get("/{shift_id}", response_model=ShiftDetail)
async def get_shift(
    shift_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_shift_manage_role),
) -> ShiftDetail:
    return await ShiftService(db).get_shift(shift_id, clinic_id=clinic_id, actor=current_user)


@router.post("/{shift_id}/close", response_model=ShiftDetail)
async def close_shift(
    shift_id: UUID,
    payload: ShiftClose,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_shift_manage_role),
) -> ShiftDetail:
    return await ShiftService(db).close_shift(shift_id, payload, clinic_id=clinic_id, actor=current_user)


@router.post("/{shift_id}/reopen", response_model=ShiftDetail)
async def reopen_shift(
    shift_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_shift_reopen_role),
) -> ShiftDetail:
    return await ShiftService(db).reopen_shift(shift_id, clinic_id=clinic_id, actor=current_user)
