"""Repository for the MedicineBatch model."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medicine import MedicineBatch
from app.repositories.base import BaseRepository


class MedicineBatchRepository(BaseRepository[MedicineBatch]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=MedicineBatch)

    async def get_by_number(self, medicine_id: UUID, batch_number: str, clinic_id: UUID) -> MedicineBatch | None:
        stmt = select(MedicineBatch).where(
            MedicineBatch.clinic_id == clinic_id,
            MedicineBatch.medicine_id == medicine_id,
            MedicineBatch.batch_number == batch_number,
            MedicineBatch.is_deleted.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_medicine(self, medicine_id: UUID, clinic_id: UUID) -> list[MedicineBatch]:
        stmt = (
            select(MedicineBatch)
            .where(
                MedicineBatch.clinic_id == clinic_id,
                MedicineBatch.medicine_id == medicine_id,
                MedicineBatch.is_deleted.is_(False),
            )
            .order_by(MedicineBatch.expiry_date.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)
