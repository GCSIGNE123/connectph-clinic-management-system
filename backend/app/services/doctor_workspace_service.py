"""Doctor Workspace service (Phase 7).

Layers doctor-specific side effects (consultation sessions, doctor_activity
log, visit locking, WS broadcast) on top of `VisitService`, which remains
the single source of truth for Visit status transitions and
`visit_timeline_events`. This service never mutates `Visit.status`
directly - it always calls into `VisitService.change_status()` so the
legal-transition table in `models/visit.py` is only defined once.

Lock release/expiry policy (see `models/visit_lock.py` docstring for the
full rationale): a lock is released when (a) explicitly released, (b) the
visit reaches a terminal status, or (c) it has gone stale - older than
`LOCK_TTL_MINUTES` since `locked_at` with no refresh. `open_visit()` is
expected to be called periodically as a heartbeat by the frontend while a
visit viewer is mounted (see `use-doctor-actions.ts`).
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ws_manager import queue_connection_manager
from app.models.doctor import Doctor
from app.models.doctor_activity import DoctorActivityType
from app.models.queue import QUEUE_STATUS_TRANSITIONS, QueueStatus
from app.models.user import User
from app.models.visit import VisitStatus
from app.repositories.doctor_session_repository import DoctorSessionRepository
from app.repositories.doctor_workspace_repository import DoctorWorkspaceRepository
from app.schemas.doctor_workspace import LockInfo
from app.services.audit_service import AuditService
from app.services.queue_service import QueueService
from app.services.visit_service import VisitService

LOCK_TTL_MINUTES = 15

# The doctor-workspace actions drive Visit.status, but every Visit created
# from a Queue ticket (see queue_service.create_queue) keeps its own,
# separately-tracked Queue.status. Without this mapping, calling/starting/
# completing a visit from the Doctor Workspace would leave the linked Queue
# ticket permanently stuck (e.g. "Waiting" forever after the visit is
# Completed), which is visibly wrong on the Reception Queue screen even
# though the Visit itself is correct. VisitStatus.WAITING/REGISTERED have no
# entry because those are the Queue's own starting state - nothing to sync.
_VISIT_TO_QUEUE_STATUS: dict[VisitStatus, QueueStatus] = {
    VisitStatus.CALLED: QueueStatus.CALLED,
    VisitStatus.IN_CONSULTATION: QueueStatus.SERVING,
    VisitStatus.COMPLETED: QueueStatus.COMPLETED,
    VisitStatus.NO_SHOW: QueueStatus.NO_SHOW,
    VisitStatus.CANCELLED: QueueStatus.CANCELLED,
}


class DoctorWorkspaceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = DoctorWorkspaceRepository(session)
        self.session_repo = DoctorSessionRepository(session)
        self.visit_service = VisitService(session)
        self.queue_service = QueueService(session)
        self.audit_service = AuditService(session)

    async def _require_visit(self, visit_id: UUID, clinic_id: UUID):
        visit = await self.repo.get_visit(visit_id, clinic_id)
        if visit is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found")
        return visit

    async def _sync_queue_status(
        self, visit, *, clinic_id: UUID, actor_id: UUID, new_visit_status: VisitStatus, note: str
    ) -> None:
        """Mirror a Visit status transition onto its linked Queue ticket, if any."""
        target_status = _VISIT_TO_QUEUE_STATUS.get(new_visit_status)
        if target_status is None or visit.queue_id is None:
            return
        queue = await self.queue_service.repo.get_by_id_and_clinic(visit.queue_id, clinic_id)
        if queue is None or queue.status == target_status:
            return
        if target_status not in QUEUE_STATUS_TRANSITIONS.get(queue.status, set()):
            # Queue ticket already moved on its own (e.g. reception cancelled
            # it) - don't force an illegal transition, the Visit stays the
            # source of truth for clinical status either way.
            return
        actor = await self.session.get(User, actor_id)
        if actor is None:
            return
        await self.queue_service.change_status(
            visit.queue_id, clinic_id=clinic_id, actor=actor, new_status=target_status, note=note
        )

    async def _broadcast(self, clinic_id: UUID, event: str, payload: dict) -> None:
        await queue_connection_manager.broadcast(clinic_id, event, payload)

    def _require_doctor_of_visit(self, visit, *, doctor_id: UUID | None, is_privileged: bool) -> None:
        """Doctor-role callers may only act on visits assigned to them;
        Owner/Administrator ("privileged") may act on any visit."""
        if is_privileged:
            return
        if doctor_id is None or visit.doctor_id != doctor_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This visit is not assigned to you.")

    # --- Dashboard / queue ---

    async def get_dashboard(self, *, clinic_id: UUID, doctor: Doctor | None, visit_date):
        counts = await self.repo.status_counts(clinic_id=clinic_id, doctor_id=doctor.id if doctor else None, visit_date=visit_date)
        avg_seconds = await self.repo.avg_duration_seconds(
            clinic_id=clinic_id, doctor_id=doctor.id if doctor else None, visit_date=visit_date
        )
        from app.schemas.doctor_workspace import DoctorDashboardResponse, DoctorDashboardStats

        stats = DoctorDashboardStats(
            waiting=counts.get(VisitStatus.WAITING.value, 0),
            called=counts.get(VisitStatus.CALLED.value, 0),
            serving=counts.get(VisitStatus.IN_CONSULTATION.value, 0),
            completed_today=counts.get(VisitStatus.COMPLETED.value, 0),
            cancelled=counts.get(VisitStatus.CANCELLED.value, 0),
            no_show=counts.get(VisitStatus.NO_SHOW.value, 0),
            avg_consultation_seconds=avg_seconds,
        )
        return DoctorDashboardResponse(
            today=visit_date,
            doctor_id=doctor.id if doctor else None,
            doctor_name=doctor.full_name if doctor else None,
            branch_name=doctor.branch.name if doctor and doctor.branch else None,
            department_name=doctor.department.name if doctor and doctor.department else None,
            stats=stats,
        )

    async def get_queue(self, *, clinic_id: UUID, doctor: Doctor | None, visit_date, current_user_id: UUID):
        from app.schemas.doctor_workspace import DoctorQueueItem, DoctorQueueResponse

        visits = await self.repo.today_visits_for_doctor(
            clinic_id=clinic_id, doctor_id=doctor.id if doctor else None, visit_date=visit_date
        )
        now = datetime.now(UTC)
        items: list[DoctorQueueItem] = []
        for v in visits:
            lock = await self.repo.get_active_lock(v.id, clinic_id)
            waiting_seconds = None
            if v.status == VisitStatus.WAITING and v.arrival_time is not None:
                waiting_seconds = (now - v.arrival_time).total_seconds()
            age = None
            if v.patient is not None and v.patient.birth_date is not None:
                today = now.date()
                bd = v.patient.birth_date
                age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
            items.append(
                DoctorQueueItem(
                    visit_id=v.id,
                    visit_number=v.visit_number,
                    queue_id=v.queue_id,
                    queue_number=v.queue.queue_number if v.queue else None,
                    patient_id=v.patient_id,
                    patient_name=v.patient.full_name if v.patient else "",
                    patient_number=v.patient.patient_number if v.patient else "",
                    age=age,
                    gender=v.patient.gender.value if v.patient and v.patient.gender else None,
                    priority=v.priority,
                    status=v.status,
                    visit_type=v.visit_type,
                    arrival_time=v.arrival_time,
                    called_time=v.called_time,
                    consultation_start=v.consultation_start,
                    waiting_seconds=waiting_seconds,
                    is_locked=lock is not None,
                    locked_by_name=lock.locked_by_user.full_name if lock and lock.locked_by_user else None,
                    locked_by_self=bool(lock and lock.locked_by == current_user_id),
                )
            )
        return DoctorQueueResponse(items=items, total=len(items))

    # --- Actions ---

    async def call_patient(self, visit_id: UUID, *, clinic_id: UUID, doctor: Doctor | None, actor_id: UUID, is_privileged: bool):
        visit = await self._require_visit(visit_id, clinic_id)
        self._require_doctor_of_visit(visit, doctor_id=doctor.id if doctor else None, is_privileged=is_privileged)
        detail = await self.visit_service.change_status(
            visit_id, clinic_id=clinic_id, actor_id=actor_id, new_status=VisitStatus.CALLED, note="Patient called by doctor"
        )
        await self._sync_queue_status(
            visit, clinic_id=clinic_id, actor_id=actor_id, new_visit_status=VisitStatus.CALLED, note="Patient called by doctor"
        )
        target_doctor_id = visit.doctor_id or (doctor.id if doctor else None)
        if target_doctor_id is not None:
            await self.repo.log_activity(
                clinic_id=clinic_id, doctor_id=target_doctor_id, user_id=actor_id, visit_id=visit_id,
                activity_type=DoctorActivityType.PATIENT_CALLED, occurred_at=datetime.now(UTC),
            )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="doctor_workspace.patient_called",
            entity_type="visit", entity_id=str(visit_id),
        )
        await self.session.commit()
        await self._broadcast(clinic_id, "visit.called", {"visit_id": str(visit_id), "doctor_id": str(target_doctor_id) if target_doctor_id else None})
        return detail

    async def recall_patient(self, visit_id: UUID, *, clinic_id: UUID, doctor: Doctor | None, actor_id: UUID, is_privileged: bool):
        visit = await self._require_visit(visit_id, clinic_id)
        self._require_doctor_of_visit(visit, doctor_id=doctor.id if doctor else None, is_privileged=is_privileged)
        if visit.status != VisitStatus.CALLED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only a Called visit can be recalled.")
        # Bug fix (RC1 UAT): a Recall previously left the linked Queue
        # ticket's `called_at` untouched (the visit/queue status was already
        # `Called`, so `change_status`/`_sync_queue_status`'s no-op guard on
        # "already at target status" never ran). Downstream consumers -
        # most importantly the public TV Display, which detects a "new
        # call" (and fires the audible announcement) by diffing each
        # ticket's `called_at` - had no signal that a recall had happened
        # at all, so recalling a patient silently did not re-announce them.
        # Refresh `called_at` directly here (bypassing the status-transition
        # machinery since the status itself isn't changing) so every
        # consumer of that timestamp sees the recall as a fresh call event.
        if visit.queue_id is not None:
            queue = await self.queue_service.repo.get_by_id_and_clinic(visit.queue_id, clinic_id)
            if queue is not None:
                await self.queue_service.repo.update(queue, called_at=datetime.now(UTC))
        target_doctor_id = visit.doctor_id or (doctor.id if doctor else None)
        if target_doctor_id is not None:
            await self.repo.log_activity(
                clinic_id=clinic_id, doctor_id=target_doctor_id, user_id=actor_id, visit_id=visit_id,
                activity_type=DoctorActivityType.PATIENT_RECALLED, occurred_at=datetime.now(UTC),
            )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="doctor_workspace.patient_recalled",
            entity_type="visit", entity_id=str(visit_id),
        )
        await self.session.commit()
        await self._broadcast(clinic_id, "visit.called", {"visit_id": str(visit_id), "recall": True, "doctor_id": str(target_doctor_id) if target_doctor_id else None})
        return await self.visit_service.get_detail(visit_id, clinic_id=clinic_id)

    async def start_consultation(self, visit_id: UUID, *, clinic_id: UUID, doctor: Doctor | None, actor_id: UUID, is_privileged: bool):
        visit = await self._require_visit(visit_id, clinic_id)
        self._require_doctor_of_visit(visit, doctor_id=doctor.id if doctor else None, is_privileged=is_privileged)
        effective_doctor_id = visit.doctor_id or (doctor.id if doctor else None)
        if effective_doctor_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Visit has no assigned doctor.")
        detail = await self.visit_service.change_status(
            visit_id, clinic_id=clinic_id, actor_id=actor_id, new_status=VisitStatus.IN_CONSULTATION, note="Consultation started"
        )
        await self._sync_queue_status(
            visit, clinic_id=clinic_id, actor_id=actor_id, new_visit_status=VisitStatus.IN_CONSULTATION, note="Consultation started"
        )
        now = datetime.now(UTC)
        await self.repo.create_session(clinic_id=clinic_id, visit_id=visit_id, doctor_id=effective_doctor_id, started_at=now)
        await self.repo.log_activity(
            clinic_id=clinic_id, doctor_id=effective_doctor_id, user_id=actor_id, visit_id=visit_id,
            activity_type=DoctorActivityType.CONSULTATION_STARTED, occurred_at=now,
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="doctor_workspace.consultation_started",
            entity_type="visit", entity_id=str(visit_id),
        )
        await self.session.commit()
        await self._broadcast(clinic_id, "visit.consultation_started", {"visit_id": str(visit_id)})
        return detail

    async def complete_consultation(self, visit_id: UUID, *, clinic_id: UUID, doctor: Doctor | None, actor_id: UUID, is_privileged: bool):
        visit = await self._require_visit(visit_id, clinic_id)
        self._require_doctor_of_visit(visit, doctor_id=doctor.id if doctor else None, is_privileged=is_privileged)
        effective_doctor_id = visit.doctor_id or (doctor.id if doctor else None)
        detail = await self.visit_service.change_status(
            visit_id, clinic_id=clinic_id, actor_id=actor_id, new_status=VisitStatus.COMPLETED, note="Consultation completed"
        )
        await self._sync_queue_status(
            visit, clinic_id=clinic_id, actor_id=actor_id, new_visit_status=VisitStatus.COMPLETED, note="Consultation completed"
        )
        now = datetime.now(UTC)
        active_session = await self.repo.get_active_session(visit_id, clinic_id)
        if active_session is not None:
            await self.repo.end_session(active_session, ended_at=now)
        if effective_doctor_id is not None:
            await self.repo.log_activity(
                clinic_id=clinic_id, doctor_id=effective_doctor_id, user_id=actor_id, visit_id=visit_id,
                activity_type=DoctorActivityType.CONSULTATION_COMPLETED, occurred_at=now,
            )
        await self.repo.release_all_locks_for_visit(visit_id, clinic_id, released_at=now)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="doctor_workspace.consultation_completed",
            entity_type="visit", entity_id=str(visit_id),
        )

        # Doctor Workspace <-> Consultation Workspace billing parity: per the
        # spec's workflow diagram ("Doctor marks Consultation Complete ->
        # Billing Draft automatically created"), completing an encounter
        # auto-creates a Draft invoice for the visit - this used to only
        # happen via `ConsultationService.complete_consultation()` (the full
        # SOAP-note Consultation Workspace flow), not via this quicker
        # Doctor Workspace "Complete"/"Next Patient" action, so a doctor
        # checking a patient out from the queue table left the visit
        # correctly "Completed" but silently unbilled. Reuses the exact same
        # `InvoiceService.create_draft_invoice_for_consultation()` call
        # `ConsultationService` already makes - no second invoice-generation
        # implementation - which is itself idempotent (returns the existing
        # non-cancelled invoice for this visit rather than duplicating), so
        # this is safe even if the visit was already billed via the other
        # path, and safe against retries.
        from app.services.invoice_service import InvoiceService

        invoice_service = InvoiceService(self.session)
        await invoice_service.create_draft_invoice_for_consultation(
            clinic_id=clinic_id, visit_id=visit_id, actor_id=actor_id,
        )

        await self.session.commit()
        await self._broadcast(clinic_id, "visit.consultation_completed", {"visit_id": str(visit_id)})
        await self._broadcast(clinic_id, "visit.lock_released", {"visit_id": str(visit_id)})
        return detail

    async def mark_no_show(self, visit_id: UUID, *, clinic_id: UUID, doctor: Doctor | None, actor_id: UUID, is_privileged: bool):
        visit = await self._require_visit(visit_id, clinic_id)
        self._require_doctor_of_visit(visit, doctor_id=doctor.id if doctor else None, is_privileged=is_privileged)
        target_doctor_id = visit.doctor_id or (doctor.id if doctor else None)
        detail = await self.visit_service.change_status(
            visit_id, clinic_id=clinic_id, actor_id=actor_id, new_status=VisitStatus.NO_SHOW, note="Marked no-show"
        )
        await self._sync_queue_status(
            visit, clinic_id=clinic_id, actor_id=actor_id, new_visit_status=VisitStatus.NO_SHOW, note="Marked no-show"
        )
        now = datetime.now(UTC)
        if target_doctor_id is not None:
            await self.repo.log_activity(
                clinic_id=clinic_id, doctor_id=target_doctor_id, user_id=actor_id, visit_id=visit_id,
                activity_type=DoctorActivityType.MARKED_NO_SHOW, occurred_at=now,
            )
        await self.repo.release_all_locks_for_visit(visit_id, clinic_id, released_at=now)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="doctor_workspace.marked_no_show",
            entity_type="visit", entity_id=str(visit_id),
        )
        await self.session.commit()
        await self._broadcast(clinic_id, "visit.status_changed", {"visit_id": str(visit_id), "status": VisitStatus.NO_SHOW.value})
        return detail

    async def cancel_visit(self, visit_id: UUID, *, clinic_id: UUID, doctor: Doctor | None, actor_id: UUID, is_privileged: bool, reason: str | None):
        visit = await self._require_visit(visit_id, clinic_id)
        self._require_doctor_of_visit(visit, doctor_id=doctor.id if doctor else None, is_privileged=is_privileged)
        target_doctor_id = visit.doctor_id or (doctor.id if doctor else None)
        detail = await self.visit_service.change_status(
            visit_id, clinic_id=clinic_id, actor_id=actor_id, new_status=VisitStatus.CANCELLED, note=reason or "Visit cancelled"
        )
        await self._sync_queue_status(
            visit, clinic_id=clinic_id, actor_id=actor_id, new_visit_status=VisitStatus.CANCELLED, note=reason or "Visit cancelled"
        )
        now = datetime.now(UTC)
        if target_doctor_id is not None:
            await self.repo.log_activity(
                clinic_id=clinic_id, doctor_id=target_doctor_id, user_id=actor_id, visit_id=visit_id,
                activity_type=DoctorActivityType.VISIT_CANCELLED, occurred_at=now, metadata={"reason": reason},
            )
        await self.repo.release_all_locks_for_visit(visit_id, clinic_id, released_at=now)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="doctor_workspace.visit_cancelled",
            entity_type="visit", entity_id=str(visit_id), metadata={"reason": reason},
        )
        await self.session.commit()
        await self._broadcast(clinic_id, "visit.status_changed", {"visit_id": str(visit_id), "status": VisitStatus.CANCELLED.value})
        return detail

    # --- Locking ---

    async def open_visit(self, visit_id: UUID, *, clinic_id: UUID, doctor: Doctor | None, actor_id: UUID, is_privileged: bool) -> LockInfo:
        visit = await self._require_visit(visit_id, clinic_id)
        self._require_doctor_of_visit(visit, doctor_id=doctor.id if doctor else None, is_privileged=is_privileged)

        now = datetime.now(UTC)
        existing = await self.repo.get_active_lock(visit_id, clinic_id)

        if existing is not None:
            stale = (now - existing.locked_at) > timedelta(minutes=LOCK_TTL_MINUTES)
            if existing.locked_by == actor_id:
                # Same user re-opening / heartbeat - refresh by replacing the lock row.
                await self.repo.release_lock(existing, released_at=now)
                new_lock = await self.repo.create_lock(clinic_id=clinic_id, visit_id=visit_id, locked_by=actor_id, locked_at=now)
                await self.session.commit()
                return LockInfo(locked=True, locked_by=actor_id, locked_by_name=new_lock.locked_by_user.full_name, locked_at=now, is_self=True)
            if stale:
                await self.repo.release_lock(existing, released_at=now)
                new_lock = await self.repo.create_lock(clinic_id=clinic_id, visit_id=visit_id, locked_by=actor_id, locked_at=now)
                if doctor is not None:
                    await self.repo.log_activity(
                        clinic_id=clinic_id, doctor_id=doctor.id, user_id=actor_id, visit_id=visit_id,
                        activity_type=DoctorActivityType.VISIT_OPENED, occurred_at=now,
                    )
                await self.session.commit()
                await self._broadcast(clinic_id, "visit.lock_acquired", {"visit_id": str(visit_id), "locked_by": str(actor_id)})
                return LockInfo(locked=True, locked_by=actor_id, locked_by_name=new_lock.locked_by_user.full_name, locked_at=now, is_self=True)
            # Held by someone else and still fresh - return lock info, no edit access granted.
            return LockInfo(
                locked=True, locked_by=existing.locked_by,
                locked_by_name=existing.locked_by_user.full_name if existing.locked_by_user else None,
                locked_at=existing.locked_at, is_self=False,
            )

        new_lock = await self.repo.create_lock(clinic_id=clinic_id, visit_id=visit_id, locked_by=actor_id, locked_at=now)
        if doctor is not None:
            await self.repo.log_activity(
                clinic_id=clinic_id, doctor_id=doctor.id, user_id=actor_id, visit_id=visit_id,
                activity_type=DoctorActivityType.VISIT_OPENED, occurred_at=now,
            )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="doctor_workspace.visit_opened",
            entity_type="visit", entity_id=str(visit_id),
        )
        await self.session.commit()
        await self._broadcast(clinic_id, "visit.lock_acquired", {"visit_id": str(visit_id), "locked_by": str(actor_id)})
        return LockInfo(locked=True, locked_by=actor_id, locked_by_name=new_lock.locked_by_user.full_name, locked_at=now, is_self=True)

    async def release_lock(self, visit_id: UUID, *, clinic_id: UUID, actor_id: UUID) -> LockInfo:
        existing = await self.repo.get_active_lock(visit_id, clinic_id)
        now = datetime.now(UTC)
        if existing is None or existing.locked_by != actor_id:
            return LockInfo(locked=False)
        await self.repo.release_lock(existing, released_at=now)
        await self.session.commit()
        await self._broadcast(clinic_id, "visit.lock_released", {"visit_id": str(visit_id)})
        return LockInfo(locked=False)

    # --- Doctor Session Control (Client Acceptance Revisions Round 3, item 14) ---
    #
    # A `DoctorSession` is purely a "this doctor is actively receiving
    # patients today" flag/gate - it does NOT block Reception's existing
    # per-ticket Call action (that "Manual Queue Override" must keep working
    # "regardless of session state" per the spec), so no enforcement was
    # added anywhere else. It exists so (a) the Doctor Workspace can show a
    # clear started/not-started state and (b) "Next Patient" has a
    # `started_by`/`started_at` anchor to reason about, not as a hard gate.

    async def get_session_status(self, *, clinic_id: UUID, doctor_id: UUID):
        from app.schemas.doctor_workspace import DoctorSessionStatus

        open_session = await self.session_repo.get_open_for_doctor(clinic_id=clinic_id, doctor_id=doctor_id)
        return DoctorSessionStatus(
            active=open_session is not None,
            started_at=open_session.started_at if open_session else None,
        )

    async def start_session(self, *, clinic_id: UUID, doctor_id: UUID, actor_id: UUID):
        from app.schemas.doctor_workspace import DoctorSessionStatus

        existing = await self.session_repo.get_open_for_doctor(clinic_id=clinic_id, doctor_id=doctor_id)
        if existing is not None:
            return DoctorSessionStatus(active=True, started_at=existing.started_at)
        now = datetime.now(UTC)
        # The (clinic_id, doctor_id, session_date) unique constraint means a
        # doctor who already ended a session earlier today must reopen that
        # same row, not insert a second one for the same date - inserting
        # unconditionally here previously hit the constraint and raised an
        # unhandled IntegrityError (500) on any same-day restart.
        todays_row = await self.session_repo.get_for_doctor_and_date(
            clinic_id=clinic_id, doctor_id=doctor_id, session_date=now.date()
        )
        if todays_row is not None:
            todays_row.started_at = now
            todays_row.started_by = actor_id
            todays_row.ended_at = None
            await self.session.flush()
            session_row = todays_row
        else:
            session_row = await self.session_repo.create(
                clinic_id=clinic_id, doctor_id=doctor_id, session_date=now.date(), started_at=now, started_by=actor_id,
            )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="doctor_workspace.session_started",
            entity_type="doctor_session", entity_id=str(session_row.id), metadata={"doctor_id": str(doctor_id)},
        )
        await self.session.commit()
        await self._broadcast(clinic_id, "doctor_session.started", {"doctor_id": str(doctor_id)})
        return DoctorSessionStatus(active=True, started_at=now)

    async def end_session(self, *, clinic_id: UUID, doctor_id: UUID, actor_id: UUID):
        from app.schemas.doctor_workspace import DoctorSessionStatus

        existing = await self.session_repo.get_open_for_doctor(clinic_id=clinic_id, doctor_id=doctor_id)
        if existing is None:
            return DoctorSessionStatus(active=False, started_at=None)
        now = datetime.now(UTC)
        await self.session_repo.end(existing, ended_at=now)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="doctor_workspace.session_ended",
            entity_type="doctor_session", entity_id=str(existing.id), metadata={"doctor_id": str(doctor_id)},
        )
        await self.session.commit()
        await self._broadcast(clinic_id, "doctor_session.ended", {"doctor_id": str(doctor_id)})
        return DoctorSessionStatus(active=False, started_at=None)

    async def next_patient(self, *, clinic_id: UUID, doctor: Doctor, actor_id: UUID, visit_date):
        """"Next Patient": completes/moves past whichever visit is currently
        Called or InConsultation for this doctor (if any), then calls the
        earliest Waiting visit for this doctor (if any). Reuses
        `complete_consultation`/`call_patient` above rather than
        duplicating their Visit<->Queue sync / activity-log / broadcast
        logic - this method is just an orchestrator over them."""
        visits = await self.repo.today_visits_for_doctor(clinic_id=clinic_id, doctor_id=doctor.id, visit_date=visit_date)

        current = next((v for v in visits if v.status in (VisitStatus.CALLED, VisitStatus.IN_CONSULTATION)), None)
        if current is not None:
            if current.status == VisitStatus.IN_CONSULTATION:
                await self.complete_consultation(
                    current.id, clinic_id=clinic_id, doctor=doctor, actor_id=actor_id, is_privileged=True
                )
            else:
                # Called but never started (e.g. a no-show-in-progress) -
                # cancelling it here would be presumptuous; simplest safe
                # move-past is marking it no-show so it stops blocking the
                # doctor's "current" slot without destroying its record.
                await self.mark_no_show(
                    current.id, clinic_id=clinic_id, doctor=doctor, actor_id=actor_id, is_privileged=True
                )
            # Re-fetch: the visit we just moved past should no longer be
            # eligible, and its completion may have changed queue ordering.
            visits = await self.repo.today_visits_for_doctor(clinic_id=clinic_id, doctor_id=doctor.id, visit_date=visit_date)

        next_waiting = next((v for v in visits if v.status == VisitStatus.WAITING), None)
        if next_waiting is None:
            return None
        return await self.call_patient(
            next_waiting.id, clinic_id=clinic_id, doctor=doctor, actor_id=actor_id, is_privileged=True
        )
