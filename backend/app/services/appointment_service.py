"""Appointment service: create (slot-validated), confirm, reschedule, cancel,
check-in (the critical Queue+Visit integration point), complete, no-show.

Check-in design: rather than reimplementing queue-ticket/visit creation,
`check_in_appointment` builds a `QueueCreate` payload from the appointment
and calls the EXISTING `QueueService.create_queue()` (Phase 5/6), which
already atomically creates a linked Visit in the same transaction. We then
link `appointment.queue_id`/`appointment.visit_id` back from whatever
`create_queue()` returned. This is the same flow a walk-in goes through -
the only difference is the ticket originates from an Appointment instead of
a fresh reception intake, so `QueueService.create_queue()` gained one
additive, backward-compatible `visit_type` keyword (defaulting to WALK_IN)
so the resulting Visit is correctly tagged `Appointment` instead.
"""

from datetime import UTC, date, datetime, time
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.appointment import (
    APPOINTMENT_STATUS_TRANSITIONS,
    Appointment,
    AppointmentBookingSource,
    AppointmentHistoryAction,
    AppointmentStatus,
)
from app.models.department import Department
from app.models.doctor import Doctor, DoctorStatus
from app.models.patient import Patient, PatientStatus
from app.models.user import User
from app.models.visit import VisitTimelineEventType
from app.repositories.appointment_repository import AppointmentRepository
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentDetail,
    AppointmentHistoryRead,
    AppointmentListItem,
    AppointmentNoteCreate,
    AppointmentReschedule,
)
from app.services.appointment_number_generator import AppointmentNumberGenerator
from app.services.audit_service import AuditService
from app.services.time_slot_service import TimeSlotService
from app.services.waitlist_service import WaitlistService


class AppointmentService:
    def __init__(self, session) -> None:
        self.session = session
        self.repo = AppointmentRepository(session)
        self.slot_service = TimeSlotService(session)
        self.audit_service = AuditService(session)
        self.waitlist_service = WaitlistService(session)

    async def _validate_entities(self, clinic_id: UUID, *, patient_id: UUID, doctor_id: UUID, department_id: UUID | None) -> None:
        patient_stmt = select(Patient).where(Patient.id == patient_id, Patient.clinic_id == clinic_id, Patient.is_deleted.is_(False))
        patient = (await self.session.execute(patient_stmt)).scalar_one_or_none()
        if patient is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
        if patient.status != PatientStatus.ACTIVE:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Patient is not active")

        doctor_stmt = select(Doctor).where(Doctor.id == doctor_id, Doctor.clinic_id == clinic_id, Doctor.is_deleted.is_(False))
        doctor = (await self.session.execute(doctor_stmt)).scalar_one_or_none()
        if doctor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
        if doctor.status != DoctorStatus.ACTIVE:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Doctor is not active")

        if department_id is not None:
            dep_stmt = select(Department).where(Department.id == department_id, Department.clinic_id == clinic_id, Department.is_deleted.is_(False))
            if (await self.session.execute(dep_stmt)).scalar_one_or_none() is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

    async def create_appointment(self, payload: AppointmentCreate, *, clinic_id: UUID, actor: User) -> AppointmentDetail:
        return await self._create_appointment_impl(
            payload, clinic_id=clinic_id, created_by=actor.id, audit_user_id=actor.id,
            booking_source=AppointmentBookingSource.STAFF,
        )

    async def create_patient_appointment(
        self, payload: AppointmentCreate, *, clinic_id: UUID, patient_id: UUID
    ) -> AppointmentDetail:
        """Patient self-service booking (Phase 19). Reuses the exact same
        validation/slot-engine/insert path as staff booking - the only
        differences are: no `created_by`/`updated_by` User (a patient isn't a
        `users` row), `booking_source=Patient`, and the audit log is
        attributed to the patient rather than a staff user (see
        `AuditService.log_event`'s `user_id=None` + metadata pattern below,
        mirroring `patient.password_change` in `patient_portal.py`)."""
        if payload.patient_id != patient_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="patient_id must match the authenticated patient.")
        return await self._create_appointment_impl(
            payload, clinic_id=clinic_id, created_by=None, audit_user_id=None,
            booking_source=AppointmentBookingSource.PATIENT, audit_metadata_extra={"principal": "patient"},
        )

    async def _create_appointment_impl(
        self, payload: AppointmentCreate, *, clinic_id: UUID, created_by: UUID | None, audit_user_id: UUID | None,
        booking_source: AppointmentBookingSource, audit_metadata_extra: dict | None = None,
    ) -> AppointmentDetail:
        await self._validate_entities(clinic_id, patient_id=payload.patient_id, doctor_id=payload.doctor_id, department_id=payload.department_id)

        if payload.appointment_date < date.today():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot book an appointment in the past.")

        is_valid, reason, end_time = await self.slot_service.validate_slot(
            clinic_id=clinic_id, doctor_id=payload.doctor_id, branch_id=payload.branch_id,
            on_date=payload.appointment_date, start_time=payload.start_time,
        )
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

        if await self.repo.has_conflicting_booking(
            clinic_id, doctor_id=payload.doctor_id, appointment_date=payload.appointment_date, start_time=payload.start_time
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This doctor already has an appointment booked at this time.")

        # Application-level check-then-insert above is a fast-path/UX check
        # only (nicer error messages, avoids a wasted number allocation on
        # an obviously-taken slot). The REAL race-condition guarantee is the
        # Postgres partial unique index `uq_appointments_doctor_slot_active`
        # (migration 0012) on (clinic_id, doctor_id, appointment_date,
        # start_time) WHERE is_deleted=false AND status NOT IN
        # ('Cancelled','Rescheduled','NoShow'). If two requests for the same
        # slot both pass the check above (the classic TOCTOU race), the
        # second INSERT hits that index and raises a Postgres unique
        # violation, caught here and turned into a clean 409 instead of a
        # raw 500 - so at most one of two concurrent bookings ever succeeds.
        #
        # `AppointmentNumberGenerator.next_number()` is included in this same
        # try block: its `system_settings`-backed daily counter (Phase 9's
        # `_DailyNumberGenerator`) locks its row with `SELECT ... FOR UPDATE`,
        # but that only protects UPDATEs of an EXISTING counter row - the
        # very first booking of the day for a clinic still races on the
        # counter's own INSERT if two requests hit it simultaneously (found
        # while writing this phase's concurrency test - see docs/BUGS.md).
        # Catching that IntegrityError here too, and folding it into the
        # same clean 409, closes that gap without touching the shared
        # Phase 9 counter implementation (also used by Orders/Prescriptions).
        try:
            generator = AppointmentNumberGenerator(self.session)
            appointment_number = await generator.next_number(clinic_id, payload.appointment_date)
            appointment = await self.repo.create(
                clinic_id=clinic_id, appointment_number=appointment_number, branch_id=payload.branch_id,
                patient_id=payload.patient_id, doctor_id=payload.doctor_id, department_id=payload.department_id,
                service_id=payload.service_id, appointment_type=payload.appointment_type,
                appointment_date=payload.appointment_date, start_time=payload.start_time, end_time=end_time,
                status=AppointmentStatus.BOOKED, notes=payload.notes, created_by=created_by, updated_by=created_by,
                booking_source=booking_source,
            )
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This doctor already has an appointment booked at this time.",
            ) from None

        await self.repo.add_history(
            clinic_id=clinic_id, appointment_id=appointment.id, action=AppointmentHistoryAction.CREATED,
            from_value=None, to_value=f"{payload.appointment_date} {payload.start_time}",
            changed_by=created_by, note="Appointment booked",
        )
        metadata = {"appointment_number": appointment_number}
        if audit_metadata_extra:
            metadata.update(audit_metadata_extra)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=audit_user_id, action="appointment.created",
            entity_type="appointment", entity_id=str(appointment.id),
            metadata=metadata,
        )
        await self.session.commit()
        return await self.get_detail(appointment.id, clinic_id=clinic_id)

    async def _require_appointment(self, appointment_id: UUID, clinic_id: UUID) -> Appointment:
        appointment = await self.repo.get_by_id_and_clinic(appointment_id, clinic_id)
        if appointment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
        return appointment

    def _require_transition(self, appointment: Appointment, new_status: AppointmentStatus) -> None:
        allowed = APPOINTMENT_STATUS_TRANSITIONS.get(appointment.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot transition appointment from {appointment.status.value} to {new_status.value}.",
            )

    async def confirm_appointment(self, appointment_id: UUID, *, clinic_id: UUID, actor: User) -> AppointmentDetail:
        appointment = await self._require_appointment(appointment_id, clinic_id)
        self._require_transition(appointment, AppointmentStatus.CONFIRMED)
        from_status = appointment.status
        await self.repo.update(appointment, status=AppointmentStatus.CONFIRMED, updated_by=actor.id)
        await self.repo.add_history(
            clinic_id=clinic_id, appointment_id=appointment.id, action=AppointmentHistoryAction.CONFIRMED,
            from_value=from_status.value, to_value=AppointmentStatus.CONFIRMED.value, changed_by=actor.id, note=None,
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="appointment.confirmed",
            entity_type="appointment", entity_id=str(appointment.id),
        )
        await self.session.commit()
        return await self.get_detail(appointment.id, clinic_id=clinic_id)

    async def reschedule_appointment(
        self, appointment_id: UUID, payload: AppointmentReschedule, *, clinic_id: UUID, actor: User
    ) -> AppointmentDetail:
        appointment = await self._require_appointment(appointment_id, clinic_id)
        self._require_transition(appointment, AppointmentStatus.RESCHEDULED)

        is_valid, reason, end_time = await self.slot_service.validate_slot(
            clinic_id=clinic_id, doctor_id=appointment.doctor_id, branch_id=appointment.branch_id,
            on_date=payload.appointment_date, start_time=payload.start_time,
        )
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)
        if await self.repo.has_conflicting_booking(
            clinic_id, doctor_id=appointment.doctor_id, appointment_date=payload.appointment_date,
            start_time=payload.start_time, exclude_appointment_id=appointment.id,
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This doctor already has an appointment booked at this time.")

        old_value = f"{appointment.appointment_date} {appointment.start_time}"
        new_value = f"{payload.appointment_date} {payload.start_time}"

        # Mark the old row Rescheduled (terminal) and create a fresh Booked
        # row for the new slot - keeps the audit trail unambiguous (old vs
        # new are two distinct records, matching how the spec's history
        # "old/new date-time" is meant to read) while its own appointment_number stays traceable via history.
        await self.repo.update(appointment, status=AppointmentStatus.RESCHEDULED, updated_by=actor.id)
        await self.repo.add_history(
            clinic_id=clinic_id, appointment_id=appointment.id, action=AppointmentHistoryAction.RESCHEDULED,
            from_value=old_value, to_value=new_value, changed_by=actor.id, note=payload.reason,
        )

        generator = AppointmentNumberGenerator(self.session)
        new_number = await generator.next_number(clinic_id, payload.appointment_date)
        new_appointment = await self.repo.create(
            clinic_id=clinic_id, appointment_number=new_number, branch_id=appointment.branch_id,
            patient_id=appointment.patient_id, doctor_id=appointment.doctor_id, department_id=appointment.department_id,
            service_id=appointment.service_id, appointment_type=appointment.appointment_type,
            appointment_date=payload.appointment_date, start_time=payload.start_time, end_time=end_time,
            status=AppointmentStatus.BOOKED, notes=appointment.notes, created_by=actor.id, updated_by=actor.id,
        )
        await self.repo.add_history(
            clinic_id=clinic_id, appointment_id=new_appointment.id, action=AppointmentHistoryAction.CREATED,
            from_value=old_value, to_value=new_value, changed_by=actor.id,
            note=f"Rescheduled from {appointment.appointment_number}",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="appointment.rescheduled",
            entity_type="appointment", entity_id=str(appointment.id),
            metadata={"from": old_value, "to": new_value, "new_appointment_id": str(new_appointment.id)},
        )
        await self.session.commit()
        return await self.get_detail(new_appointment.id, clinic_id=clinic_id)

    async def reschedule_patient_appointment(
        self, appointment_id: UUID, payload: AppointmentReschedule, *, clinic_id: UUID, patient_id: UUID
    ) -> AppointmentDetail:
        """Patient self-service reschedule. 404s (not 403) if the appointment
        belongs to a different patient, so existence of another patient's
        appointment is never leaked (see `_require_patient_appointment`)."""
        appointment = await self._require_patient_appointment(appointment_id, clinic_id, patient_id)
        self._require_transition(appointment, AppointmentStatus.RESCHEDULED)

        if payload.appointment_date < date.today():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot reschedule to a past date.")

        is_valid, reason, end_time = await self.slot_service.validate_slot(
            clinic_id=clinic_id, doctor_id=appointment.doctor_id, branch_id=appointment.branch_id,
            on_date=payload.appointment_date, start_time=payload.start_time,
        )
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)
        if await self.repo.has_conflicting_booking(
            clinic_id, doctor_id=appointment.doctor_id, appointment_date=payload.appointment_date,
            start_time=payload.start_time, exclude_appointment_id=appointment.id,
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This doctor already has an appointment booked at this time.")

        old_value = f"{appointment.appointment_date} {appointment.start_time}"
        new_value = f"{payload.appointment_date} {payload.start_time}"

        await self.repo.update(appointment, status=AppointmentStatus.RESCHEDULED, updated_by=None)
        await self.repo.add_history(
            clinic_id=clinic_id, appointment_id=appointment.id, action=AppointmentHistoryAction.RESCHEDULED,
            from_value=old_value, to_value=new_value, changed_by=None, note=payload.reason,
        )

        try:
            generator = AppointmentNumberGenerator(self.session)
            new_number = await generator.next_number(clinic_id, payload.appointment_date)
            new_appointment = await self.repo.create(
                clinic_id=clinic_id, appointment_number=new_number, branch_id=appointment.branch_id,
                patient_id=appointment.patient_id, doctor_id=appointment.doctor_id, department_id=appointment.department_id,
                service_id=appointment.service_id, appointment_type=appointment.appointment_type,
                appointment_date=payload.appointment_date, start_time=payload.start_time, end_time=end_time,
                status=AppointmentStatus.BOOKED, notes=appointment.notes, created_by=None, updated_by=None,
                booking_source=AppointmentBookingSource.PATIENT,
            )
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This doctor already has an appointment booked at this time.",
            ) from None

        await self.repo.add_history(
            clinic_id=clinic_id, appointment_id=new_appointment.id, action=AppointmentHistoryAction.CREATED,
            from_value=old_value, to_value=new_value, changed_by=None,
            note=f"Rescheduled from {appointment.appointment_number}",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=None, action="appointment.rescheduled",
            entity_type="appointment", entity_id=str(appointment.id),
            metadata={"from": old_value, "to": new_value, "new_appointment_id": str(new_appointment.id), "principal": "patient"},
        )
        await self.session.commit()
        return await self.get_detail(new_appointment.id, clinic_id=clinic_id)

    async def cancel_patient_appointment(
        self, appointment_id: UUID, reason: str | None, *, clinic_id: UUID, patient_id: UUID
    ) -> AppointmentDetail:
        appointment = await self._require_patient_appointment(appointment_id, clinic_id, patient_id)
        self._require_transition(appointment, AppointmentStatus.CANCELLED)
        from_status = appointment.status
        await self.repo.update(appointment, status=AppointmentStatus.CANCELLED, updated_by=None)
        await self.repo.add_history(
            clinic_id=clinic_id, appointment_id=appointment.id, action=AppointmentHistoryAction.CANCELLED,
            from_value=from_status.value, to_value=AppointmentStatus.CANCELLED.value, changed_by=None, note=reason,
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=None, action="appointment.cancelled",
            entity_type="appointment", entity_id=str(appointment.id), metadata={"principal": "patient"},
        )
        await self.session.commit()
        await self.waitlist_service.offer_next_slot(
            clinic_id=clinic_id, doctor_id=appointment.doctor_id,
            freed_date=appointment.appointment_date, freed_start_time=appointment.start_time,
        )
        return await self.get_detail(appointment.id, clinic_id=clinic_id)

    async def _require_patient_appointment(self, appointment_id: UUID, clinic_id: UUID, patient_id: UUID) -> Appointment:
        appointment = await self.repo.get_by_id_and_clinic(appointment_id, clinic_id)
        if appointment is None or appointment.patient_id != patient_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
        return appointment

    async def cancel_appointment(self, appointment_id: UUID, reason: str | None, *, clinic_id: UUID, actor: User) -> AppointmentDetail:
        appointment = await self._require_appointment(appointment_id, clinic_id)
        self._require_transition(appointment, AppointmentStatus.CANCELLED)
        from_status = appointment.status
        await self.repo.update(appointment, status=AppointmentStatus.CANCELLED, updated_by=actor.id)
        await self.repo.add_history(
            clinic_id=clinic_id, appointment_id=appointment.id, action=AppointmentHistoryAction.CANCELLED,
            from_value=from_status.value, to_value=AppointmentStatus.CANCELLED.value, changed_by=actor.id, note=reason,
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="appointment.cancelled",
            entity_type="appointment", entity_id=str(appointment.id),
        )
        await self.session.commit()

        # Phase 11 waitlist: offer the freed slot to the next matching entry.
        await self.waitlist_service.offer_next_slot(
            clinic_id=clinic_id, doctor_id=appointment.doctor_id,
            freed_date=appointment.appointment_date, freed_start_time=appointment.start_time,
        )
        return await self.get_detail(appointment.id, clinic_id=clinic_id)

    async def mark_no_show(self, appointment_id: UUID, *, clinic_id: UUID, actor: User) -> AppointmentDetail:
        appointment = await self._require_appointment(appointment_id, clinic_id)
        self._require_transition(appointment, AppointmentStatus.NO_SHOW)
        from_status = appointment.status
        await self.repo.update(appointment, status=AppointmentStatus.NO_SHOW, updated_by=actor.id)
        await self.repo.add_history(
            clinic_id=clinic_id, appointment_id=appointment.id, action=AppointmentHistoryAction.NO_SHOW,
            from_value=from_status.value, to_value=AppointmentStatus.NO_SHOW.value, changed_by=actor.id, note=None,
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="appointment.no_show",
            entity_type="appointment", entity_id=str(appointment.id),
        )
        await self.session.commit()
        return await self.get_detail(appointment.id, clinic_id=clinic_id)

    async def check_in_appointment(self, appointment_id: UUID, *, clinic_id: UUID, actor: User) -> AppointmentDetail:
        """The critical cross-entity action: creates a real linked Queue
        ticket AND Visit by calling into the existing `QueueService.create_queue()`
        (Phase 5/6), instead of reimplementing that logic."""
        appointment = await self._require_appointment(appointment_id, clinic_id)
        self._require_transition(appointment, AppointmentStatus.CHECKED_IN)

        if appointment.department_id is None or appointment.service_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This appointment is missing a department/service and cannot be checked in. Edit the appointment first.",
            )

        from app.models.queue import QueuePriority
        from app.models.visit import VisitType
        from app.schemas.queue import QueueCreate
        from app.services.queue_service import QueueService

        queue_service = QueueService(self.session)
        queue_payload = QueueCreate(
            patient_id=appointment.patient_id, branch_id=appointment.branch_id,
            department_id=appointment.department_id, doctor_id=appointment.doctor_id,
            service_id=appointment.service_id, priority=QueuePriority.NORMAL,
            notes=f"Checked in from appointment {appointment.appointment_number}",
        )
        queue_detail = await queue_service.create_queue(queue_payload, clinic_id=clinic_id, actor=actor, visit_type=VisitType.APPOINTMENT)

        await self.repo.update(
            appointment, status=AppointmentStatus.CHECKED_IN, queue_id=queue_detail.id,
            visit_id=queue_detail.visit_id, updated_by=actor.id,
        )
        await self.repo.add_history(
            clinic_id=clinic_id, appointment_id=appointment.id, action=AppointmentHistoryAction.CHECKED_IN,
            from_value=None, to_value=None, changed_by=actor.id,
            note=f"Checked in - queue {queue_detail.queue_number}, visit created",
        )

        if queue_detail.visit_id is not None:
            from app.repositories.visit_repository import VisitRepository

            visit_repo = VisitRepository(self.session)
            await visit_repo.add_timeline_event(
                clinic_id=clinic_id, visit_id=queue_detail.visit_id,
                event_type=VisitTimelineEventType.APPOINTMENT_CHECKED_IN,
                occurred_at=datetime.now(UTC), recorded_by=actor.id,
                note=f"Checked in from appointment {appointment.appointment_number}",
            )

        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="appointment.checked_in",
            entity_type="appointment", entity_id=str(appointment.id),
            metadata={"queue_id": str(queue_detail.id), "visit_id": str(queue_detail.visit_id)},
        )
        await self.session.commit()
        return await self.get_detail(appointment.id, clinic_id=clinic_id)

    async def complete_appointment(self, appointment_id: UUID, *, clinic_id: UUID, actor: User) -> AppointmentDetail:
        """Doctor-only. The Visit itself reaches Completed via the existing
        Doctor Workspace flow (Phase 7); this is a direct status sync so the
        Appointment record reflects that outcome even if the doctor never
        opens the Appointment view again."""
        appointment = await self._require_appointment(appointment_id, clinic_id)
        allowed = APPOINTMENT_STATUS_TRANSITIONS.get(appointment.status, set())
        if AppointmentStatus.COMPLETED not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot complete an appointment in status {appointment.status.value}.",
            )
        from_status = appointment.status
        await self.repo.update(appointment, status=AppointmentStatus.COMPLETED, updated_by=actor.id)
        await self.repo.add_history(
            clinic_id=clinic_id, appointment_id=appointment.id, action=AppointmentHistoryAction.COMPLETED,
            from_value=from_status.value, to_value=AppointmentStatus.COMPLETED.value, changed_by=actor.id, note=None,
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="appointment.completed",
            entity_type="appointment", entity_id=str(appointment.id),
        )
        await self.session.commit()
        return await self.get_detail(appointment.id, clinic_id=clinic_id)

    async def add_note(self, appointment_id: UUID, payload: AppointmentNoteCreate, *, clinic_id: UUID, actor: User) -> None:
        appointment = await self._require_appointment(appointment_id, clinic_id)
        from app.models.appointment import AppointmentNote

        note = AppointmentNote(clinic_id=clinic_id, appointment_id=appointment.id, note=payload.note, created_by=actor.id)
        self.session.add(note)
        await self.session.commit()

    async def get_history(self, appointment_id: UUID, *, clinic_id: UUID) -> list[AppointmentHistoryRead]:
        await self._require_appointment(appointment_id, clinic_id)
        rows = await self.repo.get_history(appointment_id, clinic_id)
        return [AppointmentHistoryRead.model_validate(r) for r in rows]

    async def get_detail(self, appointment_id: UUID, *, clinic_id: UUID) -> AppointmentDetail:
        appointment = await self.repo.get_with_relations(appointment_id, clinic_id)
        if appointment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
        history = await self.repo.get_history(appointment_id, clinic_id)
        data = AppointmentRead_model_dump(appointment)
        data.update(
            patient_name=appointment.patient.full_name if appointment.patient else None,
            patient_number=appointment.patient.patient_number if appointment.patient else None,
            doctor_name=appointment.doctor.full_name if appointment.doctor else None,
            department_name=appointment.department.name if appointment.department else None,
            service_name=appointment.service.service_name if appointment.service else None,
            branch_name=appointment.branch.name if appointment.branch else None,
            history=[AppointmentHistoryRead.model_validate(h) for h in history],
        )
        return AppointmentDetail.model_validate(data)

    async def search(self, *, clinic_id: UUID, params) -> tuple[list[AppointmentListItem], int]:
        rows, total = await self.repo.search(clinic_id, params)
        items = [
            AppointmentListItem(
                id=r.id, appointment_number=r.appointment_number, appointment_date=r.appointment_date,
                start_time=r.start_time, end_time=r.end_time, status=r.status, appointment_type=r.appointment_type,
                patient_id=r.patient_id, patient_name=r.patient.full_name if r.patient else None,
                patient_number=r.patient.patient_number if r.patient else None,
                doctor_id=r.doctor_id, doctor_name=r.doctor.full_name if r.doctor else None,
                department_name=r.department.name if r.department else None, branch_id=r.branch_id,
            )
            for r in rows
        ]
        return items, total

    async def list_for_patient(self, patient_id: UUID, *, clinic_id: UUID) -> list[AppointmentListItem]:
        rows = await self.repo.list_for_patient(clinic_id, patient_id)
        return [
            AppointmentListItem(
                id=r.id, appointment_number=r.appointment_number, appointment_date=r.appointment_date,
                start_time=r.start_time, end_time=r.end_time, status=r.status, appointment_type=r.appointment_type,
                patient_id=r.patient_id, patient_name=None, patient_number=None,
                doctor_id=r.doctor_id, doctor_name=r.doctor.full_name if r.doctor else None,
                department_name=r.department.name if r.department else None, branch_id=r.branch_id,
            )
            for r in rows
        ]


def AppointmentRead_model_dump(appointment: Appointment) -> dict:
    from app.schemas.appointment import AppointmentRead

    return AppointmentRead.model_validate(appointment).model_dump()
