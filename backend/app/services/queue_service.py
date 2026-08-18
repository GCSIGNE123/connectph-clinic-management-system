"""Queue (reception ticket) service: create with full validation, list/search,
status transitions (writing history + audit log + WebSocket broadcast),
reassignment, cancellation, and printable-slip payload.
"""

import hashlib
import hmac
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.ws_manager import queue_connection_manager
from app.models.clinic import Clinic
from app.models.clinic_service import ClinicService
from app.models.department import Department
from app.models.doctor import Doctor, DoctorStatus
from app.models.patient import Patient, PatientStatus
from app.models.queue import QUEUE_STATUS_TRANSITIONS, Queue, QueueStatus
from app.models.queue_setting import QueueSetting
from app.models.user import User
from app.models.visit import VISIT_STATUS_TRANSITIONS, VisitPriority, VisitStatus, VisitTimelineEventType, VisitType
from app.repositories.consultation_repository import ConsultationRepository
from app.repositories.queue_repository import QueueRepository
from app.repositories.queue_setting_repository import QueueSettingRepository
from app.services.queue_destination import resolve_room_label
from app.services.shift_service import enforce_receptionist_open_shift
from app.schemas.queue import (
    QueueCreate,
    QueueDetail,
    QueueListItem,
    QueueRead,
    QueueSearchParams,
    QueueSlip,
    QueueStatusHistoryRead,
    QueueUpdate,
)
from app.services.audit_service import AuditService
from app.services.queue_number_generator import QueueNumberGenerator
from app.services import sync_queue_service
from app.services.visit_service import VisitService

DEFAULT_QUEUE_PREFIX = "A"

# Phase 21 (Vitals-before-Queue): services whose `service_code` marks them as
# Consultation/Follow-up - the two service types the spec requires vitals to
# be captured for BEFORE a queue ticket can be created. `ClinicService` has
# no dedicated category/type column (see models/clinic_service.py) - the
# code allowlist below is the detection signal, matched against
# `DEFAULT_SERVICES`' seeded codes (`models/clinic_service.py`). This is a
# known, documented limitation: a clinic that renames/reassigns these codes
# on its own service catalog would not be detected correctly - a real
# `category` column on `ClinicService` would be the cleaner long-term fix,
# out of scope for this additive change.
PRE_QUEUE_VITALS_SERVICE_CODES = {"CONSULT", "FOLLOW-UP"}

# Phase 21: the vitals fields required before a Consultation/Follow-up Queue
# ticket may be created (Pain Score and Head Circumference are explicitly
# OPTIONAL per spec and never appear here - Head Circumference in
# particular is gated behind `Clinic.require_head_circumference` and only
# added to this set conditionally, see `_missing_required_vitals` below).
REQUIRED_VITALS_FIELDS: dict[str, str] = {
    "blood_pressure": "Blood Pressure",
    "temperature": "Temperature",
    "pulse_rate": "Pulse Rate",
    "respiratory_rate": "Respiratory Rate",
    "oxygen_saturation": "SpO2",
    "height_cm": "Height",
    "weight_kg": "Weight",
}


def service_requires_pre_queue_vitals(service: ClinicService) -> bool:
    return service.service_code in PRE_QUEUE_VITALS_SERVICE_CODES


def _slip_qr_token(clinic_id: UUID, queue_id: UUID) -> str:
    message = f"queue:{clinic_id}:{queue_id}".encode()
    secret_key = settings.JWT_SECRET_KEY.encode()
    signature = hmac.new(secret_key, message, hashlib.sha256).hexdigest()[:16]
    return f"{clinic_id}:{queue_id}:{signature}"


def _full_name(entity) -> str:
    parts = [entity.first_name, getattr(entity, "middle_name", None), entity.last_name, getattr(entity, "suffix", None)]
    return " ".join(p for p in parts if p)


def _to_list_item(q: Queue, *, vitals_taken: bool) -> QueueListItem:
    return QueueListItem(
        id=q.id,
        queue_number=q.queue_number,
        queue_date=q.queue_date,
        priority=q.priority,
        status=q.status,
        visit_classification=q.visit_classification,
        branch_id=q.branch_id,
        department_id=q.department_id,
        department_name=q.department.name if q.department else None,
        doctor_id=q.doctor_id,
        doctor_name=_full_name(q.doctor) if q.doctor else None,
        service_id=q.service_id,
        service_name=q.service.service_name if q.service else None,
        patient_id=q.patient_id,
        patient_name=q.patient.full_name if q.patient else None,
        patient_number=q.patient.patient_number if q.patient else None,
        created_at=q.created_at,
        called_at=q.called_at,
        visit_id=q.visit_id,
        vitals_taken=vitals_taken,
    )


def _to_detail(q: Queue, history: list) -> QueueDetail:
    base = QueueRead.model_validate(q).model_dump()
    return QueueDetail(
        **base,
        history=[QueueStatusHistoryRead.model_validate(h) for h in history],
        patient_name=q.patient.full_name if q.patient else None,
        patient_number=q.patient.patient_number if q.patient else None,
        department_name=q.department.name if q.department else None,
        doctor_name=_full_name(q.doctor) if q.doctor else None,
        service_name=q.service.service_name if q.service else None,
        branch_name=q.branch.name if q.branch else None,
        # Phase 6: denormalized visit number, if a visit is linked (see
        # `queue_service.create_queue` -> `visit_service.create_visit_for_queue`).
        visit_number=q.visit.visit_number if getattr(q, "visit", None) else None,
    )


class QueueService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = QueueRepository(session)
        self.setting_repo = QueueSettingRepository(session)
        self.number_generator = QueueNumberGenerator(session)
        self.audit_service = AuditService(session)
        self.visit_service = VisitService(session)
        self.consultation_repo = ConsultationRepository(session)

    async def _validate_and_fetch_entities(
        self, clinic_id: UUID, *, patient_id: UUID, department_id: UUID, doctor_id: UUID | None, service_id: UUID
    ) -> tuple[Patient, Department, Doctor | None, ClinicService]:
        patient = await self.repo.get_active_entity(Patient, patient_id, clinic_id)
        if patient is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
        if patient.status == PatientStatus.ARCHIVED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot create a queue ticket for an archived patient.",
            )

        department = await self.repo.get_active_entity(Department, department_id, clinic_id)
        if department is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
        if department.status != "Active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Selected department is not active."
            )

        doctor = None
        if doctor_id is not None:
            doctor = await self.repo.get_active_entity(Doctor, doctor_id, clinic_id)
            if doctor is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
            if doctor.status != DoctorStatus.ACTIVE:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Selected doctor is not active."
                )

        service = await self.repo.get_active_entity(ClinicService, service_id, clinic_id)
        if service is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
        if service.status != "Active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected service is not active.")

        return patient, department, doctor, service

    async def _resolve_prefix(
        self, clinic_id: UUID, branch_id: UUID, department_id: UUID, doctor_id: UUID | None = None
    ) -> str:
        # Post-RC1 (Multi-Department/Multi-Doctor TV Queue Display):
        # doctor_id is optional and additive - a ticket with no doctor
        # assigned (e.g. Laboratory/Radiology department-only tickets)
        # resolves exactly as before via the department/branch/clinic chain.
        setting = await self.setting_repo.get_effective_for_doctor(clinic_id, branch_id, department_id, doctor_id)
        if setting is not None:
            return setting.queue_prefix
        return DEFAULT_QUEUE_PREFIX

    async def _resolve_max_daily_queue(
        self, clinic_id: UUID, branch_id: UUID, department_id: UUID, doctor_id: UUID | None = None
    ) -> int:
        # Item 13: per-prefix daily ceiling (default 200). Uses the same
        # effective-setting resolution as `_resolve_prefix` (doctor override,
        # else department override, else branch/clinic default) so the limit
        # that applies is whichever `QueueSetting` row actually determined
        # the prefix.
        setting = await self.setting_repo.get_effective_for_doctor(clinic_id, branch_id, department_id, doctor_id)
        if setting is not None:
            return setting.max_daily_queue
        return 200

    async def _required_vitals_fields(self, clinic_id: UUID) -> dict[str, str]:
        required = dict(REQUIRED_VITALS_FIELDS)
        clinic = await self.session.get(Clinic, clinic_id)
        if clinic is not None and clinic.require_head_circumference:
            required["head_circumference_cm"] = "Head Circumference"
        return required

    async def _missing_required_vitals(self, visit_id: UUID, *, clinic_id: UUID) -> list[str]:
        """Phase 21: returns the human-readable labels of any required
        vitals fields absent from the draft visit's SoapNote. Real backend
        enforcement (defense in depth) for the "vitals must exist before a
        Consultation/Follow-up Queue ticket is created" rule - not merely a
        disabled frontend button."""
        required = await self._required_vitals_fields(clinic_id)

        consultation = await self.consultation_repo.get_latest_for_visit(visit_id, clinic_id)
        if consultation is None:
            return list(required.values())
        soap = await self.consultation_repo.get_soap(consultation.id, clinic_id)
        if soap is None:
            return list(required.values())
        return [label for field, label in required.items() if getattr(soap, field, None) in (None, "")]

    async def _create_queue_for_draft_visit(
        self, payload: QueueCreate, *, clinic_id: UUID, actor: User, service: ClinicService
    ) -> QueueDetail:
        """Phase 21 (Vitals-before-Queue): attaches a Queue ticket to an
        EXISTING `DraftVitals` Visit (created via `POST /visits/pre-queue`)
        instead of creating a brand-new Visit - the inverse of the normal
        `create_visit_for_queue` side effect below. Rejects with a 400
        listing exactly which required vitals are missing if the draft
        visit's SoapNote is incomplete - this is the real enforcement point,
        the frontend's disabled "Create Queue Ticket" button is only the
        first line of defense."""
        visit = await self.visit_service.repo.get_by_id_and_clinic(payload.visit_id, clinic_id)
        if visit is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft visit not found.")
        if visit.status != VisitStatus.DRAFT_VITALS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This visit is not awaiting queue creation (vitals already queued, or not a pre-queue draft).",
            )
        if visit.patient_id != payload.patient_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Draft visit does not belong to this patient.")

        missing = await self._missing_required_vitals(visit.id, clinic_id=clinic_id)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot create a queue ticket - missing required vitals: {', '.join(missing)}.",
            )

        today = datetime.now(UTC).date()
        if await self.repo.has_active_duplicate(
            clinic_id, patient_id=payload.patient_id, department_id=payload.department_id, queue_date=today
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This patient already has an active queue ticket for this department today.",
            )

        resolved_doctor_id = payload.doctor_id if payload.doctor_id is not None else visit.doctor_id
        prefix = await self._resolve_prefix(clinic_id, payload.branch_id, payload.department_id, resolved_doctor_id)
        max_daily_queue = await self._resolve_max_daily_queue(
            clinic_id, payload.branch_id, payload.department_id, resolved_doctor_id
        )
        queue_number = await self.number_generator.next_number(
            clinic_id, payload.branch_id, prefix, today, max_daily_queue=max_daily_queue
        )

        queue = await self.repo.create(
            clinic_id=clinic_id,
            branch_id=payload.branch_id,
            patient_id=payload.patient_id,
            department_id=payload.department_id,
            doctor_id=resolved_doctor_id,
            service_id=payload.service_id,
            queue_number=queue_number,
            queue_prefix=prefix,
            queue_date=today,
            priority=payload.priority,
            status=QueueStatus.WAITING,
            visit_classification=payload.visit_classification,
            notes=payload.notes,
            visit_id=visit.id,
            created_by=actor.id,
            updated_by=actor.id,
        )
        await self.repo.add_history(
            clinic_id=clinic_id, queue_id=queue.id, from_status=None, to_status=QueueStatus.WAITING,
            changed_by=actor.id, note="Queue ticket created (vitals captured pre-queue)",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="queue.created",
            entity_type="queue", entity_id=str(queue.id),
            metadata={"queue_number": queue_number, "patient_id": str(payload.patient_id), "visit_id": str(visit.id)},
        )

        now = datetime.now(UTC)
        visit = await self.visit_service.repo.update(
            visit,
            queue_id=queue.id,
            status=VisitStatus.WAITING,
            check_in_time=visit.check_in_time or now,
            updated_by=actor.id,
        )
        await self.visit_service.repo.add_timeline_event(
            clinic_id=clinic_id, visit_id=visit.id, event_type=VisitTimelineEventType.QUEUED,
            occurred_at=now, recorded_by=actor.id, note="Added to reception queue (vitals captured beforehand)",
        )
        await self.visit_service.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="visit.queued",
            entity_type="visit", entity_id=str(visit.id), metadata={"queue_id": str(queue.id)},
        )

        await self.session.commit()

        detail = await self.get_detail(queue.id, clinic_id=clinic_id)
        await queue_connection_manager.broadcast(clinic_id, "queue.created", detail.model_dump(mode="json"))
        # Post-RC1 Phase 2 Milestone 2: Cloud Backup - best-effort, never
        # affects this already-committed create (see sync_queue_service.py).
        await sync_queue_service.enqueue(
            entity_type="queue_ticket", record_id=queue.id, operation="create",
            payload=detail.model_dump(mode="json"), clinic_id=clinic_id,
        )
        await sync_queue_service.enqueue(
            entity_type="visit", record_id=visit.id, operation="update",
            payload={"visit_id": str(visit.id), "queue_id": str(queue.id), "status": "Waiting"},
            clinic_id=clinic_id,
        )
        return detail

    async def create_queue(
        self, payload: QueueCreate, *, clinic_id: UUID, actor: User, visit_type: VisitType = VisitType.WALK_IN
    ) -> QueueDetail:
        # Phase 11: `visit_type` is an additive, backward-compatible kwarg
        # (defaults to WALK_IN, unchanged behaviour for all existing
        # callers). `AppointmentService.check_in_appointment` calls this
        # exact method with `visit_type=VisitType.APPOINTMENT` instead of
        # reimplementing queue/visit creation - see services/appointment_service.py.
        #
        # Item 7 (Shift Enforcement): checked here, before any validation or
        # write, so it transparently covers BOTH "queue a walk-in patient"
        # AND "check in an appointment" (which calls this same method) with
        # one gate - a Receptionist with no open shift is blocked from
        # either path, and nothing partial gets created.
        await enforce_receptionist_open_shift(self.session, clinic_id=clinic_id, actor_id=actor.id)

        _patient, _department, _doctor, service = await self._validate_and_fetch_entities(
            clinic_id,
            patient_id=payload.patient_id,
            department_id=payload.department_id,
            doctor_id=payload.doctor_id,
            service_id=payload.service_id,
        )

        # Phase 21 (Vitals-before-Queue): Consultation/Follow-up services
        # must go through the pre-queue draft-visit path so vitals are
        # captured first - `payload.visit_id` is how the frontend signals
        # "this queue ticket is for a draft visit that already has vitals
        # entered". A direct `POST /queues` call for one of these services
        # with no `visit_id` is rejected here (backend enforcement, not just
        # a disabled frontend button - see the explicit verification item in
        # the spec about bypassing the UI via the raw API). Every other
        # service is completely unaffected - falls straight through to the
        # unchanged Queue-creates-Visit flow below.
        if service_requires_pre_queue_vitals(service):
            if payload.visit_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Vitals must be captured before creating a queue ticket for this service. "
                        "Create a draft visit (POST /visits/pre-queue) and save vitals first."
                    ),
                )
            return await self._create_queue_for_draft_visit(payload, clinic_id=clinic_id, actor=actor, service=service)
        elif payload.visit_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="visit_id is only supported for Consultation/Follow-up services.",
            )

        today = datetime.now(UTC).date()

        if await self.repo.has_active_duplicate(
            clinic_id, patient_id=payload.patient_id, department_id=payload.department_id, queue_date=today
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This patient already has an active queue ticket for this department today.",
            )

        prefix = await self._resolve_prefix(clinic_id, payload.branch_id, payload.department_id, payload.doctor_id)
        max_daily_queue = await self._resolve_max_daily_queue(
            clinic_id, payload.branch_id, payload.department_id, payload.doctor_id
        )
        queue_number = await self.number_generator.next_number(
            clinic_id, payload.branch_id, prefix, today, max_daily_queue=max_daily_queue
        )

        queue = await self.repo.create(
            clinic_id=clinic_id,
            branch_id=payload.branch_id,
            patient_id=payload.patient_id,
            department_id=payload.department_id,
            doctor_id=payload.doctor_id,
            service_id=payload.service_id,
            queue_number=queue_number,
            queue_prefix=prefix,
            queue_date=today,
            priority=payload.priority,
            status=QueueStatus.WAITING,
            visit_classification=payload.visit_classification,
            notes=payload.notes,
            created_by=actor.id,
            updated_by=actor.id,
        )
        await self.repo.add_history(
            clinic_id=clinic_id, queue_id=queue.id, from_status=None, to_status=QueueStatus.WAITING,
            changed_by=actor.id, note="Queue ticket created",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="queue.created",
            entity_type="queue", entity_id=str(queue.id),
            metadata={"queue_number": queue_number, "patient_id": str(payload.patient_id)},
        )

        # Phase 6: creating a Queue ticket automatically creates a linked
        # Visit in the same transaction, then links both FKs. This is the
        # documented creation order (Queue -> creates -> Visit) chosen to
        # avoid restructuring the already-verified Phase 5 flow: the queue
        # row/number/duplicate-check logic above is untouched, and this is
        # purely additive. See `VisitService.create_visit_for_queue`.
        visit = await self.visit_service.create_visit_for_queue(
            clinic_id=clinic_id,
            branch_id=payload.branch_id,
            patient_id=payload.patient_id,
            doctor_id=payload.doctor_id,
            department_id=payload.department_id,
            service_id=payload.service_id,
            priority=VisitPriority(payload.priority.value),
            actor_id=actor.id,
            visit_type=visit_type,
            remarks=payload.notes,
            queue_id=queue.id,
        )
        queue = await self.repo.update(queue, visit_id=visit.id)

        await self.session.commit()

        detail = await self.get_detail(queue.id, clinic_id=clinic_id)
        await queue_connection_manager.broadcast(clinic_id, "queue.created", detail.model_dump(mode="json"))
        await sync_queue_service.enqueue(
            entity_type="queue_ticket", record_id=queue.id, operation="create",
            payload=detail.model_dump(mode="json"), clinic_id=clinic_id,
        )
        await sync_queue_service.enqueue(
            entity_type="visit", record_id=visit.id, operation="create",
            payload={"visit_id": str(visit.id), "queue_id": str(queue.id)},
            clinic_id=clinic_id,
        )
        return detail

    async def search(self, *, clinic_id: UUID, params: QueueSearchParams) -> tuple[list[QueueListItem], int]:
        rows, total = await self.repo.search(clinic_id, params)

        # Reception Queue "Enter Vitals" button color: batched (one query
        # for the whole page, not one per row - see
        # `ConsultationRepository.get_latest_for_visits`) computation of
        # whether each ticket's linked visit already has all required
        # vitals recorded, reusing the exact same required-fields set/
        # completeness rule already enforced at print time
        # (`get_slip`/`_missing_required_vitals`) - no new "vitals status"
        # concept introduced.
        visit_ids = [q.visit_id for q in rows if q.visit_id is not None]
        required_fields = await self._required_vitals_fields(clinic_id)
        latest_by_visit = await self.consultation_repo.get_latest_for_visits(visit_ids, clinic_id)

        def vitals_taken_for(q: Queue) -> bool:
            if q.visit_id is None:
                return False
            consultation = latest_by_visit.get(q.visit_id)
            soap = getattr(consultation, "soap_note", None) if consultation else None
            if soap is None:
                return False
            return all(getattr(soap, field, None) not in (None, "") for field in required_fields)

        return [_to_list_item(q, vitals_taken=vitals_taken_for(q)) for q in rows], total

    async def get_detail(self, queue_id: UUID, *, clinic_id: UUID) -> QueueDetail:
        queue = await self.repo.get_with_relations(queue_id, clinic_id)
        if queue is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue ticket not found")
        history = await self.repo.get_history(queue_id, clinic_id)
        detail = _to_detail(queue, history)
        # Post-RC1 (Reception Queue Workflow Improvements): same room-label
        # resolution TV Display already uses for its "Please proceed to
        # Room X" announcement, exposed here so the Reception Queue page can
        # build the identical destination-aware announcement via the shared
        # `queue-announcer.ts` when the Receptionist calls/re-announces a
        # ticket - no separate destination concept introduced.
        settings = await self.setting_repo.list_for_clinic(clinic_id)
        detail.room_name = resolve_room_label(
            settings, branch_id=queue.branch_id, department_id=queue.department_id, doctor_id=queue.doctor_id
        )
        return detail

    async def update_queue(self, queue_id: UUID, payload: QueueUpdate, *, clinic_id: UUID, actor: User) -> QueueDetail:
        queue = await self.repo.get_by_id_and_clinic(queue_id, clinic_id)
        if queue is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue ticket not found")
        if queue.status in (QueueStatus.COMPLETED, QueueStatus.CANCELLED):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot edit a closed queue ticket.")

        updates = payload.model_dump(exclude_unset=True)
        department_id = updates.get("department_id", queue.department_id)
        doctor_id = updates.get("doctor_id", queue.doctor_id)
        service_id = updates.get("service_id", queue.service_id)

        await self._validate_and_fetch_entities(
            clinic_id, patient_id=queue.patient_id, department_id=department_id, doctor_id=doctor_id, service_id=service_id
        )

        updates["updated_by"] = actor.id
        queue = await self.repo.update(queue, **updates)

        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="queue.updated",
            entity_type="queue", entity_id=str(queue_id), metadata={"fields": list(updates.keys())},
        )
        await self.session.commit()

        detail = await self.get_detail(queue_id, clinic_id=clinic_id)
        await queue_connection_manager.broadcast(clinic_id, "queue.updated", detail.model_dump(mode="json"))
        await sync_queue_service.enqueue(
            entity_type="queue_ticket", record_id=queue_id, operation="update",
            payload=detail.model_dump(mode="json"), clinic_id=clinic_id,
        )
        return detail

    async def change_status(
        self,
        queue_id: UUID,
        *,
        clinic_id: UUID,
        actor: User,
        new_status: QueueStatus,
        note: str | None,
        expected_updated_at: datetime | None = None,
    ) -> QueueDetail:
        queue = await self.repo.get_by_id_and_clinic(queue_id, clinic_id)
        if queue is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue ticket not found")

        # Phase 5B (P1/P2, LR1): optimistic-concurrency guard against the
        # reproduced lost-update race - see `QueueStatusUpdate.expected_
        # updated_at`'s docstring. Same pattern as Laboratory's
        # `enter_results` (Phase 4I).
        if expected_updated_at is not None and queue.updated_at != expected_updated_at:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This queue ticket was updated by someone else since you last saw it. Reload and try again.",
            )

        allowed = QUEUE_STATUS_TRANSITIONS.get(queue.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot transition queue ticket from {queue.status.value} to {new_status.value}.",
            )

        from_status = queue.status
        now = datetime.now(UTC)
        field_updates: dict = {"status": new_status, "updated_by": actor.id}
        if new_status == QueueStatus.CALLED:
            field_updates["called_at"] = now
        elif new_status == QueueStatus.SERVING:
            field_updates["serving_started_at"] = now
        elif new_status == QueueStatus.COMPLETED:
            field_updates["completed_at"] = now

        queue = await self.repo.update(queue, **field_updates)
        await self.repo.add_history(
            clinic_id=clinic_id, queue_id=queue_id, from_status=from_status, to_status=new_status,
            changed_by=actor.id, note=note,
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="queue.status_changed",
            entity_type="queue", entity_id=str(queue_id),
            metadata={"from": from_status.value, "to": new_status.value},
        )
        await self.session.commit()

        detail = await self.get_detail(queue_id, clinic_id=clinic_id)
        await queue_connection_manager.broadcast(clinic_id, "queue.status_changed", detail.model_dump(mode="json"))
        await sync_queue_service.enqueue(
            entity_type="queue_ticket", record_id=queue_id, operation="update",
            payload=detail.model_dump(mode="json"), clinic_id=clinic_id,
        )
        return detail

    async def cancel(self, queue_id: UUID, *, clinic_id: UUID, actor: User, note: str | None = None) -> QueueDetail:
        return await self.change_status(
            queue_id, clinic_id=clinic_id, actor=actor, new_status=QueueStatus.CANCELLED, note=note or "Cancelled"
        )

    async def reannounce(self, queue_id: UUID, *, clinic_id: UUID, actor: User) -> QueueDetail:
        """Reception Queue Workflow Improvements: re-trigger the announcement
        for a ticket that has ALREADY been called, without creating a new
        ticket, changing the queue number, or moving queue state. Mirrors
        `DoctorWorkspaceService.recall_patient`'s exact idempotent pattern
        (same status in, same status out - `Called -> Called` is
        deliberately NOT in `QUEUE_STATUS_TRANSITIONS`, so this bypasses
        `change_status` entirely rather than adding a same-state edge to
        that transition map) - re-stamping `called_at` is what TV Display's
        existing `called_at`-diff already uses to detect "this needs
        announcing again", so no second "called" state is introduced."""
        queue = await self.repo.get_by_id_and_clinic(queue_id, clinic_id)
        if queue is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue ticket not found")
        if queue.status != QueueStatus.CALLED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only an already-called ticket can be re-announced.",
            )

        queue = await self.repo.update(queue, called_at=datetime.now(UTC), updated_by=actor.id)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="queue.reannounced",
            entity_type="queue", entity_id=str(queue_id), metadata={},
        )
        await self.session.commit()

        detail = await self.get_detail(queue_id, clinic_id=clinic_id)
        await queue_connection_manager.broadcast(clinic_id, "queue.status_changed", detail.model_dump(mode="json"))
        await sync_queue_service.enqueue(
            entity_type="queue_ticket", record_id=queue_id, operation="update",
            payload=detail.model_dump(mode="json"), clinic_id=clinic_id,
        )
        return detail

    async def get_slip(self, queue_id: UUID, *, clinic_id: UUID) -> QueueSlip:
        queue = await self.repo.get_with_relations(queue_id, clinic_id)
        if queue is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue ticket not found")

        # Reception Queue Workflow Improvements (Feature 1): the printable
        # slip is the point of enforcement, not the frontend Print button -
        # a direct API call still gets rejected. Only enforced when the
        # ticket has a linked Visit (the vitals-carrying record); every
        # Queue ticket created since Phase 6 has one (Queue creation always
        # transactionally creates/links a Visit - see `create_queue` below),
        # so this covers ticket creation. A ticket with no linked Visit at
        # all (only possible via pre-Phase-6 legacy data) is left unblocked
        # rather than guessing at vitals that were never structurally
        # capturable - a documented limitation, not a bypass.
        #
        # Laboratory tickets are exempt: a walk-in lab order has no
        # consultation/SOAP note to carry vitals in, so the requirement
        # doesn't apply to that department - identified by the same
        # `department_code == "LAB"` convention already used for the seeded
        # Laboratory department/service (see `models/department.py`,
        # `models/clinic_service.py`), not by matching the display name.
        is_laboratory_department = queue.department is not None and queue.department.department_code == "LAB"

        vitals_taken = True
        if queue.visit_id is not None:
            missing = await self._missing_required_vitals(queue.visit_id, clinic_id=clinic_id)
            if missing:
                if not is_laboratory_department:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Vital signs must be taken before printing the queue ticket.",
                    )
                vitals_taken = False
        else:
            vitals_taken = False

        clinic_stmt_result = await self.session.get(Clinic, clinic_id)
        clinic_name = clinic_stmt_result.name if clinic_stmt_result else ""

        return QueueSlip(
            queue_id=queue.id,
            queue_number=queue.queue_number,
            clinic_name=clinic_name,
            branch_name=queue.branch.name if queue.branch else "",
            patient_name=queue.patient.full_name if queue.patient else "",
            department_name=queue.department.name if queue.department else "",
            doctor_name=_full_name(queue.doctor) if queue.doctor else None,
            service_name=queue.service.service_name if queue.service else "",
            priority=queue.priority,
            queue_date=queue.queue_date,
            created_at=queue.created_at,
            vitals_taken=vitals_taken,
            qr_token=_slip_qr_token(clinic_id, queue.id),
        )
