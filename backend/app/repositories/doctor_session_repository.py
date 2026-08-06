"""Repository for `DoctorSession` (Client Acceptance Revisions Round 3, item 14)."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.doctor_session import DoctorSession


class DoctorSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_open_for_doctor(self, *, clinic_id: UUID, doctor_id: UUID) -> DoctorSession | None:
        stmt = select(DoctorSession).where(
            DoctorSession.clinic_id == clinic_id,
            DoctorSession.doctor_id == doctor_id,
            DoctorSession.ended_at.is_(None),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_for_doctor_and_date(
        self, *, clinic_id: UUID, doctor_id: UUID, session_date: date
    ) -> DoctorSession | None:
        stmt = select(DoctorSession).where(
            DoctorSession.clinic_id == clinic_id,
            DoctorSession.doctor_id == doctor_id,
            DoctorSession.session_date == session_date,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(
        self, *, clinic_id: UUID, doctor_id: UUID, session_date: date, started_at: datetime, started_by: UUID | None
    ) -> DoctorSession:
        row = DoctorSession(
            clinic_id=clinic_id, doctor_id=doctor_id, session_date=session_date,
            started_at=started_at, started_by=started_by,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def end(self, doctor_session: DoctorSession, *, ended_at: datetime) -> DoctorSession:
        doctor_session.ended_at = ended_at
        await self.session.flush()
        return doctor_session
