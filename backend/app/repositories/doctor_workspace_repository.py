"""Repository for the Doctor Workspace: today's assigned visits, consultation
sessions, visit locks, and doctor activity log."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.consultation_session import ConsultationSession, ConsultationSessionStatus
from app.models.doctor_activity import DoctorActivity, DoctorActivityType
from app.models.visit import Visit, VisitStatus
from app.models.visit_lock import VisitLock


class DoctorWorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- Visits ---

    async def get_visit(self, visit_id: UUID, clinic_id: UUID) -> Visit | None:
        stmt = (
            select(Visit)
            .where(Visit.id == visit_id, Visit.clinic_id == clinic_id, Visit.is_deleted.is_(False))
            .options(selectinload(Visit.patient), selectinload(Visit.doctor), selectinload(Visit.queue))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def today_visits_for_doctor(
        self, *, clinic_id: UUID, doctor_id: UUID | None, visit_date: date
    ) -> list[Visit]:
        filters = [Visit.clinic_id == clinic_id, Visit.visit_date == visit_date, Visit.is_deleted.is_(False)]
        if doctor_id is not None:
            filters.append(Visit.doctor_id == doctor_id)
        stmt = (
            select(Visit)
            .where(and_(*filters))
            .options(selectinload(Visit.patient), selectinload(Visit.doctor), selectinload(Visit.queue))
            .order_by(Visit.arrival_time.asc().nulls_last(), Visit.created_at.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    async def status_counts(self, *, clinic_id: UUID, doctor_id: UUID | None, visit_date: date) -> dict[str, int]:
        filters = [Visit.clinic_id == clinic_id, Visit.visit_date == visit_date, Visit.is_deleted.is_(False)]
        if doctor_id is not None:
            filters.append(Visit.doctor_id == doctor_id)
        stmt = select(Visit.status, func.count()).where(and_(*filters)).group_by(Visit.status)
        rows = (await self.session.execute(stmt)).all()
        return {status.value: count for status, count in rows}

    # --- Consultation sessions ---

    async def create_session(self, *, clinic_id: UUID, visit_id: UUID, doctor_id: UUID, started_at: datetime) -> ConsultationSession:
        session = ConsultationSession(
            clinic_id=clinic_id, visit_id=visit_id, doctor_id=doctor_id,
            started_at=started_at, status=ConsultationSessionStatus.ACTIVE,
        )
        self.session.add(session)
        await self.session.flush()
        return session

    async def get_active_session(self, visit_id: UUID, clinic_id: UUID) -> ConsultationSession | None:
        stmt = select(ConsultationSession).where(
            ConsultationSession.visit_id == visit_id,
            ConsultationSession.clinic_id == clinic_id,
            ConsultationSession.status == ConsultationSessionStatus.ACTIVE,
            ConsultationSession.is_deleted.is_(False),
        ).order_by(ConsultationSession.started_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def end_session(self, session: ConsultationSession, *, ended_at: datetime) -> ConsultationSession:
        duration = int((ended_at - session.started_at).total_seconds())
        session.ended_at = ended_at
        session.duration_seconds = max(duration, 0)
        session.status = ConsultationSessionStatus.ENDED
        await self.session.flush()
        return session

    async def avg_duration_seconds(self, *, clinic_id: UUID, doctor_id: UUID | None, visit_date: date) -> float | None:
        # Phase 9: `visit_date` is always computed in UTC by the caller
        # (`datetime.now(UTC).date()` in doctor_workspace.py's endpoint).
        # `func.date(...)` on a `timestamptz` column implicitly converts to
        # the DB session's configured timezone before truncating - on a
        # server whose Postgres session timezone isn't UTC (confirmed:
        # this deployment's is `Asia/Kuala_Lumpur`, UTC+8), that silently
        # shifts a session's date by up to a day for roughly a third of
        # every day, excluding today's real sessions from the average.
        # Converting to UTC explicitly before truncating keeps this
        # consistent with the UTC date the caller actually passes in -
        # `Visit.visit_date` (used by `status_counts` above) doesn't have
        # this problem because it's a stored plain `Date` column, not a
        # timezone-sensitive cast of a timestamp.
        filters = [
            ConsultationSession.clinic_id == clinic_id,
            ConsultationSession.status == ConsultationSessionStatus.ENDED,
            ConsultationSession.duration_seconds.is_not(None),
            func.date(func.timezone("UTC", ConsultationSession.started_at)) == visit_date,
        ]
        if doctor_id is not None:
            filters.append(ConsultationSession.doctor_id == doctor_id)
        stmt = select(func.avg(ConsultationSession.duration_seconds)).where(and_(*filters))
        result = (await self.session.execute(stmt)).scalar_one_or_none()
        return float(result) if result is not None else None

    # --- Visit locks ---

    async def get_active_lock(self, visit_id: UUID, clinic_id: UUID) -> VisitLock | None:
        stmt = (
            select(VisitLock)
            .where(VisitLock.visit_id == visit_id, VisitLock.clinic_id == clinic_id, VisitLock.released_at.is_(None))
            .options(selectinload(VisitLock.locked_by_user))
            .order_by(VisitLock.locked_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_lock(self, *, clinic_id: UUID, visit_id: UUID, locked_by: UUID, locked_at: datetime) -> VisitLock:
        lock = VisitLock(clinic_id=clinic_id, visit_id=visit_id, locked_by=locked_by, locked_at=locked_at)
        self.session.add(lock)
        await self.session.flush()
        await self.session.refresh(lock, attribute_names=["locked_by_user"])
        return lock

    async def release_lock(self, lock: VisitLock, *, released_at: datetime) -> None:
        lock.released_at = released_at
        await self.session.flush()

    async def release_all_locks_for_visit(self, visit_id: UUID, clinic_id: UUID, *, released_at: datetime) -> None:
        lock = await self.get_active_lock(visit_id, clinic_id)
        if lock is not None:
            await self.release_lock(lock, released_at=released_at)

    # --- Doctor activity ---

    async def log_activity(
        self,
        *,
        clinic_id: UUID,
        doctor_id: UUID,
        user_id: UUID,
        visit_id: UUID | None,
        activity_type: DoctorActivityType,
        occurred_at: datetime,
        metadata: dict | None = None,
    ) -> DoctorActivity:
        entry = DoctorActivity(
            clinic_id=clinic_id, doctor_id=doctor_id, user_id=user_id, visit_id=visit_id,
            activity_type=activity_type, occurred_at=occurred_at, activity_metadata=metadata,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry
