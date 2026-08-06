"""Concurrency-safe, clinic+branch+prefix+date-scoped queue number generation.

Parallel in spirit to `PatientNumberGenerator`/`DoctorCodeGenerator` (see
those modules' docstrings), but backed by the dedicated `queue_counters`
table instead of a `system_settings` JSONB row, because the natural key here
is composite (clinic, branch, prefix, date) and resets every day - modeling
that as a distinct row per bucket is simpler than nesting per-date counters
inside a single JSONB blob.

Concurrency: the counter row is fetched with `SELECT ... FOR UPDATE` inside
the caller's transaction, so two concurrent queue-creation requests for the
same (clinic, branch, prefix, date) bucket serialize on that row rather than
racing on `next_number`.
"""

from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.queue import Queue, QueueCounter


class QueueNumberGenerator:
    """Generates sequential queue numbers like `A001`, scoped by
    (clinic, branch, prefix, date) and reset daily."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_or_create_counter(
        self, clinic_id: UUID, branch_id: UUID, prefix: str, counter_date: date
    ) -> QueueCounter:
        select_stmt = (
            select(QueueCounter)
            .where(
                QueueCounter.clinic_id == clinic_id,
                QueueCounter.branch_id == branch_id,
                QueueCounter.queue_prefix == prefix,
                QueueCounter.counter_date == counter_date,
            )
            .with_for_update()
        )
        result = await self.session.execute(select_stmt)
        counter = result.scalar_one_or_none()
        if counter is not None:
            return counter

        # Row doesn't exist yet: `INSERT ... ON CONFLICT DO NOTHING` avoids
        # ever raising an IntegrityError under a concurrent create (which
        # would poison the caller's transaction), then we re-select with
        # FOR UPDATE - whether we won the insert race or lost it, this
        # picks up the (now-existing) row and holds its lock.
        insert_stmt = (
            pg_insert(QueueCounter)
            .values(
                clinic_id=clinic_id,
                branch_id=branch_id,
                queue_prefix=prefix,
                counter_date=counter_date,
                next_number=1,
            )
            .on_conflict_do_nothing(
                index_elements=["clinic_id", "branch_id", "queue_prefix", "counter_date"]
            )
        )
        await self.session.execute(insert_stmt)
        result = await self.session.execute(select_stmt)
        return result.scalar_one()

    async def next_number(
        self,
        clinic_id: UUID,
        branch_id: UUID,
        prefix: str,
        queue_date: date,
        *,
        padding: int = 3,
        max_daily_queue: int = 200,
    ) -> str:
        # `max_daily_queue` is the per-(clinic, branch, prefix, date) ceiling
        # (Item 13: "up to 200, reset daily"). Enforced here, inside the same
        # `FOR UPDATE`-locked transaction that hands out the number, so a
        # ticket is never created past the limit and numbers are never
        # silently wrapped/reused - the caller gets a clear 409 instead.
        counter = await self._get_or_create_counter(clinic_id, branch_id, prefix, queue_date)

        # Defensive resync: the counter is the source of truth under normal
        # operation, but if it ever falls behind the highest queue_number
        # actually issued for this bucket (e.g. rows created by an older
        # code path, a seed/migration script, or manual data repair that
        # bypassed this generator), blindly trusting `next_number` would
        # hand out a number that already exists - silently reusing it.
        # Re-derive the true max from `queues` itself (every ever-issued
        # number, regardless of status/soft-delete, since numbers must
        # never be freed) while still holding the FOR UPDATE lock on the
        # counter row, and bump forward if the counter is behind.
        max_issued = await self.session.execute(
            select(func.max(Queue.queue_number)).where(
                Queue.clinic_id == clinic_id,
                Queue.branch_id == branch_id,
                Queue.queue_prefix == prefix,
                Queue.queue_date == queue_date,
            )
        )
        max_issued_number = max_issued.scalar_one_or_none()
        if max_issued_number:
            suffix = max_issued_number[len(prefix):]
            try:
                issued_max = int(suffix)
            except ValueError:
                issued_max = 0
            if counter.next_number <= issued_max:
                counter.next_number = issued_max + 1

        next_value = counter.next_number
        if next_value > max_daily_queue:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Daily queue limit reached for prefix '{prefix}' "
                    f"({max_daily_queue} tickets). Cannot create another ticket today."
                ),
            )
        counter.next_number = next_value + 1
        await self.session.flush()
        return f"{prefix}{str(next_value).zfill(padding)}"
