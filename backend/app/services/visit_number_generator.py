"""Concurrency-safe, clinic+branch+date-scoped visit number generation.

Mirrors `QueueNumberGenerator` (see that module's docstring for the
rationale on why a dedicated counter table is used instead of the
`system_settings` JSONB pattern): the natural key here is composite
(clinic, branch, date) and resets daily, backed by `VisitCounter`.

Format: `VIS-YYYYMMDD-000001` (6-digit zero-padded sequence).

Concurrency: the counter row is fetched with `SELECT ... FOR UPDATE` inside
the caller's transaction, so two concurrent visit-creation requests for the
same (clinic, branch, date) bucket serialize on that row rather than racing
on `next_number`.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visit_counter import VisitCounter

VISIT_NUMBER_PREFIX = "VIS"


class VisitNumberGenerator:
    """Generates sequential visit numbers like `VIS-20260726-000001`,
    scoped by (clinic, branch, date) and reset daily."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_or_create_counter(self, clinic_id: UUID, branch_id: UUID, counter_date: date) -> VisitCounter:
        select_stmt = (
            select(VisitCounter)
            .where(
                VisitCounter.clinic_id == clinic_id,
                VisitCounter.branch_id == branch_id,
                VisitCounter.counter_date == counter_date,
            )
            .with_for_update()
        )
        result = await self.session.execute(select_stmt)
        counter = result.scalar_one_or_none()
        if counter is not None:
            return counter

        insert_stmt = (
            pg_insert(VisitCounter)
            .values(clinic_id=clinic_id, branch_id=branch_id, counter_date=counter_date, next_number=1)
            .on_conflict_do_nothing(index_elements=["clinic_id", "branch_id", "counter_date"])
        )
        await self.session.execute(insert_stmt)
        result = await self.session.execute(select_stmt)
        return result.scalar_one()

    async def next_number(self, clinic_id: UUID, branch_id: UUID, visit_date: date, *, padding: int = 6) -> str:
        counter = await self._get_or_create_counter(clinic_id, branch_id, visit_date)
        next_value = counter.next_number
        counter.next_number = next_value + 1
        await self.session.flush()
        date_part = visit_date.strftime("%Y%m%d")
        return f"{VISIT_NUMBER_PREFIX}-{date_part}-{str(next_value).zfill(padding)}"
