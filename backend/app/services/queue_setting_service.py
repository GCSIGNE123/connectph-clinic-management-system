"""Queue configuration service (pure configuration - no queue/ticket logic).

Manages per-clinic (and optionally per-branch) QueueSetting rows plus the
per-clinic PriorityType reference list.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.queue_setting import DEFAULT_PRIORITY_TYPES, PriorityType, QueueSetting
from app.models.user import User
from app.repositories.queue_setting_repository import PriorityTypeRepository, QueueSettingRepository
from app.schemas.queue_setting import (
    PriorityTypeCreate,
    PriorityTypeUpdate,
    QueueSettingCreate,
    QueueSettingUpdate,
)
from app.services.audit_service import AuditService


class QueueSettingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = QueueSettingRepository(session)
        self.priority_repo = PriorityTypeRepository(session)
        self.audit_service = AuditService(session)

    async def list_for_clinic(self, clinic_id: UUID) -> list[QueueSetting]:
        return await self.repo.list_for_clinic(clinic_id)

    async def get_or_create_default(self, clinic_id: UUID, branch_id: UUID | None) -> QueueSetting:
        setting = await self.repo.get_for_branch(clinic_id, branch_id)
        if setting is None:
            setting = await self.repo.create(
                clinic_id=clinic_id, branch_id=branch_id, queue_prefix="A",
                max_daily_queue=200, reset_time="00:00:00", allow_walkins=True, allow_priority_lane=True,
            )
            await self.session.commit()
        return setting

    async def upsert(self, payload: QueueSettingCreate, *, clinic_id: UUID, actor: User) -> QueueSetting:
        # Post-RC1 (Multi-Department/Multi-Doctor TV Queue Display): the
        # upsert key is now the full (branch_id, department_id, doctor_id)
        # scope, not just branch_id - so setting a doctor-specific prefix
        # creates/updates that doctor's own row without clobbering the
        # department or clinic-wide default row. Existing callers that never
        # send department_id/doctor_id (both default None) still upsert the
        # clinic/branch-wide row exactly as before.
        existing = await self.repo.get_for_branch(
            clinic_id, payload.branch_id, payload.department_id, payload.doctor_id
        )
        if existing is not None:
            existing = await self.repo.update(
                existing, **payload.model_dump(exclude={"branch_id", "department_id", "doctor_id"})
            )
            action = "queue_setting.updated"
            result = existing
        else:
            result = await self.repo.create(clinic_id=clinic_id, **payload.model_dump())
            action = "queue_setting.created"

        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action=action,
            entity_type="queue_setting", entity_id=str(result.id),
        )
        await self.session.commit()
        return result

    async def update(self, setting_id: UUID, payload: QueueSettingUpdate, *, clinic_id: UUID, actor: User) -> QueueSetting:
        setting = await self.repo.get_by_id_and_clinic(setting_id, clinic_id)
        if setting is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue setting not found")
        updates = payload.model_dump(exclude_unset=True)
        setting = await self.repo.update(setting, **updates)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="queue_setting.updated",
            entity_type="queue_setting", entity_id=str(setting_id), metadata={"fields": list(updates.keys())},
        )
        await self.session.commit()
        return setting

    # --- Priority types ---

    async def list_priority_types(self, clinic_id: UUID) -> list[PriorityType]:
        return await self.priority_repo.list_for_clinic(clinic_id)

    async def create_priority_type(self, payload: PriorityTypeCreate, *, clinic_id: UUID, actor: User) -> PriorityType:
        existing = await self.priority_repo.get_by_code(payload.code, clinic_id)
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Priority type code already in use")
        priority_type = await self.priority_repo.create(clinic_id=clinic_id, **payload.model_dump())
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="priority_type.created",
            entity_type="priority_type", entity_id=str(priority_type.id),
        )
        await self.session.commit()
        return priority_type

    async def update_priority_type(
        self, priority_type_id: UUID, payload: PriorityTypeUpdate, *, clinic_id: UUID, actor: User
    ) -> PriorityType:
        priority_type = await self.priority_repo.get_by_id_and_clinic(priority_type_id, clinic_id)
        if priority_type is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Priority type not found")
        updates = payload.model_dump(exclude_unset=True)
        priority_type = await self.priority_repo.update(priority_type, **updates)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="priority_type.updated",
            entity_type="priority_type", entity_id=str(priority_type_id),
        )
        await self.session.commit()
        return priority_type

    async def delete_priority_type(self, priority_type_id: UUID, *, clinic_id: UUID, actor: User) -> None:
        priority_type = await self.priority_repo.get_by_id_and_clinic(priority_type_id, clinic_id)
        if priority_type is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Priority type not found")
        await self.priority_repo.delete(priority_type, soft=True)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="priority_type.deleted",
            entity_type="priority_type", entity_id=str(priority_type_id),
        )
        await self.session.commit()

    async def seed_default_priority_types(self, clinic_id: UUID, *, actor: User) -> list[PriorityType]:
        created = []
        for entry in DEFAULT_PRIORITY_TYPES:
            existing = await self.priority_repo.get_by_code(entry["code"], clinic_id)
            if existing is not None:
                continue
            priority_type = await self.priority_repo.create(clinic_id=clinic_id, enabled=True, **entry)
            created.append(priority_type)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="priority_type.defaults_seeded",
            entity_type="priority_type", metadata={"count": len(created)},
        )
        await self.session.commit()
        return created
