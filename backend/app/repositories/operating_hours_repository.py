"""Repository for OperatingHours."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operating_hours import OperatingHours
from app.repositories.base import BaseRepository


class OperatingHoursRepository(BaseRepository[OperatingHours]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=OperatingHours)

    async def get_for_branch_day(self, clinic_id: UUID, branch_id: UUID, day_of_week: int) -> OperatingHours | None:
        stmt = select(OperatingHours).where(
            OperatingHours.clinic_id == clinic_id,
            OperatingHours.branch_id == branch_id,
            OperatingHours.day_of_week == day_of_week,
            OperatingHours.is_deleted.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_branch(self, clinic_id: UUID, branch_id: UUID) -> list[OperatingHours]:
        stmt = (
            select(OperatingHours)
            .where(
                OperatingHours.clinic_id == clinic_id,
                OperatingHours.branch_id == branch_id,
                OperatingHours.is_deleted.is_(False),
            )
            .order_by(OperatingHours.day_of_week.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)
