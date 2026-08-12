"""Visit (encounter) service.

Real-world creation trigger: `QueueService.create_queue()` calls
`create_visit_for_queue()` internally, in the same DB transaction as the
queue-ticket insert, then links `queue.visit_id` back to the new visit (see
`services/queue_service.py`). `create_visit()` is also exposed directly for
completeness/testing (e.g. `POST /visits`), keeping the service layer honest
even though receptionists trigger visit creation exclusively via the Queue
flow per the product's Reception workflow.

Status transitions write both to `visit_timeline_events` (the domain-specific
timeline rendered on the Visit Details page) and to the generic
`audit_service` (the cross-cutting security/compliance audit trail).
"""

from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinic_service import ClinicService
from app.models.department import Department
from app.models.doctor import Doctor, DoctorStatus
from app.models.patient import Patient, PatientStatus
from app.models.visit import VISIT_STATUS_TRANSITIONS, Visit, VisitPriority, VisitStatus, VisitTimelineEventType, VisitType
from app.repositories.visit_repository import VisitRepository
from app.schemas.visit import (
    VisitCreate,
    VisitDetail,
    VisitListItem,
    VisitPreQueueCreate,
    VisitRead,
    VisitSearchParams,
    VisitTimelineEventRead,
    VisitUpdate,
)
from app.services.audit_service import AuditService
from app.services.visit_number_generator import VisitNumberGenerator
from app.services import sync_queue_service


def _full_name(entity) -> str:
    parts = [entity.first_name, getattr(entity, "middle_name", None), entity.last_name, getattr(entity, "suffix", None)]
    return " ".join(p for p in parts if p)


def _to_list_item(v: Visit) -> VisitListItem:
    return VisitListItem(
        id=v.id,
        visit_number=v.visit_number,
        visit_date=v.visit_date,
        visit_type=v.visit_type,
        status=v.status,
        priority=v.priority,
        branch_id=v.branch_id,
        patient_id=v.patient_id,
        patient_name=v.patient.full_name if v.patient else None,
        patient_number=v.patient.patient_number if v.patient else None,
        doctor_id=v.doctor_id,
        doctor_name=_full_name(v.doctor) if v.doctor else None,
        department_id=v.department_id,
        department_name=v.department.name if v.department else None,
        service_id=v.service_id,
        service_name=v.service.service_name if v.service else None,
        queue_id=v.queue_id,
        queue_number=v.queue.queue_number if v.queue else None,
        created_at=v.created_at,
    )


def _to_detail(v: Visit, timeline: list) -> VisitDetail:
    base = VisitRead.model_validate(v).model_dump()
    return VisitDetail(
        **base,
        patient_name=v.patient.full_name if v.patient else None,
        patient_number=v.patient.patient_number if v.patient else None,
        doctor_name=_full_name(v.doctor) if v.doctor else None,
        department_name=v.department.name if v.department else None,
        service_name=v.service.service_name if v.service else None,
        branch_name=v.branch.name if v.branch else None,
        queue_number=v.queue.queue_number if v.queue else None,
        timeline=[VisitTimelineEventRead.model_validate(t) for t in timeline],
    )


class VisitService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = VisitRepository(session)
        self.number_generator = VisitNumberGenerator(session)
        self.audit_service = AuditService(session)

    async def _validate_entities(
        self,
        clinic_id: UUID,
        *,
        patient_id: UUID,
        doctor_id: UUID | None,
        department_id: UUID | None,
        service_id: UUID | None,
    ) -> Patient:
        patient = await self.repo.get_active_entity(Patient, patient_id, clinic_id)
        if patient is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
        if patient.status == PatientStatus.ARCHIVED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot create a visit for an archived patient.")

        if doctor_id is not None:
            doctor = await self.repo.get_active_entity(Doctor, doctor_id, clinic_id)
            if doctor is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
            if doctor.status != DoctorStatus.ACTIVE:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected doctor is not active.")

        if department_id is not None:
            department = await self.repo.get_active_entity(Department, department_id, clinic_id)
            if department is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

        if service_id is not None:
            service = await self.repo.get_active_entity(ClinicService, service_id, clinic_id)
            if service is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

        return patient

    async def create_visit_for_queue(
        self,
        *,
        clinic_id: UUID,
        branch_id: UUID,
        patient_id: UUID,
        doctor_id: UUID | None,
        department_id: UUID | None,
        service_id: UUID | None,
        priority: VisitPriority,
        actor_id: UUID | None,
        visit_type: VisitType = VisitType.WALK_IN,
        remarks: str | None = None,
        queue_id: UUID | None = None,
    ) -> Visit:
        """Called internally from `QueueService.create_queue()`, in the same
        transaction as the queue-ticket insert. Does NOT commit - the caller
        (QueueService) owns the transaction boundary."""
        today = datetime.now(UTC).date()
        visit_number = await self.number_generator.next_number(clinic_id, branch_id, today)
        now = datetime.now(UTC)

        visit = await self.repo.create(
            clinic_id=clinic_id,
            branch_id=branch_id,
            patient_id=patient_id,
            queue_id=queue_id,
            doctor_id=doctor_id,
            department_id=department_id,
            service_id=service_id,
            visit_number=visit_number,
            visit_date=today,
            visit_type=visit_type,
            status=VisitStatus.WAITING,
            priority=priority,
            arrival_time=now,
            check_in_time=now,
            remarks=remarks,
            created_by=actor_id,
            updated_by=actor_id,
        )
        await self.repo.add_timeline_event(
            clinic_id=clinic_id,
            visit_id=visit.id,
            event_type=VisitTimelineEventType.REGISTERED,
            occurred_at=now,
            recorded_by=actor_id,
            note="Visit registered from queue ticket creation",
        )
        await self.repo.add_timeline_event(
            clinic_id=clinic_id,
            visit_id=visit.id,
            event_type=VisitTimelineEventType.QUEUED,
            occurred_at=now,
            recorded_by=actor_id,
            note="Added to reception queue",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="visit.created",
            entity_type="visit", entity_id=str(visit.id),
            metadata={"visit_number": visit_number, "patient_id": str(patient_id), "source": "queue"},
        )
        return visit

    async def create_draft_visit_for_pre_queue(
        self, payload: "VisitPreQueueCreate", *, clinic_id: UUID, actor_id: UUID | None
    ) -> VisitDetail:
        """Phase 21 (Vitals-before-Queue): the new entrypoint for
        `POST /visits/pre-queue`. Creates a Visit in `DRAFT_VITALS` status
        with `queue_id=None` - the inverse creation order from the normal
        Queue-creates-Visit flow (`create_visit_for_queue` above). The
        Consultation/vitals endpoints (`open_consultation_for_reception`,
        `save_soap_subjective_objective`) work against this Visit completely
        unmodified, since they only ever look at `visit_id`/`visit.doctor_id`.
        `QueueService.create_queue` later transitions this same Visit row
        from DRAFT_VITALS -> WAITING and attaches the Queue ticket, instead
        of creating a brand new Visit (see `queue_service.py`)."""
        await self._validate_entities(
            clinic_id,
            patient_id=payload.patient_id,
            doctor_id=payload.doctor_id,
            department_id=payload.department_id,
            service_id=payload.service_id,
        )

        today = datetime.now(UTC).date()
        visit_number = await self.number_generator.next_number(clinic_id, payload.branch_id, today)
        now = datetime.now(UTC)

        visit = await self.repo.create(
            clinic_id=clinic_id,
            branch_id=payload.branch_id,
            patient_id=payload.patient_id,
            queue_id=None,
            doctor_id=payload.doctor_id,
            department_id=payload.department_id,
            service_id=payload.service_id,
            visit_number=visit_number,
            visit_date=today,
            visit_type=payload.visit_type,
            status=VisitStatus.DRAFT_VITALS,
            priority=payload.priority,
            arrival_time=now,
            remarks=payload.remarks,
            created_by=actor_id,
            updated_by=actor_id,
        )
        await self.repo.add_timeline_event(
            clinic_id=clinic_id,
            visit_id=visit.id,
            event_type=VisitTimelineEventType.REGISTERED,
            occurred_at=now,
            recorded_by=actor_id,
            note="Visit registered for pre-queue vitals capture",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="visit.created",
            entity_type="visit", entity_id=str(visit.id),
            metadata={"visit_number": visit_number, "patient_id": str(payload.patient_id), "source": "pre_queue"},
        )
        await self.session.commit()
        detail = await self.get_detail(visit.id, clinic_id=clinic_id)
        # Post-RC1 Phase 2 Milestone 2: Cloud Backup - best-effort, never
        # affects this already-committed create (see sync_queue_service.py).
        await sync_queue_service.enqueue(
            entity_type="visit", record_id=visit.id, operation="create",
            payload=detail.model_dump(mode="json"), clinic_id=clinic_id,
        )
        return detail

    async def create_visit(self, payload: VisitCreate, *, clinic_id: UUID, actor_id: UUID | None) -> VisitDetail:
        """Standalone creation entrypoint (internal/test use - see module docstring)."""
        await self._validate_entities(
            clinic_id,
            patient_id=payload.patient_id,
            doctor_id=payload.doctor_id,
            department_id=payload.department_id,
            service_id=payload.service_id,
        )
        visit = await self.create_visit_for_queue(
            clinic_id=clinic_id,
            branch_id=payload.branch_id,
            patient_id=payload.patient_id,
            doctor_id=payload.doctor_id,
            department_id=payload.department_id,
            service_id=payload.service_id,
            priority=payload.priority,
            actor_id=actor_id,
            visit_type=payload.visit_type,
            remarks=payload.remarks,
        )
        await self.session.commit()
        return await self.get_detail(visit.id, clinic_id=clinic_id)

    async def search(self, *, clinic_id: UUID, params: VisitSearchParams) -> tuple[list[VisitListItem], int]:
        rows, total = await self.repo.search(clinic_id, params)
        return [_to_list_item(v) for v in rows], total

    async def list_for_patient(
        self, *, clinic_id: UUID, patient_id: UUID, limit: int = 50, offset: int = 0
    ) -> tuple[list[VisitListItem], int]:
        rows, total = await self.repo.list_for_patient(clinic_id, patient_id, limit=limit, offset=offset)
        return [_to_list_item(v) for v in rows], total

    async def get_detail(self, visit_id: UUID, *, clinic_id: UUID) -> VisitDetail:
        visit = await self.repo.get_with_relations(visit_id, clinic_id)
        if visit is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found")
        timeline = await self.repo.get_timeline(visit_id, clinic_id)
        return _to_detail(visit, timeline)

    async def get_timeline(self, visit_id: UUID, *, clinic_id: UUID) -> list[VisitTimelineEventRead]:
        visit = await self.repo.get_by_id_and_clinic(visit_id, clinic_id)
        if visit is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found")
        timeline = await self.repo.get_timeline(visit_id, clinic_id)
        return [VisitTimelineEventRead.model_validate(t) for t in timeline]

    async def update_visit(self, visit_id: UUID, payload: VisitUpdate, *, clinic_id: UUID, actor_id: UUID | None) -> VisitDetail:
        visit = await self.repo.get_by_id_and_clinic(visit_id, clinic_id)
        if visit is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found")
        if visit.status in (VisitStatus.COMPLETED, VisitStatus.CANCELLED):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot edit a closed visit.")

        updates = payload.model_dump(exclude_unset=True)
        doctor_id = updates.get("doctor_id", visit.doctor_id)
        department_id = updates.get("department_id", visit.department_id)
        service_id = updates.get("service_id", visit.service_id)

        await self._validate_entities(
            clinic_id, patient_id=visit.patient_id, doctor_id=doctor_id, department_id=department_id, service_id=service_id
        )

        updates["updated_by"] = actor_id
        visit = await self.repo.update(visit, **updates)

        await self.repo.add_timeline_event(
            clinic_id=clinic_id, visit_id=visit_id, event_type=VisitTimelineEventType.NOTE,
            occurred_at=datetime.now(UTC), recorded_by=actor_id,
            note=f"Visit updated: {', '.join(updates.keys())}",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="visit.updated",
            entity_type="visit", entity_id=str(visit_id), metadata={"fields": list(updates.keys())},
        )
        await self.session.commit()
        detail = await self.get_detail(visit_id, clinic_id=clinic_id)
        await sync_queue_service.enqueue(
            entity_type="visit", record_id=visit_id, operation="update",
            payload=detail.model_dump(mode="json"), clinic_id=clinic_id,
        )
        return detail

    async def change_status(
        self, visit_id: UUID, *, clinic_id: UUID, actor_id: UUID | None, new_status: VisitStatus, note: str | None
    ) -> VisitDetail:
        visit = await self.repo.get_by_id_and_clinic(visit_id, clinic_id)
        if visit is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found")

        allowed = VISIT_STATUS_TRANSITIONS.get(visit.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot transition visit from {visit.status.value} to {new_status.value}.",
            )

        from_status = visit.status
        now = datetime.now(UTC)
        field_updates: dict = {"status": new_status, "updated_by": actor_id}
        event_type = VisitTimelineEventType.STATUS_CHANGED
        if new_status == VisitStatus.CALLED:
            field_updates["called_time"] = now
            event_type = VisitTimelineEventType.CALLED
        elif new_status == VisitStatus.IN_CONSULTATION:
            field_updates["consultation_start"] = now
            event_type = VisitTimelineEventType.CONSULTATION_STARTED
        elif new_status == VisitStatus.COMPLETED:
            field_updates["consultation_end"] = now
            field_updates["check_out_time"] = now
            event_type = VisitTimelineEventType.CONSULTATION_FINISHED
        elif new_status == VisitStatus.CANCELLED:
            event_type = VisitTimelineEventType.CANCELLED

        visit = await self.repo.update(visit, **field_updates)
        await self.repo.add_timeline_event(
            clinic_id=clinic_id, visit_id=visit_id, event_type=event_type, occurred_at=now,
            recorded_by=actor_id, note=note,
            metadata={"from_status": from_status.value, "to_status": new_status.value},
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="visit.status_changed",
            entity_type="visit", entity_id=str(visit_id),
            metadata={"from": from_status.value, "to": new_status.value},
        )
        await self.session.commit()
        detail = await self.get_detail(visit_id, clinic_id=clinic_id)
        await sync_queue_service.enqueue(
            entity_type="visit", record_id=visit_id, operation="update",
            payload=detail.model_dump(mode="json"), clinic_id=clinic_id,
        )
        return detail
