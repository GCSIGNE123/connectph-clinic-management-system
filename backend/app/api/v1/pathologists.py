"""Pathologist master-data CRUD + e-signature endpoints.

Mirrors `api/v1/doctors.py`'s CRUD + signature-upload shape (see that
file's own "Doctor E-Signature" section docstring for why real file bytes
are relayed to local disk rather than a presigned-URL stub). Manage
(create/update/delete/signature) is Owner/Administrator-only
(`require_config_manage_role`) - unlike Doctor signatures, a Pathologist
has no login of their own to self-manage, so there is no ownership-based
carve-out to enforce.
"""

import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_clinic_context, require_config_manage_role, require_config_view_role
from app.core.doctor_signature_storage import PATHOLOGIST_SIGNATURES_UPLOAD_ROOT, resolve_pathologist_signature_path
from app.core.upload_validation import validate_upload_request
from app.models.user import User
from app.schemas.pathologist import PathologistCreate, PathologistListResponse, PathologistRead, PathologistUpdate
from app.services.pathologist_service import PathologistService

router = APIRouter(prefix="/pathologists", tags=["pathologists"])

SIGNATURE_MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB - same cap as Doctor e-signature uploads


@router.get("", response_model=PathologistListResponse)
async def list_pathologists(
    active_only: bool = Query(default=False, alias="activeOnly"),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> PathologistListResponse:
    service = PathologistService(db)
    items, total = await service.list_for_clinic(clinic_id, active_only=active_only)
    return PathologistListResponse(items=[PathologistRead.model_validate(i) for i in items], total=total)


@router.get("/{pathologist_id}", response_model=PathologistRead)
async def get_pathologist(
    pathologist_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> PathologistRead:
    service = PathologistService(db)
    return await service.get(pathologist_id, clinic_id)


@router.post("", response_model=PathologistRead, status_code=201)
async def create_pathologist(
    payload: PathologistCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> PathologistRead:
    service = PathologistService(db)
    return await service.create(payload, clinic_id=clinic_id, actor=current_user)


@router.put("/{pathologist_id}", response_model=PathologistRead)
async def update_pathologist(
    pathologist_id: UUID,
    payload: PathologistUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> PathologistRead:
    service = PathologistService(db)
    return await service.update(pathologist_id, payload, clinic_id=clinic_id, actor=current_user)


@router.delete("/{pathologist_id}", status_code=204)
async def delete_pathologist(
    pathologist_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> None:
    service = PathologistService(db)
    await service.delete(pathologist_id, clinic_id=clinic_id, actor=current_user)


# --- Pathologist E-Signature ---


@router.post("/{pathologist_id}/signature", response_model=PathologistRead)
async def upload_pathologist_signature(
    pathologist_id: UUID,
    file: UploadFile = File(...),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> PathologistRead:
    service = PathologistService(db)
    pathologist = await service.get(pathologist_id, clinic_id)

    file_name = file.filename or "signature.png"
    content = await file.read()
    validate_upload_request(
        file_name=file_name, file_size_bytes=len(content),
        allowed_extensions={".png"}, max_size_bytes=SIGNATURE_MAX_SIZE_BYTES,
    )
    if len(content) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty.")

    replaced = pathologist.signature_url is not None
    stored_filename = f"{uuid.uuid4().hex}.png"
    clinic_dir = PATHOLOGIST_SIGNATURES_UPLOAD_ROOT / str(clinic_id) / str(pathologist_id)
    clinic_dir.mkdir(parents=True, exist_ok=True)
    (clinic_dir / stored_filename).write_bytes(content)

    # Old file (if replacing) intentionally left on disk - a Laboratory
    # order may have already snapshotted the stored filename BEFORE this
    # replace (see migration 0040) and must keep resolving it on reprint.
    return await service.set_signature(
        pathologist_id, clinic_id=clinic_id, actor=current_user, stored_filename=stored_filename, replaced=replaced,
    )


@router.get("/{pathologist_id}/signature/file")
async def get_pathologist_signature_file(
    pathologist_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> FileResponse:
    service = PathologistService(db)
    pathologist = await service.get(pathologist_id, clinic_id)
    if not pathologist.signature_url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This pathologist has no signature configured.")
    file_path = resolve_pathologist_signature_path(clinic_id, pathologist_id, pathologist.signature_url)
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signature file not found")
    return FileResponse(file_path, media_type="image/png", filename="signature.png")


@router.delete("/{pathologist_id}/signature", response_model=PathologistRead)
async def remove_pathologist_signature(
    pathologist_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> PathologistRead:
    service = PathologistService(db)
    return await service.remove_signature(pathologist_id, clinic_id=clinic_id, actor=current_user)
