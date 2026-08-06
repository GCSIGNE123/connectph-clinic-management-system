"""Repository for the Department model."""

from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.repositories.base import BaseRepository
from app.schemas.department import DepartmentSearchParams


class DepartmentRepository(BaseRepository[Department]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=Department)

    async def get_by_code(self, code: str, clinic_id: UUID) -> Department | None:
        stmt = select(Department).where(
            Department.clinic_id == clinic_id,
            Department.department_code == code,
            Department.is_deleted.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def search(self, clinic_id: UUID, params: DepartmentSearchParams) -> tuple[list[Department], int]:
        filters = [Department.clinic_id == clinic_id, Department.is_deleted.is_(False)]
        if params.q:
            like = f"%{params.q.lower()}%"
            filters.append(
                or_(
                    func.lower(Department.name).like(like),
                    func.lower(Department.department_code).like(like),
                )
            )
        if params.status:
            filters.append(Department.status == params.status)

        count_stmt = select(func.count()).select_from(Department).where(and_(*filters))
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = (
            select(Department)
            .where(and_(*filters))
            .order_by(Department.name.asc())
            .offset(params.offset)
            .limit(params.limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), total

    async def count_active(self, clinic_id: UUID) -> int:
        stmt = select(func.count()).select_from(Department).where(
            Department.clinic_id == clinic_id, Department.is_deleted.is_(False)
        )
        return int((await self.session.execute(stmt)).scalar_one())
