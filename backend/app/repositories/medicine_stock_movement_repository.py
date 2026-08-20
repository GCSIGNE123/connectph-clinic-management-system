"""Repository for the MedicineStockMovement (Phase 2) ledger."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.medicine import MedicineStockMovement
from app.repositories.base import BaseRepository


class MedicineStockMovementRepository(BaseRepository[MedicineStockMovement]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=MedicineStockMovement)

    async def get_by_id_with_actor(self, movement_id: UUID, clinic_id: UUID) -> MedicineStockMovement | None:
        stmt = (
            select(MedicineStockMovement)
            .where(MedicineStockMovement.id == movement_id, MedicineStockMovement.clinic_id == clinic_id)
            .options(selectinload(MedicineStockMovement.performed_by_user))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_batch(self, batch_id: UUID, clinic_id: UUID) -> list[MedicineStockMovement]:
        # Reverse chronological (newest first) - consistently, per the
        # Phase 2 spec's "Show stock history in ... order consistently".
        stmt = (
            select(MedicineStockMovement)
            .where(MedicineStockMovement.batch_id == batch_id, MedicineStockMovement.clinic_id == clinic_id)
            .options(selectinload(MedicineStockMovement.performed_by_user))
            .order_by(MedicineStockMovement.created_at.desc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)
