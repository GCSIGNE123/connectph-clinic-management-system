"""Patient CRUD/search/archive endpoints, tenant-scoped and role-gated.

View is available to any authenticated clinic role; add/edit is restricted
to Owner/Administrator/Receptionist/Doctor/Nurse; archive/restore is
restricted to Owner/Administrator/Receptionist (see
`core/dependencies.py::PATIENT_*_ROLES`).
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_db,
    require_clinic_context,
    require_patient_archive_role,
    require_patient_manage_role,
    require_patient_view_role,
)
from app.models.patient import Gender, PatientStatus
from app.models.user import User
from app.repositories.patient_repository import PatientRepository
from app.schemas.patient import (
    PatientCreate,
    PatientCreateResponse,
    PatientListItem,
    PatientListResponse,
    PatientPhotoUploadResponse,
    PatientQrResponse,
    PatientRead,
    PatientSearchParams,
    PatientUpdate,
)
from app.schemas.visit import VisitListResponse
from app.services.patient_service import PatientService
from app.services.visit_service import VisitService

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("", response_model=PatientListResponse)
async def list_patients(
    q: str | None = Query(default=None, description="Search patient number, legacy id, name, mobile, or email."),
    branch_id: UUID | None = Query(default=None),
    gender: Gender | None = Query(default=None),
    status_filter: PatientStatus | None = Query(default=None, alias="status"),
    age_min: int | None = Query(default=None, ge=0, le=150),
    age_max: int | None = Query(default=None, ge=0, le=150),
    registered_from: date | None = Query(default=None),
    registered_to: date | None = Query(default=None),
    last_visit_from: date | None = Query(default=None),
    last_visit_to: date | None = Query(default=None),
    sort: str = Query(default="newest", pattern="^(newest|oldest|alphabetical|recently_visited)$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_patient_view_role),
) -> PatientListResponse:
    params = PatientSearchParams(
        q=q,
        branch_id=branch_id,
        gender=gender,
        status=status_filter,
        age_min=age_min,
        age_max=age_max,
        registered_from=registered_from,
        registered_to=registered_to,
        last_visit_from=last_visit_from,
        last_visit_to=last_visit_to,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    service = PatientService(db)
    items, total = await service.search_patients(clinic_id=clinic_id, params=params)
    return PatientListResponse(
        items=[PatientListItem.model_validate(p) for p in items], total=total, limit=limit, offset=offset
    )


@router.get("/{patient_id}", response_model=PatientRead)
async def get_patient(
    patient_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_patient_view_role),
) -> PatientRead:
    repo = PatientRepository(db)
    patient = await repo.get_by_id_and_clinic(patient_id, clinic_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return patient


@router.post("", response_model=PatientCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_patient(
    payload: PatientCreate,
    override: bool = Query(default=False, description="Bypass duplicate-warning and create anyway."),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_patient_manage_role),
) -> PatientCreateResponse:
    if override and current_user.role.name not in {"Owner", "Administrator"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an Owner or Administrator can override a duplicate warning.",
        )
    service = PatientService(db)
    return await service.create_patient(
        payload, clinic_id=clinic_id, actor=current_user, override_duplicate_warning=override
    )


@router.put("/{patient_id}", response_model=PatientCreateResponse)
async def update_patient(
    patient_id: UUID,
    payload: PatientUpdate,
    override: bool = Query(default=False, description="Bypass duplicate-warning and save anyway."),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_patient_manage_role),
) -> PatientCreateResponse:
    if override and current_user.role.name not in {"Owner", "Administrator"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an Owner or Administrator can override a duplicate warning.",
        )
    service = PatientService(db)
    return await service.update_patient(
        patient_id, payload, clinic_id=clinic_id, actor=current_user, override_duplicate_warning=override
    )


@router.post("/{patient_id}/archive", response_model=PatientRead)
async def archive_patient(
    patient_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_patient_archive_role),
) -> PatientRead:
    service = PatientService(db)
    return await service.archive_patient(patient_id, clinic_id=clinic_id, actor=current_user)


@router.post("/{patient_id}/restore", response_model=PatientRead)
async def restore_patient(
    patient_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_patient_archive_role),
) -> PatientRead:
    service = PatientService(db)
    return await service.restore_patient(patient_id, clinic_id=clinic_id, actor=current_user)


@router.get("/{patient_id}/qr", response_model=PatientQrResponse)
async def get_patient_qr(
    patient_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_patient_view_role),
) -> PatientQrResponse:
    service = PatientService(db)
    pid, qr_code = await service.get_qr(patient_id, clinic_id=clinic_id)
    return PatientQrResponse(patient_id=pid, qr_code=qr_code, payload=qr_code)


@router.get("/{patient_id}/visits", response_model=VisitListResponse)
async def get_patient_visits(
    patient_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_patient_view_role),
) -> VisitListResponse:
    """Paginated visit history for the Patient Details 'Visit History' tab
    (Phase 6). Reuses `VisitService` rather than duplicating query logic."""
    service = VisitService(db)
    items, total = await service.list_for_patient(clinic_id=clinic_id, patient_id=patient_id, limit=limit, offset=offset)
    return VisitListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/{patient_id}/photo", response_model=PatientPhotoUploadResponse)
async def request_patient_photo_upload(
    patient_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_patient_manage_role),
) -> PatientPhotoUploadResponse:
    """Presigned-URL stub for uploading a patient photo to Supabase Storage.
    See `PatientService.request_photo_upload_url` for the TODO covering the
    real Supabase integration + thumbnail generation.
    """
    service = PatientService(db)
    result = await service.request_photo_upload_url(patient_id, clinic_id=clinic_id)
    return PatientPhotoUploadResponse(**result)
