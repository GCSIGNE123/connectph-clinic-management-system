"""Repository for the Medicine (catalog) model."""

from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medicine import Medicine
from app.repositories.base import BaseRepository
from app.schemas.medicine import MedicineSearchParams


class MedicineRepository(BaseRepository[Medicine]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=Medicine)

    async def search(self, clinic_id: UUID, params: MedicineSearchParams) -> tuple[list[Medicine], int]:
        filters = [Medicine.clinic_id == clinic_id, Medicine.is_deleted.is_(False)]
        if params.q:
            like = f"%{params.q.lower()}%"
            filters.append(
                or_(
                    func.lower(Medicine.generic_name).like(like),
                    func.lower(Medicine.brand_name).like(like),
                )
            )
        if params.is_active is not None:
            filters.append(Medicine.is_active.is_(params.is_active))

        count_stmt = select(func.count()).select_from(Medicine).where(and_(*filters))
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = (
            select(Medicine)
            .where(and_(*filters))
            .order_by(Medicine.generic_name.asc())
            .offset(params.offset)
            .limit(params.limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), total
