"""Repository for Appointment: search/filter, double-booking check, history."""

from datetime import UTC, date, datetime, time
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.appointment import (
    NON_BLOCKING_APPOINTMENT_STATUSES,
    Appointment,
    AppointmentHistory,
    AppointmentHistoryAction,
)
from app.models.patient import Patient
from app.repositories.base import BaseRepository
from app.schemas.appointment import AppointmentSearchParams


class AppointmentRepository(BaseRepository[Appointment]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=Appointment)

    async def get_by_id_and_clinic(self, id_: UUID, clinic_id: UUID) -> Appointment | None:
        stmt = select(Appointment).where(
            Appointment.id == id_, Appointment.clinic_id == clinic_id, Appointment.is_deleted.is_(False)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_relations(self, id_: UUID, clinic_id: UUID) -> Appointment | None:
        stmt = (
            select(Appointment)
            .where(Appointment.id == id_, Appointment.clinic_id == clinic_id, Appointment.is_deleted.is_(False))
            .options(
                selectinload(Appointment.patient),
                selectinload(Appointment.doctor),
                selectinload(Appointment.department),
                selectinload(Appointment.service),
                selectinload(Appointment.branch),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def has_conflicting_booking(
        self, clinic_id: UUID, *, doctor_id: UUID, appointment_date: date, start_time: time,
        exclude_appointment_id: UUID | None = None,
    ) -> bool:
        filters = [
            Appointment.clinic_id == clinic_id,
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == appointment_date,
            Appointment.start_time == start_time,
            Appointment.is_deleted.is_(False),
            ~Appointment.status.in_(NON_BLOCKING_APPOINTMENT_STATUSES),
        ]
        if exclude_appointment_id is not None:
            filters.append(Appointment.id != exclude_appointment_id)
        stmt = select(func.count()).select_from(Appointment).where(and_(*filters))
        result = await self.session.execute(stmt)
        return int(result.scalar_one()) > 0

    async def list_for_doctor_date(self, clinic_id: UUID, *, doctor_id: UUID, appointment_date: date) -> list[Appointment]:
        stmt = select(Appointment).where(
            Appointment.clinic_id == clinic_id,
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == appointment_date,
            Appointment.is_deleted.is_(False),
            ~Appointment.status.in_(NON_BLOCKING_APPOINTMENT_STATUSES),
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    def _base_filters(self, clinic_id: UUID, params: AppointmentSearchParams):
        filters = [Appointment.clinic_id == clinic_id, Appointment.is_deleted.is_(False)]
        if params.branch_id is not None:
            filters.append(Appointment.branch_id == params.branch_id)
        if params.department_id is not None:
            filters.append(Appointment.department_id == params.department_id)
        if params.doctor_id is not None:
            filters.append(Appointment.doctor_id == params.doctor_id)
        if params.status is not None:
            filters.append(Appointment.status == params.status)
        if params.appointment_type is not None:
            filters.append(Appointment.appointment_type == params.appointment_type)
        if params.date_from is not None:
            filters.append(Appointment.appointment_date >= params.date_from)
        if params.date_to is not None:
            filters.append(Appointment.appointment_date <= params.date_to)
        return filters

    async def search(self, clinic_id: UUID, params: AppointmentSearchParams) -> tuple[list[Appointment], int]:
        filters = self._base_filters(clinic_id, params)
        base_query = select(Appointment).where(and_(*filters))
        if params.q:
            like = f"%{params.q.lower()}%"
            base_query = base_query.join(Patient, Patient.id == Appointment.patient_id).where(
                (func.lower(Appointment.appointment_number).like(like))
                | (func.lower(Patient.first_name).like(like))
                | (func.lower(Patient.last_name).like(like))
                | (func.lower(Patient.patient_number).like(like))
                | (func.lower(Patient.mobile_number).like(like))
            )

        count_stmt = select(func.count()).select_from(base_query.subquery())
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = (
            base_query.options(
                selectinload(Appointment.patient),
                selectinload(Appointment.doctor),
                selectinload(Appointment.department),
            )
            .order_by(Appointment.appointment_date.asc(), Appointment.start_time.asc())
            .offset(params.offset)
            .limit(params.limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), total

    async def list_for_patient(self, clinic_id: UUID, patient_id: UUID) -> list[Appointment]:
        stmt = (
            select(Appointment)
            .where(Appointment.clinic_id == clinic_id, Appointment.patient_id == patient_id, Appointment.is_deleted.is_(False))
            .options(selectinload(Appointment.doctor), selectinload(Appointment.department))
            .order_by(Appointment.appointment_date.desc(), Appointment.start_time.desc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    async def get_history(self, appointment_id: UUID, clinic_id: UUID) -> list[AppointmentHistory]:
        stmt = (
            select(AppointmentHistory)
            .where(AppointmentHistory.appointment_id == appointment_id, AppointmentHistory.clinic_id == clinic_id)
            .order_by(AppointmentHistory.changed_at.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    async def add_history(
        self, *, clinic_id: UUID, appointment_id: UUID, action: AppointmentHistoryAction,
        from_value: str | None, to_value: str | None, changed_by: UUID | None, note: str | None,
    ) -> AppointmentHistory:
        entry = AppointmentHistory(
            clinic_id=clinic_id, appointment_id=appointment_id, action=action,
            from_value=from_value, to_value=to_value, changed_by=changed_by,
            changed_at=datetime.now(UTC), note=note,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    # --- Phase 12: Owner Dashboard & Reports (Appointment Reports) ---

    async def status_counts_in_range(self, clinic_id: UUID, date_from: date, date_to: date) -> dict[str, int]:
        stmt = (
            select(Appointment.status, func.count())
            .where(
                Appointment.clinic_id == clinic_id, Appointment.is_deleted.is_(False),
                Appointment.appointment_date >= date_from, Appointment.appointment_date <= date_to,
            )
            .group_by(Appointment.status)
        )
        rows = (await self.session.execute(stmt)).all()
        return {r[0].value: int(r[1]) for r in rows}

    async def rescheduled_count_in_range(self, clinic_id: UUID, date_from: date, date_to: date) -> int:
        stmt = select(func.count()).select_from(AppointmentHistory).join(
            Appointment, Appointment.id == AppointmentHistory.appointment_id
        ).where(
            Appointment.clinic_id == clinic_id,
            AppointmentHistory.action == AppointmentHistoryAction.RESCHEDULED,
            Appointment.appointment_date >= date_from, Appointment.appointment_date <= date_to,
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def doctor_utilization_in_range(self, clinic_id: UUID, date_from: date, date_to: date) -> list[dict]:
        """Simplification (documented per spec's fallback): booked vs.
        completed ratio per doctor over the range, rather than a full
        slot-capacity calculation against `DoctorSchedule` (which would
        require per-day schedule resolution for every date in the range -
        heavy for a report endpoint). `TimeSlotService` remains the source
        of truth for live per-day slot availability used at booking time."""
        from app.models.doctor import Doctor
        from app.models.appointment import AppointmentStatus

        booked_stmt = (
            select(Doctor.id, Doctor.first_name, Doctor.last_name, func.count())
            .select_from(Appointment)
            .join(Doctor, Doctor.id == Appointment.doctor_id)
            .where(
                Appointment.clinic_id == clinic_id, Appointment.is_deleted.is_(False),
                Appointment.appointment_date >= date_from, Appointment.appointment_date <= date_to,
            )
            .group_by(Doctor.id, Doctor.first_name, Doctor.last_name)
        )
        booked_rows = {r[0]: {"doctor_name": f"{r[1]} {r[2]}".strip(), "booked": int(r[3])} for r in (await self.session.execute(booked_stmt)).all()}

        completed_stmt = (
            select(Appointment.doctor_id, func.count())
            .where(
                Appointment.clinic_id == clinic_id, Appointment.is_deleted.is_(False),
                Appointment.appointment_date >= date_from, Appointment.appointment_date <= date_to,
                Appointment.status == AppointmentStatus.COMPLETED,
            )
            .group_by(Appointment.doctor_id)
        )
        completed_rows = {r[0]: int(r[1]) for r in (await self.session.execute(completed_stmt)).all()}

        results = []
        for doctor_id, info in booked_rows.items():
            completed = completed_rows.get(doctor_id, 0)
            utilization = (completed / info["booked"]) if info["booked"] else 0.0
            results.append({
                "doctor_id": doctor_id, "doctor_name": info["doctor_name"],
                "booked": info["booked"], "completed": completed, "utilization": round(utilization, 4),
            })
        return results

    async def daily_booking_series(self, clinic_id: UUID, date_from: date, date_to: date) -> list[dict]:
        stmt = (
            select(Appointment.appointment_date, func.count())
            .where(
                Appointment.clinic_id == clinic_id, Appointment.is_deleted.is_(False),
                Appointment.appointment_date >= date_from, Appointment.appointment_date <= date_to,
            )
            .group_by(Appointment.appointment_date)
            .order_by(Appointment.appointment_date)
        )
        rows = (await self.session.execute(stmt)).all()
        return [{"date": r[0].isoformat(), "value": int(r[1])} for r in rows]

    async def get_active_entity(self, model, id_: UUID, clinic_id: UUID):
        stmt = select(model).where(model.id == id_, model.clinic_id == clinic_id, model.is_deleted.is_(False))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
