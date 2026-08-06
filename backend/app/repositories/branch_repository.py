"""Repository for the Branch model: tenant-scoped search/filter/paginate."""

from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.branch import Branch
from app.repositories.base import BaseRepository
from app.schemas.branch import BranchSearchParams


class BranchRepository(BaseRepository[Branch]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=Branch)

    async def get_by_code(self, code: str, clinic_id: UUID) -> Branch | None:
        stmt = select(Branch).where(
            Branch.clinic_id == clinic_id, Branch.code == code, Branch.is_deleted.is_(False)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def search(self, clinic_id: UUID, params: BranchSearchParams) -> tuple[list[Branch], int]:
        filters = [Branch.clinic_id == clinic_id, Branch.is_deleted.is_(False)]
        if params.q:
            like = f"%{params.q.lower()}%"
            filters.append(
                or_(
                    func.lower(Branch.name).like(like),
                    func.lower(func.coalesce(Branch.code, "")).like(like),
                    func.lower(func.coalesce(Branch.address, "")).like(like),
                )
            )
        if params.status:
            filters.append(Branch.status == params.status)

        count_stmt = select(func.count()).select_from(Branch).where(and_(*filters))
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = (
            select(Branch)
            .where(and_(*filters))
            .order_by(Branch.name.asc())
            .offset(params.offset)
            .limit(params.limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), total
