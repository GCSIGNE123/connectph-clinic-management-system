"""Time Slot Engine (Phase 11).

Computes available appointment slots for a doctor on a given date from:
  DoctorSchedule (weekly availability, lunch break, slot duration)
  minus Holiday (clinic/branch-wide closures, reused from Phase 4)
  minus DoctorScheduleBlock (doctor-specific vacation/blocked dates)
  minus existing non-cancelled Appointments for that doctor/date (no double-booking)

Slots are computed on demand and never persisted - see the module docstring
in `models/appointment.py` for the rationale (`TimeSlot` is a DTO, not a table).
"""

from datetime import date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment, DoctorScheduleBlock
from app.models.doctor import DoctorSchedule
from app.models.holiday import Holiday
from app.schemas.appointment import TimeSlotOut


def _add_minutes(t: time, minutes: int) -> time:
    dt = datetime.combine(date.today(), t) + timedelta(minutes=minutes)
    return dt.time()


class TimeSlotService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_schedule_for_day(
        self, clinic_id: UUID, doctor_id: UUID, on_date: date
    ) -> DoctorSchedule | None:
        day_of_week = on_date.weekday()  # Monday=0 .. Sunday=6, matches our convention
        stmt = select(DoctorSchedule).where(
            DoctorSchedule.clinic_id == clinic_id,
            DoctorSchedule.doctor_id == doctor_id,
            DoctorSchedule.day_of_week == day_of_week,
            DoctorSchedule.is_active.is_(True),
            DoctorSchedule.is_deleted.is_(False),
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        if not rows:
            return None
        # Prefer a non-recurring, date-bounded override row if one applies.
        for row in rows:
            if not row.is_recurring:
                if row.effective_from and on_date < row.effective_from:
                    continue
                if row.effective_to and on_date > row.effective_to:
                    continue
                return row
        return rows[0]

    async def _get_block(self, clinic_id: UUID, doctor_id: UUID, on_date: date) -> DoctorScheduleBlock | None:
        stmt = select(DoctorScheduleBlock).where(
            DoctorScheduleBlock.clinic_id == clinic_id,
            DoctorScheduleBlock.doctor_id == doctor_id,
            DoctorScheduleBlock.block_date == on_date,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _get_holiday(self, clinic_id: UUID, branch_id: UUID | None, on_date: date) -> Holiday | None:
        stmt = select(Holiday).where(
            Holiday.clinic_id == clinic_id,
            Holiday.date == on_date,
            Holiday.is_closed.is_(True),
            Holiday.is_deleted.is_(False),
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        for h in rows:
            if h.branch_id is None or h.branch_id == branch_id:
                return h
        return None

    async def _get_booked_start_times(self, clinic_id: UUID, doctor_id: UUID, on_date: date) -> set[time]:
        from app.models.appointment import NON_BLOCKING_APPOINTMENT_STATUSES

        stmt = select(Appointment.start_time).where(
            Appointment.clinic_id == clinic_id,
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == on_date,
            Appointment.is_deleted.is_(False),
            ~Appointment.status.in_(NON_BLOCKING_APPOINTMENT_STATUSES),
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return set(rows)

    async def get_available_slots(
        self, *, clinic_id: UUID, doctor_id: UUID, branch_id: UUID | None, on_date: date
    ) -> list[TimeSlotOut]:
        holiday = await self._get_holiday(clinic_id, branch_id, on_date)
        if holiday is not None:
            return []

        block = await self._get_block(clinic_id, doctor_id, on_date)
        if block is not None:
            return []

        schedule = await self._get_schedule_for_day(clinic_id, doctor_id, on_date)
        if schedule is None:
            return []

        booked = await self._get_booked_start_times(clinic_id, doctor_id, on_date)

        slots: list[TimeSlotOut] = []
        cursor = schedule.start_time
        duration = schedule.slot_duration_minutes
        count_available = 0
        while True:
            slot_end = _add_minutes(cursor, duration)
            if slot_end > schedule.end_time:
                break
            in_lunch = (
                schedule.lunch_break_start is not None
                and schedule.lunch_break_end is not None
                and cursor >= schedule.lunch_break_start
                and cursor < schedule.lunch_break_end
            )
            if in_lunch:
                slots.append(TimeSlotOut(start_time=cursor, end_time=slot_end, is_available=False, reason="Lunch break"))
            elif cursor in booked:
                slots.append(TimeSlotOut(start_time=cursor, end_time=slot_end, is_available=False, reason="Already booked"))
            elif schedule.max_patients_per_day is not None and count_available >= schedule.max_patients_per_day:
                slots.append(TimeSlotOut(start_time=cursor, end_time=slot_end, is_available=False, reason="Daily patient limit reached"))
            else:
                slots.append(TimeSlotOut(start_time=cursor, end_time=slot_end, is_available=True))
                count_available += 1
            cursor = slot_end
        return slots

    async def validate_slot(
        self, *, clinic_id: UUID, doctor_id: UUID, branch_id: UUID | None, on_date: date, start_time: time
    ) -> tuple[bool, str | None, time | None]:
        """Returns (is_valid, error_reason, end_time)."""
        holiday = await self._get_holiday(clinic_id, branch_id, on_date)
        if holiday is not None:
            return False, f"The clinic is closed on {on_date.isoformat()} ({holiday.holiday_name}).", None

        block = await self._get_block(clinic_id, doctor_id, on_date)
        if block is not None:
            return False, f"The doctor is unavailable on {on_date.isoformat()} ({block.block_type.value}).", None

        schedule = await self._get_schedule_for_day(clinic_id, doctor_id, on_date)
        if schedule is None:
            return False, "The doctor has no working hours configured for this day.", None

        if start_time < schedule.start_time or start_time >= schedule.end_time:
            return False, "The requested time is outside the doctor's working hours.", None

        end_time = _add_minutes(start_time, schedule.slot_duration_minutes)
        if end_time > schedule.end_time:
            return False, "The requested slot does not fit within the doctor's working hours.", None

        if (
            schedule.lunch_break_start is not None
            and schedule.lunch_break_end is not None
            and start_time >= schedule.lunch_break_start
            and start_time < schedule.lunch_break_end
        ):
            return False, "The requested time falls within the doctor's lunch break.", None

        # Slot must be grid-aligned to the schedule's slot duration.
        cursor = schedule.start_time
        aligned = False
        while cursor < schedule.end_time:
            if cursor == start_time:
                aligned = True
                break
            cursor = _add_minutes(cursor, schedule.slot_duration_minutes)
        if not aligned:
            return False, "The requested time does not align to the doctor's slot schedule.", None

        if schedule.max_patients_per_day is not None:
            booked = await self._get_booked_start_times(clinic_id, doctor_id, on_date)
            if len(booked) >= schedule.max_patients_per_day:
                return False, "The doctor has reached the maximum number of patients for this day.", None

        return True, None, end_time
