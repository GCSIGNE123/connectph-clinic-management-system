"""Repository for the ConsultationRoom model."""

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.models.consultation_room import ConsultationRoom
from app.repositories.base import BaseRepository
from app.schemas.consultation_room import ConsultationRoomSearchParams


class ConsultationRoomRepository(BaseRepository[ConsultationRoom]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=ConsultationRoom)

    async def search(self, clinic_id: UUID, params: ConsultationRoomSearchParams) -> tuple[list[ConsultationRoom], int]:
        filters = [ConsultationRoom.clinic_id == clinic_id, ConsultationRoom.is_deleted.is_(False)]
        if params.q:
            like = f"%{params.q.lower()}%"
            filters.append(
                or_(
                    func.lower(ConsultationRoom.room_name).like(like),
                    func.lower(func.coalesce(ConsultationRoom.room_number, "")).like(like),
                )
            )
        if params.department_id is not None:
            filters.append(ConsultationRoom.department_id == params.department_id)
        if params.branch_id is not None:
            filters.append(ConsultationRoom.branch_id == params.branch_id)
        if params.status:
            filters.append(ConsultationRoom.status == params.status)

        count_stmt = select(func.count()).select_from(ConsultationRoom).where(and_(*filters))
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = (
            select(ConsultationRoom)
            .where(and_(*filters))
            .order_by(ConsultationRoom.room_name.asc())
            .offset(params.offset)
            .limit(params.limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), total
