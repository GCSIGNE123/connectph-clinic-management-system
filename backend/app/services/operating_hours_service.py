"""Operating hours service: weekly schedule CRUD per branch (0=Monday..6=Sunday)."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operating_hours import OperatingHours
from app.models.user import User
from app.repositories.operating_hours_repository import OperatingHoursRepository
from app.schemas.operating_hours import OperatingHoursCreate, OperatingHoursUpdate
from app.services.audit_service import AuditService


class OperatingHoursService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = OperatingHoursRepository(session)
        self.audit_service = AuditService(session)

    async def list_for_branch(self, clinic_id: UUID, branch_id: UUID) -> list[OperatingHours]:
        return await self.repo.list_for_branch(clinic_id, branch_id)

    async def upsert(self, payload: OperatingHoursCreate, *, clinic_id: UUID, actor: User) -> OperatingHours:
        existing = await self.repo.get_for_branch_day(clinic_id, payload.branch_id, payload.day_of_week)
        if existing is not None:
            entry = await self.repo.update(existing, **payload.model_dump(exclude={"branch_id", "day_of_week"}))
            action = "operating_hours.updated"
        else:
            entry = await self.repo.create(clinic_id=clinic_id, **payload.model_dump())
            action = "operating_hours.created"

        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action=action,
            entity_type="operating_hours", entity_id=str(entry.id),
            metadata={"branch_id": str(payload.branch_id), "day_of_week": payload.day_of_week},
        )
        await self.session.commit()
        return entry

    async def update(self, entry_id: UUID, payload: OperatingHoursUpdate, *, clinic_id: UUID, actor: User) -> OperatingHours:
        entry = await self.repo.get_by_id_and_clinic(entry_id, clinic_id)
        if entry is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operating hours entry not found")
        updates = payload.model_dump(exclude_unset=True)
        entry = await self.repo.update(entry, **updates)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="operating_hours.updated",
            entity_type="operating_hours", entity_id=str(entry_id),
        )
        await self.session.commit()
        return entry

    async def delete(self, entry_id: UUID, *, clinic_id: UUID, actor: User) -> None:
        entry = await self.repo.get_by_id_and_clinic(entry_id, clinic_id)
        if entry is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operating hours entry not found")
        await self.repo.delete(entry, soft=True)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="operating_hours.deleted",
            entity_type="operating_hours", entity_id=str(entry_id),
        )
        await self.session.commit()
