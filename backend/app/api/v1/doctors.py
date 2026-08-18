"""Doctor CRUD + doctor-schedule sub-routes, tenant-scoped and role-gated."""

import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_db,
    require_clinic_context,
    require_config_manage_role,
    require_config_view_role,
    require_doctor_signature_manage_role,
)
from app.core.doctor_signature_storage import DOCTOR_SIGNATURES_UPLOAD_ROOT, resolve_doctor_signature_path
from app.core.upload_validation import validate_upload_request
from app.models.doctor import DoctorStatus
from app.models.user import User
from app.schemas.doctor import (
    DoctorCreate,
    DoctorListResponse,
    DoctorPhotoUploadResponse,
    DoctorRead,
    DoctorScheduleCreate,
    DoctorScheduleRead,
    DoctorScheduleUpdate,
    DoctorSearchParams,
    DoctorUpdate,
)
from app.services.doctor_service import DoctorService

router = APIRouter(prefix="/doctors", tags=["doctors"])

SIGNATURE_MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB - same cap as other image uploads, no compelling reason to change it


@router.get("", response_model=DoctorListResponse)
async def list_doctors(
    q: str | None = Query(default=None),
    department_id: UUID | None = Query(default=None),
    branch_id: UUID | None = Query(default=None),
    status_filter: DoctorStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> DoctorListResponse:
    params = DoctorSearchParams(
        q=q, department_id=department_id, branch_id=branch_id, status=status_filter, limit=limit, offset=offset
    )
    service = DoctorService(db)
    items, total = await service.search(clinic_id, params)
    return DoctorListResponse(items=[DoctorRead.model_validate(i) for i in items], total=total, limit=limit, offset=offset)


@router.get("/{doctor_id}", response_model=DoctorRead)
async def get_doctor(
    doctor_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> DoctorRead:
    service = DoctorService(db)
    return await service.get(doctor_id, clinic_id)


@router.post("", response_model=DoctorRead, status_code=201)
async def create_doctor(
    payload: DoctorCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> DoctorRead:
    service = DoctorService(db)
    return await service.create(payload, clinic_id=clinic_id, actor=current_user)


@router.put("/{doctor_id}", response_model=DoctorRead)
async def update_doctor(
    doctor_id: UUID,
    payload: DoctorUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> DoctorRead:
    service = DoctorService(db)
    return await service.update(doctor_id, payload, clinic_id=clinic_id, actor=current_user)


@router.delete("/{doctor_id}", status_code=204)
async def delete_doctor(
    doctor_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> None:
    service = DoctorService(db)
    await service.delete(doctor_id, clinic_id=clinic_id, actor=current_user)


@router.post("/{doctor_id}/restore", response_model=DoctorRead)
async def restore_doctor(
    doctor_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> DoctorRead:
    service = DoctorService(db)
    return await service.restore(doctor_id, clinic_id=clinic_id, actor=current_user)


@router.post("/{doctor_id}/photo", response_model=DoctorPhotoUploadResponse)
async def request_doctor_photo_upload(
    doctor_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> DoctorPhotoUploadResponse:
    service = DoctorService(db)
    result = await service.request_photo_upload_url(doctor_id, clinic_id=clinic_id)
    return DoctorPhotoUploadResponse(**result)


# --- Doctor E-Signature ---
#
# Unlike `/photo` above (an unimplemented presigned-URL stub - see its
# docstring in `doctor_service.py`), these relay real file bytes to local
# disk, same reasoning as `consultations.py`'s attachment upload: no
# Supabase project is provisioned for this deployment target. PNG-only
# (product decision - transparency support, no JPEG compression artifacts
# on a legal document), reusing `validate_upload_request` with a
# PNG-specific allow-list rather than the general `validate_image_upload`.


@router.post("/{doctor_id}/signature", response_model=DoctorRead)
async def upload_doctor_signature(
    doctor_id: UUID,
    file: UploadFile = File(...),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor_signature_manage_role),
) -> DoctorRead:
    service = DoctorService(db)
    service.require_signature_manage_permission(doctor_id, current_user=current_user)
    doctor = await service.get(doctor_id, clinic_id)

    file_name = file.filename or "signature.png"
    content = await file.read()
    validate_upload_request(
        file_name=file_name, file_size_bytes=len(content),
        allowed_extensions={".png"}, max_size_bytes=SIGNATURE_MAX_SIZE_BYTES,
    )
    if len(content) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty.")

    replaced = doctor.signature_url is not None
    stored_filename = f"{uuid.uuid4().hex}.png"
    clinic_dir = DOCTOR_SIGNATURES_UPLOAD_ROOT / str(clinic_id) / str(doctor_id)
    clinic_dir.mkdir(parents=True, exist_ok=True)
    (clinic_dir / stored_filename).write_bytes(content)

    # Old file (if replacing) is intentionally left on disk, not deleted -
    # any document row snapshotted its stored filename BEFORE this replace
    # (see migration 0036) and must keep resolving it on reprint.
    updated = await service.set_signature(
        doctor_id, clinic_id=clinic_id, actor=current_user, stored_filename=stored_filename, replaced=replaced,
    )
    return updated


@router.get("/{doctor_id}/signature/file")
async def get_doctor_signature_file(
    doctor_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> FileResponse:
    """Same broad view-role gate as the rest of the Doctor resource
    (`require_config_view_role`) - a configured signature is visible to
    anyone already allowed to see doctor records, exactly like PRC/PTR.
    Never a public/unauthenticated static mount."""
    service = DoctorService(db)
    doctor = await service.get(doctor_id, clinic_id)
    if not doctor.signature_url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This doctor has no signature configured.")
    return _signature_file_response(clinic_id, doctor_id, doctor.signature_url)


@router.delete("/{doctor_id}/signature", response_model=DoctorRead)
async def remove_doctor_signature(
    doctor_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor_signature_manage_role),
) -> DoctorRead:
    service = DoctorService(db)
    service.require_signature_manage_permission(doctor_id, current_user=current_user)
    return await service.remove_signature(doctor_id, clinic_id=clinic_id, actor=current_user)


def _signature_file_response(clinic_id: UUID, doctor_id: UUID, stored_filename: str) -> FileResponse:
    file_path = resolve_doctor_signature_path(clinic_id, doctor_id, stored_filename)
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signature file not found")
    return FileResponse(file_path, media_type="image/png", filename="signature.png")


# --- Doctor schedules (availability windows - no slot/booking logic) ---


@router.get("/{doctor_id}/schedules", response_model=list[DoctorScheduleRead])
async def list_doctor_schedules(
    doctor_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> list[DoctorScheduleRead]:
    service = DoctorService(db)
    schedules = await service.list_schedules(doctor_id, clinic_id=clinic_id)
    return [DoctorScheduleRead.model_validate(s) for s in schedules]


@router.post("/{doctor_id}/schedules", response_model=DoctorScheduleRead, status_code=201)
async def add_doctor_schedule(
    doctor_id: UUID,
    payload: DoctorScheduleCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> DoctorScheduleRead:
    service = DoctorService(db)
    return await service.add_schedule(doctor_id, payload, clinic_id=clinic_id, actor=current_user)


@router.put("/{doctor_id}/schedules/{schedule_id}", response_model=DoctorScheduleRead)
async def update_doctor_schedule(
    doctor_id: UUID,
    schedule_id: UUID,
    payload: DoctorScheduleUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> DoctorScheduleRead:
    service = DoctorService(db)
    return await service.update_schedule(doctor_id, schedule_id, payload, clinic_id=clinic_id, actor=current_user)


@router.delete("/{doctor_id}/schedules/{schedule_id}", status_code=204)
async def delete_doctor_schedule(
    doctor_id: UUID,
    schedule_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> None:
    service = DoctorService(db)
    await service.delete_schedule(doctor_id, schedule_id, clinic_id=clinic_id, actor=current_user)
