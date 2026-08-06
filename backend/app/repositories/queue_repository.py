"""Repository for Queue: search/filter, today's queue, duplicate-active check."""

from datetime import date
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.patient import Patient
from app.models.queue import ACTIVE_QUEUE_STATUSES, Queue, QueueStatusHistory
from app.repositories.base import BaseRepository
from app.schemas.queue import QueueSearchParams


class QueueRepository(BaseRepository[Queue]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=Queue)

    async def get_by_id_and_clinic(self, id_: UUID, clinic_id: UUID) -> Queue | None:
        stmt = select(Queue).where(Queue.id == id_, Queue.clinic_id == clinic_id, Queue.is_deleted.is_(False))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def has_active_duplicate(
        self, clinic_id: UUID, *, patient_id: UUID, department_id: UUID, queue_date: date
    ) -> bool:
        stmt = select(func.count()).select_from(Queue).where(
            Queue.clinic_id == clinic_id,
            Queue.patient_id == patient_id,
            Queue.department_id == department_id,
            Queue.queue_date == queue_date,
            Queue.is_deleted.is_(False),
            Queue.status.in_(ACTIVE_QUEUE_STATUSES),
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one()) > 0

    def _base_filters(self, clinic_id: UUID, params: QueueSearchParams):
        filters = [Queue.clinic_id == clinic_id, Queue.is_deleted.is_(False)]
        if params.branch_id is not None:
            filters.append(Queue.branch_id == params.branch_id)
        if params.department_id is not None:
            filters.append(Queue.department_id == params.department_id)
        if params.doctor_id is not None:
            filters.append(Queue.doctor_id == params.doctor_id)
        if params.status is not None:
            filters.append(Queue.status == params.status)
        if params.priority is not None:
            filters.append(Queue.priority == params.priority)
        if params.queue_date is not None:
            filters.append(Queue.queue_date == params.queue_date)
        return filters

    async def search(self, clinic_id: UUID, params: QueueSearchParams) -> tuple[list[Queue], int]:
        filters = self._base_filters(clinic_id, params)

        base_query = select(Queue).where(and_(*filters))
        if params.q:
            like = f"%{params.q.lower()}%"
            base_query = base_query.join(Patient, Patient.id == Queue.patient_id).where(
                (func.lower(Queue.queue_number).like(like))
                | (func.lower(Patient.first_name).like(like))
                | (func.lower(Patient.last_name).like(like))
                | (func.lower(Patient.patient_number).like(like))
                | (func.lower(Patient.mobile_number).like(like))
            )

        count_stmt = select(func.count()).select_from(base_query.subquery())
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = (
            base_query.options(
                selectinload(Queue.patient),
                selectinload(Queue.department),
                selectinload(Queue.doctor),
                selectinload(Queue.service),
            )
            .order_by(Queue.created_at.asc())
            .offset(params.offset)
            .limit(params.limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), total

    async def get_with_relations(self, id_: UUID, clinic_id: UUID) -> Queue | None:
        stmt = (
            select(Queue)
            .where(Queue.id == id_, Queue.clinic_id == clinic_id, Queue.is_deleted.is_(False))
            .options(
                selectinload(Queue.patient),
                selectinload(Queue.department),
                selectinload(Queue.doctor),
                selectinload(Queue.service),
                selectinload(Queue.branch),
                selectinload(Queue.visit),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_history(self, queue_id: UUID, clinic_id: UUID) -> list[QueueStatusHistory]:
        stmt = (
            select(QueueStatusHistory)
            .where(QueueStatusHistory.queue_id == queue_id, QueueStatusHistory.clinic_id == clinic_id)
            .order_by(QueueStatusHistory.changed_at.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    async def add_history(
        self, *, clinic_id: UUID, queue_id: UUID, from_status, to_status, changed_by: UUID | None, note: str | None
    ) -> QueueStatusHistory:
        from datetime import UTC, datetime

        entry = QueueStatusHistory(
            clinic_id=clinic_id,
            queue_id=queue_id,
            from_status=from_status,
            to_status=to_status,
            changed_by=changed_by,
            changed_at=datetime.now(UTC),
            note=note,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def get_active_entity(self, model, id_: UUID, clinic_id: UUID):
        """Fetch a Department/Doctor/ClinicService row scoped to clinic, or None."""
        stmt = select(model).where(model.id == id_, model.clinic_id == clinic_id, model.is_deleted.is_(False))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # --- Phase 12: Owner Dashboard & Reports (Queue Reports) ---

    async def waiting_time_stats(self, clinic_id: UUID, date_from: date, date_to: date) -> dict:
        """Average/longest wait (created -> called) in seconds, real SQL
        aggregation over `Queue.called_at - Queue.created_at`, for every
        ticket that was actually called within the date range."""
        from sqlalchemy import extract

        wait_seconds = extract("epoch", Queue.called_at - Queue.created_at)
        stmt = select(func.avg(wait_seconds), func.max(wait_seconds)).where(
            Queue.clinic_id == clinic_id, Queue.is_deleted.is_(False),
            Queue.queue_date >= date_from, Queue.queue_date <= date_to,
            Queue.called_at.is_not(None),
        )
        row = (await self.session.execute(stmt)).one()
        avg_s, max_s = row[0], row[1]
        return {
            "avg_waiting_seconds": float(avg_s) if avg_s is not None else None,
            "longest_wait_seconds": float(max_s) if max_s is not None else None,
        }

    async def status_counts_in_range(self, clinic_id: UUID, date_from: date, date_to: date) -> dict[str, int]:
        stmt = (
            select(Queue.status, func.count())
            .where(
                Queue.clinic_id == clinic_id, Queue.is_deleted.is_(False),
                Queue.queue_date >= date_from, Queue.queue_date <= date_to,
            )
            .group_by(Queue.status)
        )
        rows = (await self.session.execute(stmt)).all()
        return {r[0].value: int(r[1]) for r in rows}

    async def volume_by_hour(self, clinic_id: UUID, date_from: date, date_to: date) -> list[dict]:
        from sqlalchemy import extract

        hour_col = extract("hour", Queue.created_at)
        stmt = (
            select(hour_col, func.count())
            .where(
                Queue.clinic_id == clinic_id, Queue.is_deleted.is_(False),
                Queue.queue_date >= date_from, Queue.queue_date <= date_to,
            )
            .group_by(hour_col)
            .order_by(hour_col)
        )
        rows = (await self.session.execute(stmt)).all()
        return [{"hour": int(r[0]), "value": int(r[1])} for r in rows]
