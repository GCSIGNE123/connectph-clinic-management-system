"""Clinic settings + branding service - singleton-per-clinic GET/PUT (the
clinic row itself, extended in Phase 4). See docs/DATABASE.md."""

import secrets
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinic import Clinic
from app.models.user import User
from app.repositories.clinic_repository import ClinicRepository
from app.schemas.clinic import ClinicBrandingUpdate, ClinicSettingsUpdate
from app.services.audit_service import AuditService


class ClinicSettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.clinic_repo = ClinicRepository(session)
        self.audit_service = AuditService(session)

    async def get(self, clinic_id: UUID) -> Clinic:
        clinic = await self.clinic_repo.get_by_id(clinic_id)
        if clinic is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinic not found")
        return clinic

    async def update(self, clinic_id: UUID, payload: ClinicSettingsUpdate, *, actor: User) -> Clinic:
        clinic = await self.get(clinic_id)
        updates = payload.model_dump(exclude_unset=True)

        tier_fields = (
            "medicine_expiry_warning_days_tier1", "medicine_expiry_warning_days_tier2",
            "medicine_expiry_warning_days_tier3", "medicine_expiry_warning_days_tier4",
        )
        if any(f in updates for f in tier_fields):
            merged = [updates.get(f, getattr(clinic, f)) for f in tier_fields]
            if not (merged[0] > merged[1] > merged[2] > merged[3]):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Expiry warning tiers must be strictly descending: tier1 > tier2 > tier3 > tier4",
                )

        clinic = await self.clinic_repo.update(clinic, **updates)

        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="clinic_settings.updated",
            entity_type="clinic", entity_id=str(clinic_id), metadata={"fields": list(updates.keys())},
        )
        await self.session.commit()
        return await self.get(clinic_id)

    async def update_branding(self, clinic_id: UUID, payload: ClinicBrandingUpdate, *, actor: User) -> Clinic:
        clinic = await self.get(clinic_id)
        updates = payload.model_dump(exclude_unset=True)
        clinic = await self.clinic_repo.update(clinic, **updates)

        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="clinic_branding.updated",
            entity_type="clinic", entity_id=str(clinic_id), metadata={"fields": list(updates.keys())},
        )
        await self.session.commit()
        return await self.get(clinic_id)

    async def set_logo(self, clinic_id: UUID, logo_url: str | None, *, actor: User) -> Clinic:
        """Round 7: real logo set/remove, sharing the same audit-log
        convention as `update_branding` above. `logo_url` is either the
        newly-stored file's relative media path or `None` (remove)."""
        clinic = await self.get(clinic_id)
        clinic = await self.clinic_repo.update(clinic, logo_url=logo_url)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id,
            action="clinic_branding.logo_removed" if logo_url is None else "clinic_branding.logo_updated",
            entity_type="clinic", entity_id=str(clinic_id),
        )
        await self.session.commit()
        return await self.get(clinic_id)

    async def request_upload_url(self, clinic_id: UUID, asset: str) -> dict:
        """Presigned-URL stub for logo/favicon/login-background uploads.

        TODO(storage): replace with a real Supabase Storage signed-upload call
        once a project/bucket is provisioned (mirrors PatientService's photo
        upload stub).
        """
        token = secrets.token_urlsafe(24)
        object_path = f"clinics/{clinic_id}/branding/{asset}-{token}.png"
        return {
            "upload_url": f"https://stub.supabase.local/storage/v1/upload/{object_path}",
            "public_url": f"https://stub.supabase.local/storage/v1/object/public/{object_path}",
            "expires_in": 600,
        }
