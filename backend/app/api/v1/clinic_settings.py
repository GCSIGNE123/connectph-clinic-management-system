"""Clinic settings + branding endpoints (singleton-per-clinic, GET/PUT only).

View is available to any authenticated clinic role; writes are restricted to
Owner/Administrator (see `core/dependencies.py::require_config_*_role`).

Round 7 (clinic logo): `POST/DELETE /clinic-settings/logo` are, like
`tv_display.py`'s `/tv-info-content/{id}/image`, real file-relay endpoints
rather than the presigned-URL stub every other upload flow in this app uses
(see `app/core/upload_validation.py`'s docstring) - reusing that exact same
local-disk + `StaticFiles` mount convention (`var/clinic_logo_images/`,
mounted at `/media/clinic-logo` in `app/main.py`) rather than inventing a
new storage mechanism. Unauthenticated read access is required because the
logo must also render on the fully public, no-auth TV Display kiosk
(`GET /public/tv-display/{public_slug}`) - a clinic logo is not sensitive
data, same reasoning `tv_display.py` already documents for its own images.
`Clinic.logo_url` (Phase 4, previously unused - only ever set by the
`ClinicBrandingUpdate` stub) is the ONE shared branding value read by both
the TV Display header and the Laboratory Report header; no separate
TV-only or print-only logo field was introduced.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_db,
    require_clinic_context,
    require_config_manage_role,
    require_config_view_role,
)
from app.core.upload_validation import IMAGE_EXTENSIONS, MAX_IMAGE_SIZE_BYTES
from app.models.user import User
from app.schemas.clinic import (
    BrandingUploadResponse,
    ClinicBrandingUpdate,
    ClinicSettingsRead,
    ClinicSettingsUpdate,
)
from app.services.clinic_settings_service import ClinicSettingsService

router = APIRouter(prefix="/clinic-settings", tags=["clinic-settings"])

# Mirrors tv_display.py's TV_INFO_CONTENT_UPLOAD_ROOT convention exactly.
CLINIC_LOGO_UPLOAD_ROOT = Path(__file__).resolve().parents[3] / "var" / "clinic_logo_images"
CLINIC_LOGO_MEDIA_URL_PREFIX = "/media/clinic-logo"


@router.get("", response_model=ClinicSettingsRead)
async def get_clinic_settings(
    clinic_id=Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_view_role),
) -> ClinicSettingsRead:
    service = ClinicSettingsService(db)
    return await service.get(clinic_id)


@router.put("", response_model=ClinicSettingsRead)
async def update_clinic_settings(
    payload: ClinicSettingsUpdate,
    clinic_id=Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> ClinicSettingsRead:
    service = ClinicSettingsService(db)
    return await service.update(clinic_id, payload, actor=current_user)


@router.patch("/branding", response_model=ClinicSettingsRead)
async def update_clinic_branding(
    payload: ClinicBrandingUpdate,
    clinic_id=Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> ClinicSettingsRead:
    service = ClinicSettingsService(db)
    return await service.update_branding(clinic_id, payload, actor=current_user)


@router.post("/branding/{asset}/upload", response_model=BrandingUploadResponse)
async def request_branding_upload(
    asset: str,
    clinic_id=Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_config_manage_role),
) -> BrandingUploadResponse:
    """Presigned-URL stub. `asset` is one of `logo`, `favicon`, `login-background`.
    Superseded for `logo` specifically by the real `POST /logo` endpoint
    below; left in place unchanged for `favicon`/`login-background`, which
    remain out of scope for this feature."""
    service = ClinicSettingsService(db)
    result = await service.request_upload_url(clinic_id, asset)
    return BrandingUploadResponse(**result)


@router.post("/logo", response_model=ClinicSettingsRead)
async def upload_clinic_logo(
    file: UploadFile = File(...),
    clinic_id=Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> ClinicSettingsRead:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{ext or '(none)'}' is not allowed. Allowed types: {', '.join(sorted(IMAGE_EXTENSIONS))}.",
        )
    content = await file.read()
    if len(content) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File is too large. Maximum allowed size is {MAX_IMAGE_SIZE_BYTES // (1024 * 1024)} MB.",
        )
    if len(content) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty.")

    clinic_dir = CLINIC_LOGO_UPLOAD_ROOT / str(clinic_id)
    clinic_dir.mkdir(parents=True, exist_ok=True)
    # Remove any previously-uploaded logo for this clinic first (same
    # "clear the old file(s) before writing the new one" convention as
    # `tv_display.py::upload_info_content_image`) - a logo is live
    # configuration, never historically snapshotted (see the Round 7
    # implementation report's snapshot-decision section), so there is no
    # reason to keep the old file around once replaced.
    for existing in clinic_dir.glob("logo-*"):
        existing.unlink(missing_ok=True)
    # Random suffix (not just a fixed `logo{ext}` name) so a stale cached
    # copy of the previous logo is never served under the same URL to an
    # already-open TV Display kiosk tab that hasn't refetched yet.
    filename = f"logo-{uuid.uuid4().hex[:8]}{ext}"
    (clinic_dir / filename).write_bytes(content)

    logo_url = f"{CLINIC_LOGO_MEDIA_URL_PREFIX}/{clinic_id}/{filename}"
    service = ClinicSettingsService(db)
    return await service.set_logo(clinic_id, logo_url, actor=current_user)


@router.delete("/logo", response_model=ClinicSettingsRead)
async def remove_clinic_logo(
    clinic_id=Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> ClinicSettingsRead:
    service = ClinicSettingsService(db)
    clinic = await service.get(clinic_id)
    if clinic.logo_url and clinic.logo_url.startswith(CLINIC_LOGO_MEDIA_URL_PREFIX):
        clinic_dir = CLINIC_LOGO_UPLOAD_ROOT / str(clinic_id)
        for existing in clinic_dir.glob("logo-*"):
            existing.unlink(missing_ok=True)
    return await service.set_logo(clinic_id, None, actor=current_user)
