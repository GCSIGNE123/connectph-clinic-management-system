"""Pathologist master-data + e-signature management service.

Signature management mirrors `DoctorService`'s e-signature methods
(`set_signature`/`remove_signature`) exactly - same audit-log convention,
same "old file left on disk, not deleted" reasoning (a `LaboratoryOrder`
may have already snapshotted the stored filename at release time - see
migration 0040 - and must keep resolving it on reprint).
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pathologist import Pathologist
from app.models.user import User
from app.repositories.pathologist_repository import PathologistRepository
from app.schemas.pathologist import PathologistCreate, PathologistUpdate
from app.services.audit_service import AuditService


class PathologistService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PathologistRepository(session)
        self.audit_service = AuditService(session)

    async def list_for_clinic(self, clinic_id: UUID, *, active_only: bool = False) -> tuple[list[Pathologist], int]:
        return await self.repo.list_for_clinic(clinic_id, active_only=active_only)

    async def get(self, pathologist_id: UUID, clinic_id: UUID) -> Pathologist:
        pathologist = await self.repo.get_by_id_and_clinic(pathologist_id, clinic_id)
        if pathologist is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pathologist not found")
        return pathologist

    async def create(self, payload: PathologistCreate, *, clinic_id: UUID, actor: User) -> Pathologist:
        pathologist = await self.repo.create(clinic_id=clinic_id, **payload.model_dump())
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="pathologist.created",
            entity_type="pathologist", entity_id=str(pathologist.id),
        )
        await self.session.commit()
        return await self.get(pathologist.id, clinic_id)

    async def update(self, pathologist_id: UUID, payload: PathologistUpdate, *, clinic_id: UUID, actor: User) -> Pathologist:
        pathologist = await self.get(pathologist_id, clinic_id)
        updates = payload.model_dump(exclude_unset=True)
        pathologist = await self.repo.update(pathologist, **updates)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="pathologist.updated",
            entity_type="pathologist", entity_id=str(pathologist_id), metadata={"fields": list(updates.keys())},
        )
        await self.session.commit()
        return await self.get(pathologist.id, clinic_id)

    async def delete(self, pathologist_id: UUID, *, clinic_id: UUID, actor: User) -> None:
        pathologist = await self.get(pathologist_id, clinic_id)
        await self.repo.delete(pathologist, soft=True)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="pathologist.deleted",
            entity_type="pathologist", entity_id=str(pathologist_id),
        )
        await self.session.commit()

    # --- Pathologist e-signature ---

    async def set_signature(
        self, pathologist_id: UUID, *, clinic_id: UUID, actor: User, stored_filename: str, replaced: bool
    ) -> Pathologist:
        pathologist = await self.get(pathologist_id, clinic_id)
        pathologist = await self.repo.update(pathologist, signature_url=stored_filename)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id,
            action="pathologist_signature.replaced" if replaced else "pathologist_signature.added",
            entity_type="pathologist", entity_id=str(pathologist_id), metadata={"stored_filename": stored_filename},
        )
        await self.session.commit()
        return await self.get(pathologist.id, clinic_id)

    async def remove_signature(self, pathologist_id: UUID, *, clinic_id: UUID, actor: User) -> Pathologist:
        pathologist = await self.get(pathologist_id, clinic_id)
        previous = pathologist.signature_url
        pathologist = await self.repo.update(pathologist, signature_url=None)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="pathologist_signature.removed",
            entity_type="pathologist", entity_id=str(pathologist_id), metadata={"stored_filename": previous},
        )
        await self.session.commit()
        return await self.get(pathologist.id, clinic_id)
