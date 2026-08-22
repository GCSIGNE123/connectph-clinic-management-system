"""Repository for the Pathologist master-data resource."""

from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pathologist import Pathologist
from app.repositories.base import BaseRepository


class PathologistRepository(BaseRepository[Pathologist]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=Pathologist)

    async def list_for_clinic(self, clinic_id: UUID, *, active_only: bool = False) -> tuple[list[Pathologist], int]:
        filters = [Pathologist.clinic_id == clinic_id, Pathologist.is_deleted.is_(False)]
        if active_only:
            filters.append(Pathologist.is_active.is_(True))

        count_stmt = select(func.count()).select_from(Pathologist).where(and_(*filters))
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = select(Pathologist).where(and_(*filters)).order_by(Pathologist.name.asc())
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), total
