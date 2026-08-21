"""Repository for the Medicine (catalog) model."""

from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.medicine import Medicine
from app.repositories.base import BaseRepository
from app.schemas.medicine import MedicineSearchParams


class MedicineRepository(BaseRepository[Medicine]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=Medicine)

    async def search_with_batches(self, clinic_id: UUID, params: MedicineSearchParams) -> list[Medicine]:
        """Returns every clinic medicine matching `q`/`is_active` (no DB-level
        pagination), batches eager-loaded. Phase 3's `stock_status` filter
        and the per-medicine summary badge both need to inspect every batch
        of every matching medicine, so `MedicineService.search` does the
        actual filtering/pagination in Python over this result - acceptable
        for a single clinic's medicine catalog size; see the Phase 3 report
        for the tradeoff this documents."""
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

        stmt = (
            select(Medicine)
            .where(and_(*filters))
            .options(selectinload(Medicine.batches))
            .order_by(Medicine.generic_name.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    async def list_all_active_with_batches(self, clinic_id: UUID) -> list[Medicine]:
        """Every active, non-deleted medicine with batches eager-loaded -
        used by `MedicineService.get_stats` (dashboard counts)."""
        stmt = (
            select(Medicine)
            .where(Medicine.clinic_id == clinic_id, Medicine.is_deleted.is_(False))
            .options(selectinload(Medicine.batches))
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)
