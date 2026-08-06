"""Consultation Room management service: CRUD + soft-delete/restore, audited."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consultation_room import ConsultationRoom
from app.models.user import User
from app.repositories.consultation_room_repository import ConsultationRoomRepository
from app.schemas.consultation_room import (
    ConsultationRoomCreate,
    ConsultationRoomSearchParams,
    ConsultationRoomUpdate,
)
from app.services.audit_service import AuditService


class ConsultationRoomService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ConsultationRoomRepository(session)
        self.audit_service = AuditService(session)

    async def search(self, clinic_id: UUID, params: ConsultationRoomSearchParams) -> tuple[list[ConsultationRoom], int]:
        return await self.repo.search(clinic_id, params)

    async def get(self, room_id: UUID, clinic_id: UUID) -> ConsultationRoom:
        room = await self.repo.get_by_id_and_clinic(room_id, clinic_id)
        if room is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation room not found")
        return room

    async def create(self, payload: ConsultationRoomCreate, *, clinic_id: UUID, actor: User) -> ConsultationRoom:
        room = await self.repo.create(clinic_id=clinic_id, **payload.model_dump())
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="consultation_room.created",
            entity_type="consultation_room", entity_id=str(room.id),
        )
        await self.session.commit()
        return await self.get(room.id, clinic_id)

    async def update(self, room_id: UUID, payload: ConsultationRoomUpdate, *, clinic_id: UUID, actor: User) -> ConsultationRoom:
        room = await self.get(room_id, clinic_id)
        updates = payload.model_dump(exclude_unset=True)
        room = await self.repo.update(room, **updates)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="consultation_room.updated",
            entity_type="consultation_room", entity_id=str(room_id), metadata={"fields": list(updates.keys())},
        )
        await self.session.commit()
        return await self.get(room.id, clinic_id)

    async def delete(self, room_id: UUID, *, clinic_id: UUID, actor: User) -> None:
        room = await self.get(room_id, clinic_id)
        await self.repo.delete(room, soft=True)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="consultation_room.deleted",
            entity_type="consultation_room", entity_id=str(room_id),
        )
        await self.session.commit()

    async def restore(self, room_id: UUID, *, clinic_id: UUID, actor: User) -> ConsultationRoom:
        room = await self.repo.get_by_id_and_clinic(room_id, clinic_id)
        if room is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation room not found")
        room.is_deleted = False
        room.deleted_at = None
        await self.session.flush()
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="consultation_room.restored",
            entity_type="consultation_room", entity_id=str(room_id),
        )
        await self.session.commit()
        return await self.get(room.id, clinic_id)
