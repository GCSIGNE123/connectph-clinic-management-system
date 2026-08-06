"""Repositories for Doctor and DoctorSchedule."""

from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.doctor import Doctor, DoctorSchedule
from app.repositories.base import BaseRepository
from app.schemas.doctor import DoctorSearchParams


class DoctorRepository(BaseRepository[Doctor]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=Doctor)

    async def get_by_code(self, code: str, clinic_id: UUID) -> Doctor | None:
        stmt = select(Doctor).where(
            Doctor.clinic_id == clinic_id, Doctor.doctor_code == code, Doctor.is_deleted.is_(False)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def search(self, clinic_id: UUID, params: DoctorSearchParams) -> tuple[list[Doctor], int]:
        filters = [Doctor.clinic_id == clinic_id, Doctor.is_deleted.is_(False)]
        if params.q:
            like = f"%{params.q.lower()}%"
            filters.append(
                or_(
                    func.lower(Doctor.first_name).like(like),
                    func.lower(Doctor.last_name).like(like),
                    func.lower(Doctor.doctor_code).like(like),
                    func.lower(func.coalesce(Doctor.specialization, "")).like(like),
                )
            )
        if params.department_id is not None:
            filters.append(Doctor.department_id == params.department_id)
        if params.branch_id is not None:
            filters.append(Doctor.branch_id == params.branch_id)
        if params.status is not None:
            filters.append(Doctor.status == params.status)

        count_stmt = select(func.count()).select_from(Doctor).where(and_(*filters))
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = (
            select(Doctor)
            .where(and_(*filters))
            .order_by(Doctor.last_name.asc(), Doctor.first_name.asc())
            .offset(params.offset)
            .limit(params.limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), total


class DoctorScheduleRepository(BaseRepository[DoctorSchedule]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=DoctorSchedule)

    async def list_for_doctor(self, doctor_id: UUID, clinic_id: UUID) -> list[DoctorSchedule]:
        stmt = (
            select(DoctorSchedule)
            .where(
                DoctorSchedule.doctor_id == doctor_id,
                DoctorSchedule.clinic_id == clinic_id,
                DoctorSchedule.is_deleted.is_(False),
            )
            .order_by(DoctorSchedule.day_of_week.asc(), DoctorSchedule.start_time.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)
