"""Repository for the ClinicService (services catalog) model."""

from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinic_service import ClinicService
from app.repositories.base import BaseRepository
from app.schemas.clinic_service import ClinicServiceSearchParams


class ClinicServiceRepository(BaseRepository[ClinicService]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=ClinicService)

    async def get_by_code(self, code: str, clinic_id: UUID) -> ClinicService | None:
        stmt = select(ClinicService).where(
            ClinicService.clinic_id == clinic_id,
            ClinicService.service_code == code,
            ClinicService.is_deleted.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def search(self, clinic_id: UUID, params: ClinicServiceSearchParams) -> tuple[list[ClinicService], int]:
        filters = [ClinicService.clinic_id == clinic_id, ClinicService.is_deleted.is_(False)]
        if params.q:
            like = f"%{params.q.lower()}%"
            filters.append(
                or_(
                    func.lower(ClinicService.service_name).like(like),
                    func.lower(ClinicService.service_code).like(like),
                )
            )
        if params.department_id is not None:
            filters.append(ClinicService.department_id == params.department_id)
        if params.status:
            filters.append(ClinicService.status == params.status)

        count_stmt = select(func.count()).select_from(ClinicService).where(and_(*filters))
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = (
            select(ClinicService)
            .where(and_(*filters))
            .order_by(ClinicService.service_name.asc())
            .offset(params.offset)
            .limit(params.limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), total
