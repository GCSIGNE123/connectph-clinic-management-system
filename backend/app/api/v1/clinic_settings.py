"""Clinic settings + branding endpoints (singleton-per-clinic, GET/PUT only).

View is available to any authenticated clinic role; writes are restricted to
Owner/Administrator (see `core/dependencies.py::require_config_*_role`).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_db,
    require_clinic_context,
    require_config_manage_role,
    require_config_view_role,
)
from app.models.user import User
from app.schemas.clinic import (
    BrandingUploadResponse,
    ClinicBrandingUpdate,
    ClinicSettingsRead,
    ClinicSettingsUpdate,
)
from app.services.clinic_settings_service import ClinicSettingsService

router = APIRouter(prefix="/clinic-settings", tags=["clinic-settings"])


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
    """Presigned-URL stub. `asset` is one of `logo`, `favicon`, `login-background`."""
    service = ClinicSettingsService(db)
    result = await service.request_upload_url(clinic_id, asset)
    return BrandingUploadResponse(**result)
