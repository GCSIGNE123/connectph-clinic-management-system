"""Holiday calendar service: CRUD, tenant-scoped, audited."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holiday import Holiday
from app.models.user import User
from app.repositories.holiday_repository import HolidayRepository
from app.schemas.holiday import HolidayCreate, HolidaySearchParams, HolidayUpdate
from app.services.audit_service import AuditService


class HolidayService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = HolidayRepository(session)
        self.audit_service = AuditService(session)

    async def search(self, clinic_id: UUID, params: HolidaySearchParams) -> tuple[list[Holiday], int]:
        return await self.repo.search(clinic_id, params)

    async def get(self, holiday_id: UUID, clinic_id: UUID) -> Holiday:
        holiday = await self.repo.get_by_id_and_clinic(holiday_id, clinic_id)
        if holiday is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holiday not found")
        return holiday

    async def create(self, payload: HolidayCreate, *, clinic_id: UUID, actor: User) -> Holiday:
        holiday = await self.repo.create(clinic_id=clinic_id, **payload.model_dump())
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="holiday.created",
            entity_type="holiday", entity_id=str(holiday.id),
        )
        await self.session.commit()
        return holiday

    async def update(self, holiday_id: UUID, payload: HolidayUpdate, *, clinic_id: UUID, actor: User) -> Holiday:
        holiday = await self.get(holiday_id, clinic_id)
        updates = payload.model_dump(exclude_unset=True)
        holiday = await self.repo.update(holiday, **updates)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="holiday.updated",
            entity_type="holiday", entity_id=str(holiday_id), metadata={"fields": list(updates.keys())},
        )
        await self.session.commit()
        return holiday

    async def delete(self, holiday_id: UUID, *, clinic_id: UUID, actor: User) -> None:
        holiday = await self.get(holiday_id, clinic_id)
        await self.repo.delete(holiday, soft=True)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="holiday.deleted",
            entity_type="holiday", entity_id=str(holiday_id),
        )
        await self.session.commit()

    async def restore(self, holiday_id: UUID, *, clinic_id: UUID, actor: User) -> Holiday:
        holiday = await self.repo.get_by_id_and_clinic(holiday_id, clinic_id)
        if holiday is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holiday not found")
        holiday.is_deleted = False
        holiday.deleted_at = None
        await self.session.flush()
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="holiday.restored",
            entity_type="holiday", entity_id=str(holiday_id),
        )
        await self.session.commit()
        return await self.get(holiday.id, clinic_id)
