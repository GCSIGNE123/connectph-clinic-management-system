"""Services catalog (ClinicService model) management: CRUD + optional default seeding."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinic_service import DEFAULT_SERVICES, ClinicService
from app.models.user import User
from app.repositories.clinic_service_repository import ClinicServiceRepository
from app.schemas.clinic_service import ClinicServiceCreate, ClinicServiceSearchParams, ClinicServiceUpdate
from app.services.audit_service import AuditService


class ClinicServiceCatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ClinicServiceRepository(session)
        self.audit_service = AuditService(session)

    async def search(self, clinic_id: UUID, params: ClinicServiceSearchParams) -> tuple[list[ClinicService], int]:
        return await self.repo.search(clinic_id, params)

    async def get(self, service_id: UUID, clinic_id: UUID) -> ClinicService:
        service = await self.repo.get_by_id_and_clinic(service_id, clinic_id)
        if service is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
        return service

    async def create(self, payload: ClinicServiceCreate, *, clinic_id: UUID, actor: User) -> ClinicService:
        existing = await self.repo.get_by_code(payload.service_code, clinic_id)
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Service code already in use")

        # The check above has a race window - two concurrent creates for the
        # same code (e.g. overlapping CSV imports) can both pass it before
        # either commits. The database's unique constraint is the real
        # guard; without this catch, the second request's flush raises an
        # unhandled IntegrityError that crashes the connection instead of
        # returning the same clean 409 the pre-check already promises.
        try:
            service = await self.repo.create(clinic_id=clinic_id, **payload.model_dump())
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Service code already in use") from None
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="service.created",
            entity_type="service", entity_id=str(service.id),
        )
        await self.session.commit()
        return await self.get(service.id, clinic_id)

    async def update(self, service_id: UUID, payload: ClinicServiceUpdate, *, clinic_id: UUID, actor: User) -> ClinicService:
        service = await self.get(service_id, clinic_id)
        updates = payload.model_dump(exclude_unset=True)
        if "service_code" in updates:
            existing = await self.repo.get_by_code(updates["service_code"], clinic_id)
            if existing is not None and existing.id != service_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Service code already in use")

        try:
            service = await self.repo.update(service, **updates)
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Service code already in use") from None
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="service.updated",
            entity_type="service", entity_id=str(service_id), metadata={"fields": list(updates.keys())},
        )
        await self.session.commit()
        return await self.get(service.id, clinic_id)

    async def delete(self, service_id: UUID, *, clinic_id: UUID, actor: User) -> None:
        service = await self.get(service_id, clinic_id)
        await self.repo.delete(service, soft=True)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="service.deleted",
            entity_type="service", entity_id=str(service_id),
        )
        await self.session.commit()

    async def restore(self, service_id: UUID, *, clinic_id: UUID, actor: User) -> ClinicService:
        service = await self.repo.get_by_id_and_clinic(service_id, clinic_id)
        if service is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
        service.is_deleted = False
        service.deleted_at = None
        await self.session.flush()
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="service.restored",
            entity_type="service", entity_id=str(service_id),
        )
        await self.session.commit()
        return await self.get(service.id, clinic_id)

    async def seed_defaults(self, clinic_id: UUID, *, actor: User) -> list[ClinicService]:
        created = []
        for entry in DEFAULT_SERVICES:
            existing = await self.repo.get_by_code(entry["service_code"], clinic_id)
            if existing is not None:
                continue
            service = await self.repo.create(clinic_id=clinic_id, status="Active", description=None, **entry)
            created.append(service)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="service.defaults_seeded",
            entity_type="service", metadata={"count": len(created)},
        )
        await self.session.commit()
        return created
