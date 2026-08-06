"""Concurrency-safe, clinic+date-scoped invoice number generation.

Mirrors `VisitNumberGenerator`/`QueueNumberGenerator` (see those modules'
docstrings for the rationale on the dedicated-counter-table pattern).
Invoices are not branch-scoped in their numbering (clinic-wide sequence,
since the cashier workflow spans the whole clinic, not per-branch queues).

Format: `INV-YYYYMMDD-000001` (6-digit zero-padded sequence, resets daily).
"""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice_counter import InvoiceCounter

INVOICE_NUMBER_PREFIX = "INV"


class InvoiceNumberGenerator:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_or_create_counter(self, clinic_id: UUID, counter_date: date) -> InvoiceCounter:
        select_stmt = (
            select(InvoiceCounter)
            .where(InvoiceCounter.clinic_id == clinic_id, InvoiceCounter.counter_date == counter_date)
            .with_for_update()
        )
        result = await self.session.execute(select_stmt)
        counter = result.scalar_one_or_none()
        if counter is not None:
            return counter

        insert_stmt = (
            pg_insert(InvoiceCounter)
            .values(clinic_id=clinic_id, counter_date=counter_date, next_number=1)
            .on_conflict_do_nothing(index_elements=["clinic_id", "counter_date"])
        )
        await self.session.execute(insert_stmt)
        result = await self.session.execute(select_stmt)
        return result.scalar_one()

    async def next_number(self, clinic_id: UUID, invoice_date: date, *, padding: int = 6) -> str:
        counter = await self._get_or_create_counter(clinic_id, invoice_date)
        next_value = counter.next_number
        counter.next_number = next_value + 1
        await self.session.flush()
        date_part = invoice_date.strftime("%Y%m%d")
        return f"{INVOICE_NUMBER_PREFIX}-{date_part}-{str(next_value).zfill(padding)}"
