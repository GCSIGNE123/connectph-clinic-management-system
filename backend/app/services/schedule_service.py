"""Doctor working-hours schedule + vacation/blocked-date CRUD (Phase 11)."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import DoctorScheduleBlock
from app.models.doctor import Doctor, DoctorSchedule
from app.schemas.appointment import DoctorScheduleBlockCreate, DoctorScheduleOut, DoctorScheduleSet


class ScheduleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _require_doctor(self, doctor_id: UUID, clinic_id: UUID) -> Doctor:
        stmt = select(Doctor).where(Doctor.id == doctor_id, Doctor.clinic_id == clinic_id, Doctor.is_deleted.is_(False))
        doctor = (await self.session.execute(stmt)).scalar_one_or_none()
        if doctor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
        return doctor

    async def get_schedule(self, doctor_id: UUID, *, clinic_id: UUID) -> DoctorScheduleOut:
        await self._require_doctor(doctor_id, clinic_id)
        days_stmt = select(DoctorSchedule).where(
            DoctorSchedule.doctor_id == doctor_id, DoctorSchedule.clinic_id == clinic_id, DoctorSchedule.is_deleted.is_(False)
        ).order_by(DoctorSchedule.day_of_week.asc())
        days = (await self.session.execute(days_stmt)).scalars().all()

        blocks_stmt = select(DoctorScheduleBlock).where(
            DoctorScheduleBlock.doctor_id == doctor_id, DoctorScheduleBlock.clinic_id == clinic_id
        ).order_by(DoctorScheduleBlock.block_date.asc())
        blocks = (await self.session.execute(blocks_stmt)).scalars().all()

        return DoctorScheduleOut(doctor_id=doctor_id, days=list(days), blocks=list(blocks))

    async def set_schedule(self, doctor_id: UUID, payload: DoctorScheduleSet, *, clinic_id: UUID) -> DoctorScheduleOut:
        """Replaces the doctor's recurring weekly schedule wholesale (simple,
        predictable semantics matching how `OperatingHours` is edited)."""
        await self._require_doctor(doctor_id, clinic_id)

        existing_stmt = select(DoctorSchedule).where(
            DoctorSchedule.doctor_id == doctor_id, DoctorSchedule.clinic_id == clinic_id
        )
        existing = (await self.session.execute(existing_stmt)).scalars().all()
        for row in existing:
            await self.session.delete(row)
        await self.session.flush()

        for day in payload.days:
            row = DoctorSchedule(
                clinic_id=clinic_id, doctor_id=doctor_id, branch_id=day.branch_id, day_of_week=day.day_of_week,
                start_time=day.start_time, end_time=day.end_time, lunch_break_start=day.lunch_break_start,
                lunch_break_end=day.lunch_break_end, slot_duration_minutes=day.slot_duration_minutes,
                max_patients_per_day=day.max_patients_per_day, is_active=day.is_active, is_recurring=True,
            )
            self.session.add(row)
        await self.session.commit()
        return await self.get_schedule(doctor_id, clinic_id=clinic_id)

    async def add_block(self, doctor_id: UUID, payload: DoctorScheduleBlockCreate, *, clinic_id: UUID) -> DoctorScheduleOut:
        await self._require_doctor(doctor_id, clinic_id)
        block = DoctorScheduleBlock(
            clinic_id=clinic_id, doctor_id=doctor_id, block_date=payload.block_date,
            block_type=payload.block_type, reason=payload.reason,
        )
        self.session.add(block)
        try:
            await self.session.commit()
        except Exception as exc:  # duplicate block date for this doctor
            await self.session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A block already exists for this doctor on this date.") from exc
        return await self.get_schedule(doctor_id, clinic_id=clinic_id)

    async def remove_block(self, doctor_id: UUID, block_id: UUID, *, clinic_id: UUID) -> DoctorScheduleOut:
        await self._require_doctor(doctor_id, clinic_id)
        stmt = select(DoctorScheduleBlock).where(
            DoctorScheduleBlock.id == block_id, DoctorScheduleBlock.doctor_id == doctor_id, DoctorScheduleBlock.clinic_id == clinic_id
        )
        block = (await self.session.execute(stmt)).scalar_one_or_none()
        if block is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")
        await self.session.delete(block)
        await self.session.commit()
        return await self.get_schedule(doctor_id, clinic_id=clinic_id)
