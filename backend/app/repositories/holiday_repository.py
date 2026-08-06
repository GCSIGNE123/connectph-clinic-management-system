"""Repository for the Holiday calendar."""

from uuid import UUID

from sqlalchemy import and_, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holiday import Holiday
from app.repositories.base import BaseRepository
from app.schemas.holiday import HolidaySearchParams


class HolidayRepository(BaseRepository[Holiday]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=Holiday)

    async def search(self, clinic_id: UUID, params: HolidaySearchParams) -> tuple[list[Holiday], int]:
        filters = [Holiday.clinic_id == clinic_id, Holiday.is_deleted.is_(False)]
        if params.year is not None:
            filters.append(extract("year", Holiday.date) == params.year)
        if params.branch_id is not None:
            filters.append(Holiday.branch_id == params.branch_id)

        count_stmt = select(func.count()).select_from(Holiday).where(and_(*filters))
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = (
            select(Holiday)
            .where(and_(*filters))
            .order_by(Holiday.date.asc())
            .offset(params.offset)
            .limit(params.limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), total
