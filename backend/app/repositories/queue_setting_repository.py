"""Repositories for QueueSetting and PriorityType."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.queue_setting import PriorityType, QueueSetting
from app.repositories.base import BaseRepository


class QueueSettingRepository(BaseRepository[QueueSetting]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=QueueSetting)

    async def get_for_branch(
        self, clinic_id: UUID, branch_id: UUID | None, department_id: UUID | None = None
    ) -> QueueSetting | None:
        stmt = select(QueueSetting).where(
            QueueSetting.clinic_id == clinic_id,
            QueueSetting.branch_id == branch_id,
            QueueSetting.department_id == department_id,
            QueueSetting.is_deleted.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_effective_for_department(
        self, clinic_id: UUID, branch_id: UUID | None, department_id: UUID | None
    ) -> QueueSetting | None:
        """Department-specific setting if one exists, else the branch/clinic default."""
        if department_id is not None:
            specific = await self.get_for_branch(clinic_id, branch_id, department_id)
            if specific is not None:
                return specific
        return await self.get_for_branch(clinic_id, branch_id, None)

    async def list_for_clinic(self, clinic_id: UUID) -> list[QueueSetting]:
        stmt = select(QueueSetting).where(
            QueueSetting.clinic_id == clinic_id, QueueSetting.is_deleted.is_(False)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)


class PriorityTypeRepository(BaseRepository[PriorityType]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=PriorityType)

    async def get_by_code(self, code: str, clinic_id: UUID) -> PriorityType | None:
        stmt = select(PriorityType).where(
            PriorityType.clinic_id == clinic_id,
            PriorityType.code == code,
            PriorityType.is_deleted.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_clinic(self, clinic_id: UUID) -> list[PriorityType]:
        stmt = select(PriorityType).where(
            PriorityType.clinic_id == clinic_id, PriorityType.is_deleted.is_(False)
        ).order_by(PriorityType.label.asc())
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)
