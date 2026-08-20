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

    async def get_for_update(self, batch_id: UUID, medicine_id: UUID, clinic_id: UUID) -> MedicineBatch | None:
        """Locks the batch row (`SELECT ... FOR UPDATE`) for the duration of
        the caller's transaction - same concurrency pattern as
        `VisitNumberGenerator`/`QueueNumberGenerator` - so two concurrent
        stock movements against the same batch serialize on this row
        instead of racing on `quantity_remaining`."""
        stmt = (
            select(MedicineBatch)
            .where(
                MedicineBatch.id == batch_id,
                MedicineBatch.medicine_id == medicine_id,
                MedicineBatch.clinic_id == clinic_id,
                MedicineBatch.is_deleted.is_(False),
            )
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
