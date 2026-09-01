"""Repository for Visit: search/filter, today's visits, timeline events,
and the patient visit-history projection."""

from datetime import date
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.patient import Patient
from app.models.queue import Queue
from app.models.visit import Visit, VisitTimelineEvent
from app.repositories.base import BaseRepository
from app.schemas.visit import VisitSearchParams


class VisitRepository(BaseRepository[Visit]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=Visit)

    async def get_by_id_and_clinic(self, id_: UUID, clinic_id: UUID) -> Visit | None:
        stmt = select(Visit).where(Visit.id == id_, Visit.clinic_id == clinic_id, Visit.is_deleted.is_(False))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_relations(self, id_: UUID, clinic_id: UUID) -> Visit | None:
        stmt = (
            select(Visit)
            .where(Visit.id == id_, Visit.clinic_id == clinic_id, Visit.is_deleted.is_(False))
            .options(
                selectinload(Visit.patient),
                selectinload(Visit.doctor),
                selectinload(Visit.department),
                selectinload(Visit.service),
                selectinload(Visit.branch),
                selectinload(Visit.queue),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    def _base_filters(self, clinic_id: UUID, params: VisitSearchParams):
        filters = [Visit.clinic_id == clinic_id, Visit.is_deleted.is_(False)]
        if params.branch_id is not None:
            filters.append(Visit.branch_id == params.branch_id)
        if params.patient_id is not None:
            filters.append(Visit.patient_id == params.patient_id)
        if params.doctor_id is not None:
            filters.append(Visit.doctor_id == params.doctor_id)
        if params.department_id is not None:
            filters.append(Visit.department_id == params.department_id)
        if params.status is not None:
            filters.append(Visit.status == params.status)
        if params.visit_type is not None:
            filters.append(Visit.visit_type == params.visit_type)
        if params.date_from is not None:
            filters.append(Visit.visit_date >= params.date_from)
        if params.date_to is not None:
            filters.append(Visit.visit_date <= params.date_to)
        return filters

    async def search(self, clinic_id: UUID, params: VisitSearchParams) -> tuple[list[Visit], int]:
        filters = self._base_filters(clinic_id, params)

        base_query = select(Visit).where(and_(*filters))
        if params.q:
            like = f"%{params.q.lower()}%"
            base_query = base_query.outerjoin(Queue, Queue.id == Visit.queue_id).join(
                Patient, Patient.id == Visit.patient_id
            ).where(
                (func.lower(Visit.visit_number).like(like))
                | (func.lower(Patient.first_name).like(like))
                | (func.lower(Patient.last_name).like(like))
                | (func.lower(Patient.patient_number).like(like))
                | (func.lower(Queue.queue_number).like(like))
            )

        count_stmt = select(func.count()).select_from(base_query.subquery())
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = (
            base_query.options(
                selectinload(Visit.patient),
                selectinload(Visit.doctor),
                selectinload(Visit.department),
                selectinload(Visit.service),
                selectinload(Visit.queue),
            )
            # Sort on the same field the date filter above applies to
            # (visit_date) - previously sorted on created_at, which could
            # disagree with a `date_from`/`date_to` filter on visit_date
            # (e.g. a backdated visit_date). created_at/id are stable
            # tie-breaks for same-day visits.
            .order_by(Visit.visit_date.desc(), Visit.created_at.desc(), Visit.id.desc())
            .offset(params.offset)
            .limit(params.limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), total

    async def list_for_patient(
        self,
        clinic_id: UUID,
        patient_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[list[Visit], int]:
        filters = [
            Visit.clinic_id == clinic_id,
            Visit.patient_id == patient_id,
            Visit.is_deleted.is_(False),
        ]
        if date_from is not None:
            filters.append(Visit.visit_date >= date_from)
        if date_to is not None:
            filters.append(Visit.visit_date <= date_to)
        count_stmt = select(func.count()).select_from(Visit).where(and_(*filters))
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = (
            select(Visit)
            .where(and_(*filters))
            .options(
                selectinload(Visit.patient),
                selectinload(Visit.doctor),
                selectinload(Visit.department),
                selectinload(Visit.service),
                selectinload(Visit.queue),
            )
            .order_by(Visit.visit_date.desc(), Visit.created_at.desc(), Visit.id.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), total

    async def get_timeline(self, visit_id: UUID, clinic_id: UUID) -> list[VisitTimelineEvent]:
        stmt = (
            select(VisitTimelineEvent)
            .where(VisitTimelineEvent.visit_id == visit_id, VisitTimelineEvent.clinic_id == clinic_id)
            .order_by(VisitTimelineEvent.occurred_at.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    async def add_timeline_event(
        self,
        *,
        clinic_id: UUID,
        visit_id: UUID,
        event_type,
        occurred_at,
        recorded_by: UUID | None,
        note: str | None = None,
        metadata: dict | None = None,
    ) -> VisitTimelineEvent:
        entry = VisitTimelineEvent(
            clinic_id=clinic_id,
            visit_id=visit_id,
            event_type=event_type,
            occurred_at=occurred_at,
            recorded_by=recorded_by,
            note=note,
            event_metadata=metadata,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def get_active_entity(self, model, id_: UUID, clinic_id: UUID):
        stmt = select(model).where(model.id == id_, model.clinic_id == clinic_id, model.is_deleted.is_(False))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def today_count(self, clinic_id: UUID, branch_id: UUID, visit_date: date) -> int:
        stmt = select(func.count()).select_from(Visit).where(
            Visit.clinic_id == clinic_id,
            Visit.branch_id == branch_id,
            Visit.visit_date == visit_date,
            Visit.is_deleted.is_(False),
        )
        return int((await self.session.execute(stmt)).scalar_one())

    # --- Phase 12: Owner Dashboard & Reports ---
    # Real SQL GROUP BY/COUNT/AVG aggregation over `visits` - no in-Python
    # row iteration, per the spec's 100k+/1M+ scale note.

    async def status_counts_in_range(self, clinic_id: UUID, date_from: date, date_to: date, branch_id: UUID | None = None) -> dict[str, int]:
        filters = [
            Visit.clinic_id == clinic_id, Visit.is_deleted.is_(False),
            Visit.visit_date >= date_from, Visit.visit_date <= date_to,
        ]
        if branch_id is not None:
            filters.append(Visit.branch_id == branch_id)
        stmt = select(Visit.status, func.count()).where(and_(*filters)).group_by(Visit.status)
        rows = (await self.session.execute(stmt)).all()
        return {r[0].value: int(r[1]) for r in rows}

    async def visit_type_counts_in_range(self, clinic_id: UUID, date_from: date, date_to: date) -> dict[str, int]:
        stmt = (
            select(Visit.visit_type, func.count())
            .where(
                Visit.clinic_id == clinic_id, Visit.is_deleted.is_(False),
                Visit.visit_date >= date_from, Visit.visit_date <= date_to,
            )
            .group_by(Visit.visit_type)
        )
        rows = (await self.session.execute(stmt)).all()
        return {r[0].value: int(r[1]) for r in rows}

    async def distinct_doctors_with_activity(self, clinic_id: UUID, visit_date: date) -> int:
        """"Doctors On Duty": distinct doctors with a Called/InConsultation/
        Completed visit today (an active/today consultation)."""
        from app.models.visit import VisitStatus

        stmt = select(func.count(func.distinct(Visit.doctor_id))).where(
            Visit.clinic_id == clinic_id, Visit.is_deleted.is_(False), Visit.visit_date == visit_date,
            Visit.doctor_id.is_not(None),
            Visit.status.in_([VisitStatus.CALLED, VisitStatus.IN_CONSULTATION, VisitStatus.COMPLETED]),
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def daily_census_series(self, clinic_id: UUID, date_from: date, date_to: date) -> list[dict]:
        """Daily Patient Census: visit counts by day."""
        stmt = (
            select(Visit.visit_date, func.count())
            .where(
                Visit.clinic_id == clinic_id, Visit.is_deleted.is_(False),
                Visit.visit_date >= date_from, Visit.visit_date <= date_to,
            )
            .group_by(Visit.visit_date)
            .order_by(Visit.visit_date)
        )
        rows = (await self.session.execute(stmt)).all()
        return [{"date": r[0].isoformat(), "value": int(r[1])} for r in rows]

    async def monthly_census_series(self, clinic_id: UUID, date_from: date, date_to: date) -> list[dict]:
        """Monthly Patient Census: visit counts by month (YYYY-MM)."""
        month_col = func.to_char(Visit.visit_date, "YYYY-MM")
        stmt = (
            select(month_col, func.count())
            .where(
                Visit.clinic_id == clinic_id, Visit.is_deleted.is_(False),
                Visit.visit_date >= date_from, Visit.visit_date <= date_to,
            )
            .group_by(month_col)
            .order_by(month_col)
        )
        rows = (await self.session.execute(stmt)).all()
        return [{"date": r[0], "value": int(r[1])} for r in rows]

    async def distinct_patient_ids_in_range(self, clinic_id: UUID, date_from: date, date_to: date) -> set[UUID]:
        stmt = select(func.distinct(Visit.patient_id)).where(
            Visit.clinic_id == clinic_id, Visit.is_deleted.is_(False),
            Visit.visit_date >= date_from, Visit.visit_date <= date_to,
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return set(rows)

    async def returning_patient_count(self, clinic_id: UUID, date_from: date, date_to: date) -> int:
        """Patients with more than one visit within the period."""
        subq = (
            select(Visit.patient_id, func.count().label("visit_count"))
            .where(
                Visit.clinic_id == clinic_id, Visit.is_deleted.is_(False),
                Visit.visit_date >= date_from, Visit.visit_date <= date_to,
            )
            .group_by(Visit.patient_id)
            .having(func.count() > 1)
            .subquery()
        )
        stmt = select(func.count()).select_from(subq)
        return int((await self.session.execute(stmt)).scalar_one())

    async def doctor_visit_stats(self, clinic_id: UUID, date_from: date, date_to: date) -> list[dict]:
        """Per-doctor Patients Seen (distinct patients), Completed, Cancelled - for the Doctor Report."""
        from app.models.doctor import Doctor
        from app.models.visit import VisitStatus

        stmt = (
            select(
                Doctor.id, Doctor.first_name, Doctor.last_name,
                func.count(func.distinct(Visit.patient_id)),
                func.count(func.distinct(Visit.id)).filter(Visit.status == VisitStatus.COMPLETED),
                func.count(func.distinct(Visit.id)).filter(Visit.status == VisitStatus.CANCELLED),
            )
            .select_from(Visit)
            .join(Doctor, Doctor.id == Visit.doctor_id)
            .where(
                Visit.clinic_id == clinic_id, Visit.is_deleted.is_(False),
                Visit.visit_date >= date_from, Visit.visit_date <= date_to,
            )
            .group_by(Doctor.id, Doctor.first_name, Doctor.last_name)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            {
                "doctor_id": r[0], "doctor_name": f"{r[1]} {r[2]}".strip(),
                "patients_seen": int(r[3]), "completed": int(r[4]), "cancelled": int(r[5]),
            }
            for r in rows
        ]

    async def avg_consultation_seconds_for_doctor(self, clinic_id: UUID, doctor_id: UUID, date_from: date, date_to: date) -> float | None:
        from sqlalchemy import extract

        duration = extract("epoch", Visit.consultation_end - Visit.consultation_start)
        stmt = select(func.avg(duration)).where(
            Visit.clinic_id == clinic_id, Visit.doctor_id == doctor_id, Visit.is_deleted.is_(False),
            Visit.visit_date >= date_from, Visit.visit_date <= date_to,
            Visit.consultation_start.is_not(None), Visit.consultation_end.is_not(None),
        )
        val = (await self.session.execute(stmt)).scalar_one()
        return float(val) if val is not None else None

    async def recent_timeline_events(self, clinic_id: UUID, limit: int = 50) -> list[VisitTimelineEvent]:
        """Real-time Activity Feed source #1: recent visit-timeline events.
        `VisitTimelineEvent` has no ORM relationship to Visit/Patient, so the
        service layer (`AnalyticsService`) resolves patient/visit display
        names separately rather than adding a new relationship here purely
        for a read-only reporting concern."""
        stmt = (
            select(VisitTimelineEvent)
            .where(VisitTimelineEvent.clinic_id == clinic_id)
            .order_by(VisitTimelineEvent.occurred_at.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)
