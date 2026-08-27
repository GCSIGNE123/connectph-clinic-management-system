"""Clinical Consultation / SOAP service (Phase 8).

Layers on top of `VisitService` and reuses Phase 7's `visit_locks` (via
`DoctorWorkspaceRepository`) for locking, keyed by `visit_id` - a Visit and
its Consultation are 1:1, so a lock on the visit already covers "the
consultation for this visit" (see `models/consultation.py` docstring).

Consultation <-> Visit status-sync design decision (Phase 7 lesson applied):
`complete_consultation()` transitions `Consultation.status` to `Completed`
and then calls `VisitService.change_status(..., VisitStatus.COMPLETED)` the
same way `DoctorWorkspaceService` does, so the Visit always reflects a
completed clinical encounter. If the Visit is already `Completed` (e.g. the
doctor used the Doctor Workspace's "Complete Consultation" button first),
the transition is treated as an idempotent no-op rather than an error -
this mirrors `VISIT_STATUS_TRANSITIONS[COMPLETED] == set()` from
`models/visit.py`.

Consultation <-> Queue status-sync: completing a Consultation is *another*
independent path (besides the Doctor Workspace) that can complete a Visit,
so it must ALSO mirror `DoctorWorkspaceService._sync_queue_status` and
transition the linked Queue ticket - otherwise a Visit completed purely via
`POST /consultations/{id}/complete` (without ever hitting the Doctor
Workspace "Complete Consultation" button) leaves the Reception Queue screen
showing a ticket stuck "Serving"/"Waiting" forever, which is exactly the
Phase 7 bug this project already got bitten by once, one hop further down
the call chain. `_sync_queue_status` below is a deliberate near-duplicate of
`DoctorWorkspaceService._sync_queue_status` (same tolerant "don't force an
illegal Queue transition" behaviour) rather than a shared import, to keep
this service's only dependency on doctor-workspace internals limited to the
lock repository it already reuses.

Autosave-idempotency design: `save_soap()` only writes a
`visit_timeline_events`/audit entry when the submitted payload actually
differs from what is already stored (or on the very first save that puts
real content in a previously-empty note). A 30-second autosave interval
that resubmits unchanged content therefore updates `soap_notes.updated_at`
silently but never spams the timeline or audit log.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consultation import CONSULTATION_STATUS_TRANSITIONS, Consultation, ConsultationStatus
from app.models.consultation_attachment import ConsultationAttachment
from app.models.diagnosis import Diagnosis
from app.models.doctor import resolve_workspace_config
from app.models.order import OrderCategory
from app.models.queue import QUEUE_STATUS_TRANSITIONS, QueueStatus
from app.models.user import User
from app.models.visit import VisitStatus, VisitTimelineEventType
from app.repositories.consultation_repository import ConsultationRepository
from app.repositories.doctor_workspace_repository import DoctorWorkspaceRepository
from app.repositories.visit_repository import VisitRepository
from app.services.queue_service import QueueService
from app.schemas.consultation import (
    AttachmentRead,
    ConsultationDetail,
    DiagnosisRead,
    SoapNoteRead,
)
from app.schemas.doctor_workspace import LockInfo
from app.services.audit_service import AuditService
from app.services.visit_service import VisitService
from app.services import sync_queue_service

LOCK_TTL_MINUTES = 15
SOAP_FIELDS = [
    "chief_complaint", "history_of_present_illness", "past_medical_history", "family_history",
    "social_history", "review_of_systems", "subjective_notes",
    "blood_pressure", "pulse_rate", "respiratory_rate", "temperature", "height_cm", "weight_kg",
    "oxygen_saturation", "pain_score", "head_circumference_cm", "physical_examination", "clinical_findings",
    "clinical_impression", "differential_diagnosis", "assessment_notes",
    "treatment_plan", "patient_instructions", "followup_recommendation", "referral_notes",
]
# Phase 20 (items 4-5): the subset of SOAP_FIELDS a Receptionist/Nurse may
# write via `save_soap_subjective_objective` below - Subjective + Objective/
# vitals only. Assessment/Plan fields are never touched by that method.
# Phase 21 additionally added `pain_score`/`head_circumference_cm` here -
# both optional vitals fields the Vitals-before-Queue flow may submit.
SUBJECTIVE_OBJECTIVE_FIELDS = [
    "chief_complaint", "history_of_present_illness", "past_medical_history", "family_history",
    "social_history", "review_of_systems", "subjective_notes",
    "blood_pressure", "pulse_rate", "respiratory_rate", "temperature", "height_cm", "weight_kg",
    "oxygen_saturation", "pain_score", "head_circumference_cm", "physical_examination", "clinical_findings",
]


def _compute_bmi(height_cm: float | None, weight_kg: float | None) -> float | None:
    if not height_cm or not weight_kg or height_cm <= 0:
        return None
    height_m = height_cm / 100
    return round(weight_kg / (height_m * height_m), 2)


def attachment_to_read(attachment) -> AttachmentRead:
    """Builds the API-facing `file_url` as a path into
    `GET /consultations/{id}/attachments/{id}/file` (see
    `api/v1/consultations.py::get_attachment_file`), rather than exposing
    the raw on-disk filename stored in the `file_url` column. Shared by
    both `list_attachments`/the upload endpoint and `_to_detail` below, so
    every place a consultation's attachments are serialized resolves to
    the same real, authenticated, viewable URL."""
    return AttachmentRead(
        id=attachment.id,
        consultation_id=attachment.consultation_id,
        attachment_type=attachment.attachment_type,
        file_name=attachment.file_name,
        file_url=f"/consultations/{attachment.consultation_id}/attachments/{attachment.id}/file",
        file_size_bytes=attachment.file_size_bytes,
        uploaded_by=attachment.uploaded_by,
        created_at=attachment.created_at,
    )


class ConsultationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ConsultationRepository(session)
        self.visit_repo = VisitRepository(session)
        self.lock_repo = DoctorWorkspaceRepository(session)
        self.visit_service = VisitService(session)
        self.queue_service = QueueService(session)
        self.audit_service = AuditService(session)
        self._invoice_service = None  # lazy import to avoid a circular import at module load

    async def _sync_queue_status(self, visit, *, clinic_id: UUID, actor_id: UUID, note: str) -> None:
        """Mirror a completed Visit onto its linked Queue ticket, if any -
        see module docstring for why this duplicates
        `DoctorWorkspaceService._sync_queue_status` rather than sharing it."""
        if visit.queue_id is None:
            return
        queue = await self.queue_service.repo.get_by_id_and_clinic(visit.queue_id, clinic_id)
        if queue is None or queue.status == QueueStatus.COMPLETED:
            return
        if QueueStatus.COMPLETED not in QUEUE_STATUS_TRANSITIONS.get(queue.status, set()):
            return
        actor = await self.session.get(User, actor_id)
        if actor is None:
            return
        await self.queue_service.change_status(
            visit.queue_id, clinic_id=clinic_id, actor=actor, new_status=QueueStatus.COMPLETED, note=note
        )

    async def _require_visit(self, visit_id: UUID, clinic_id: UUID):
        visit = await self.visit_repo.get_with_relations(visit_id, clinic_id)
        if visit is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found")
        return visit

    async def _require_consultation(self, consultation_id: UUID, clinic_id: UUID) -> Consultation:
        consultation = await self.repo.get_by_id(consultation_id, clinic_id)
        if consultation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")
        return consultation

    def _require_can_edit(self, can_edit: bool) -> None:
        if not can_edit:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have edit access to this consultation.")

    async def _lock_info(self, visit_id: UUID, clinic_id: UUID, current_user_id: UUID) -> LockInfo:
        lock = await self.lock_repo.get_active_lock(visit_id, clinic_id)
        if lock is None:
            return LockInfo(locked=False)
        return LockInfo(
            locked=True, locked_by=lock.locked_by,
            locked_by_name=lock.locked_by_user.full_name if lock.locked_by_user else None,
            locked_at=lock.locked_at, is_self=bool(lock.locked_by == current_user_id),
        )

    def _to_detail(self, consultation: Consultation, *, soap, diagnoses, attachments, lock: LockInfo) -> ConsultationDetail:
        from app.schemas.consultation import ConsultationRead
        base = ConsultationRead.model_validate(consultation, from_attributes=True).model_dump()
        return ConsultationDetail(
            **base,
            doctor_name=consultation.doctor.full_name if consultation.doctor else None,
            doctor_prc_license=consultation.doctor.prc_license if consultation.doctor else None,
            doctor_ptr_number=consultation.doctor.ptr_number if consultation.doctor else None,
            doctor_workspace_config=(
                consultation.doctor.effective_workspace_config
                if consultation.doctor
                else resolve_workspace_config(None)
            ),
            patient_name=consultation.patient.full_name if consultation.patient else None,
            patient_number=consultation.patient.patient_number if consultation.patient else None,
            visit_number=consultation.visit.visit_number if consultation.visit else None,
            soap_note=SoapNoteRead.model_validate(soap) if soap else None,
            diagnoses=[DiagnosisRead.model_validate(d) for d in diagnoses],
            attachments=[attachment_to_read(a) for a in attachments],
            lock=lock,
        )

    # --- Open / resume ---

    async def open_consultation(
        self, visit_id: UUID, *, clinic_id: UUID, doctor_id: UUID, actor_id: UUID, current_user_id: UUID, acquire_lock: bool
    ) -> ConsultationDetail:
        visit = await self._require_visit(visit_id, clinic_id)

        consultation = await self.repo.get_latest_for_visit(visit_id, clinic_id)
        now = datetime.now(UTC)
        is_new = consultation is None
        if consultation is None:
            consultation = await self.repo.create_consultation(
                clinic_id=clinic_id, visit_id=visit_id, branch_id=visit.branch_id, doctor_id=doctor_id,
                patient_id=visit.patient_id, started_at=now, actor_id=actor_id,
            )
            await self.visit_repo.add_timeline_event(
                clinic_id=clinic_id, visit_id=visit_id, event_type=VisitTimelineEventType.CONSULTATION_OPENED,
                occurred_at=now, recorded_by=actor_id, note="Consultation opened",
            )
            await self.audit_service.log_event(
                clinic_id=clinic_id, user_id=actor_id, action="consultation.opened",
                entity_type="consultation", entity_id=str(consultation.id), metadata={"visit_id": str(visit_id)},
            )

        if acquire_lock:
            existing = await self.lock_repo.get_active_lock(visit_id, clinic_id)
            if existing is None:
                await self.lock_repo.create_lock(clinic_id=clinic_id, visit_id=visit_id, locked_by=actor_id, locked_at=now)
            elif existing.locked_by == actor_id:
                # heartbeat: refresh
                await self.lock_repo.release_lock(existing, released_at=now)
                await self.lock_repo.create_lock(clinic_id=clinic_id, visit_id=visit_id, locked_by=actor_id, locked_at=now)
            # else: held by someone else - leave as-is, caller only gets view access.

        await self.session.commit()
        return await self.get_detail(consultation.id, clinic_id=clinic_id, current_user_id=current_user_id)

    async def open_consultation_for_reception(
        self, visit_id: UUID, *, clinic_id: UUID, actor_id: UUID, current_user_id: UUID
    ) -> ConsultationDetail:
        """Phase 20 (items 4-5): lets a Receptionist/Nurse open (or resume)
        a visit's consultation to enter Subjective/Objective data, without
        the Doctor-linkage check `open_consultation`'s normal caller
        (`_require_visit_and_permissions` in `api/v1/consultations.py`)
        applies - a Receptionist/Nurse user has no `doctor_id` at all.
        Never acquires the edit lock (`acquire_lock=False`), same as a
        privileged view-only caller, since this path is never allowed to
        touch Assessment/Plan or complete/sign the consultation."""
        visit = await self._require_visit(visit_id, clinic_id)
        if visit.doctor_id is None:
            # BUG-024: `Consultation.doctor_id` is NOT NULL (see
            # models/consultation.py), so a consultation genuinely cannot be
            # opened for a visit with no doctor assigned yet - this is a
            # real, reachable state since `New Queue Ticket` allows
            # "Any / unassigned" for Doctor. Previously this 400 was correct
            # but its message got swallowed by the frontend's generic catch
            # (`ReceptionVitalsDialog`), showing "Could not open this
            # visit's consultation." with no indication of the real cause.
            # The frontend fix (surfacing `err.message`) now shows this
            # message verbatim, so make it actionable here.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This visit has no doctor assigned yet. Assign a doctor to the queue ticket before entering vitals.",
            )
        return await self.open_consultation(
            visit_id, clinic_id=clinic_id, doctor_id=visit.doctor_id, actor_id=actor_id,
            current_user_id=current_user_id, acquire_lock=False,
        )

    async def save_soap_subjective_objective(
        self, consultation_id: UUID, payload: dict, *, clinic_id: UUID, actor_id: UUID, current_user_id: UUID
    ) -> ConsultationDetail:
        """Phase 20 (items 4-5): merge-write ONLY the Subjective/Objective
        fields present in `payload` (caller passes `model_dump(exclude_unset=True)`
        so untouched fields are simply absent), preserving whatever
        Assessment/Plan (and any Subjective/Objective fields not submitted
        this call) already exist on the note - unlike `save_soap`, which
        overwrites the entire note from a full payload. This is what keeps a
        Receptionist/Nurse call from ever being able to wipe a Doctor's
        Assessment/Plan entries."""
        consultation = await self._require_consultation(consultation_id, clinic_id)
        if consultation.status == ConsultationStatus.SIGNED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot edit a signed consultation.")

        existing = await self.repo.get_soap(consultation_id, clinic_id)
        fields = {f: getattr(existing, f) if existing is not None else None for f in SOAP_FIELDS}
        for f in SUBJECTIVE_OBJECTIVE_FIELDS:
            if f in payload:
                fields[f] = payload[f]
        fields["bmi"] = _compute_bmi(fields.get("height_cm"), fields.get("weight_kg"))

        had_content_before = existing is not None and any(getattr(existing, f) is not None for f in SOAP_FIELDS)
        changed = existing is None or any(getattr(existing, f) != fields[f] for f in SOAP_FIELDS)

        note = await self.repo.upsert_soap(consultation_id=consultation_id, clinic_id=clinic_id, fields=fields)

        now = datetime.now(UTC)
        has_real_content = any(fields.get(f) is not None for f in SOAP_FIELDS)
        if consultation.status == ConsultationStatus.DRAFT and has_real_content:
            await self.repo.update_consultation(consultation, status=ConsultationStatus.IN_PROGRESS, updated_by=actor_id)

        if changed and (has_real_content or had_content_before):
            await self.visit_repo.add_timeline_event(
                clinic_id=clinic_id, visit_id=consultation.visit_id, event_type=VisitTimelineEventType.SOAP_SAVED,
                occurred_at=now, recorded_by=actor_id, note="Subjective/Objective entered",
            )
            await self.audit_service.log_event(
                clinic_id=clinic_id, user_id=actor_id,
                action="consultation.soap_subjective_objective_updated" if existing is not None else "consultation.soap_created",
                entity_type="soap_note", entity_id=str(note.id),
            )
        await self.session.commit()
        await sync_queue_service.enqueue(
            entity_type="soap_note", record_id=note.id,
            operation="update" if existing is not None else "create",
            payload=jsonable_encoder({"consultation_id": str(consultation_id), **fields}),
            clinic_id=clinic_id,
        )
        return await self.get_detail(consultation_id, clinic_id=clinic_id, current_user_id=current_user_id)

    async def get_consultation_for_visit(self, visit_id: UUID, *, clinic_id: UUID, current_user_id: UUID) -> ConsultationDetail | None:
        consultation = await self.repo.get_latest_for_visit(visit_id, clinic_id)
        if consultation is None:
            return None
        return await self.get_detail(consultation.id, clinic_id=clinic_id, current_user_id=current_user_id)

    async def get_detail(self, consultation_id: UUID, *, clinic_id: UUID, current_user_id: UUID) -> ConsultationDetail:
        consultation = await self._require_consultation(consultation_id, clinic_id)
        soap = await self.repo.get_soap(consultation_id, clinic_id)
        diagnoses = await self.repo.list_diagnoses(consultation_id, clinic_id)
        attachments = await self.repo.list_attachments(consultation_id, clinic_id)
        lock = await self._lock_info(consultation.visit_id, clinic_id, current_user_id)
        return self._to_detail(consultation, soap=soap, diagnoses=diagnoses, attachments=attachments, lock=lock)

    # --- SOAP ---

    async def save_soap(self, consultation_id: UUID, payload: dict, *, clinic_id: UUID, actor_id: UUID, current_user_id: UUID, can_edit: bool) -> ConsultationDetail:
        """Bug fix (RC1 UAT): this used to build `fields` from
        `payload.get(k)` over EVERY `SOAP_FIELDS` key with no merge against
        the existing row, so any Doctor save of Assessment/Plan that didn't
        also re-send every Subjective/Objective/vitals field (which the
        Assessment/Plan UI has no reason to resubmit - Reception already
        saved them) silently wiped the patient's chief complaint and vitals
        back to null. Now merge-writes like the sibling
        `save_soap_subjective_objective`: start from whatever already exists
        on the note, and only overwrite the specific fields present in
        `payload` (the caller passes `model_dump(exclude_unset=True)`)."""
        self._require_can_edit(can_edit)
        consultation = await self._require_consultation(consultation_id, clinic_id)
        if consultation.status == ConsultationStatus.SIGNED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot edit a signed consultation.")

        existing = await self.repo.get_soap(consultation_id, clinic_id)
        fields = {f: getattr(existing, f) if existing is not None else None for f in SOAP_FIELDS}
        for f in SOAP_FIELDS:
            if f in payload:
                fields[f] = payload[f]
        fields["bmi"] = _compute_bmi(fields.get("height_cm"), fields.get("weight_kg"))

        had_content_before = existing is not None and any(getattr(existing, f) is not None for f in SOAP_FIELDS)
        changed = existing is None or any(getattr(existing, f) != fields[f] for f in SOAP_FIELDS)

        note = await self.repo.upsert_soap(consultation_id=consultation_id, clinic_id=clinic_id, fields=fields)

        now = datetime.now(UTC)
        has_real_content = any(fields.get(f) is not None for f in SOAP_FIELDS)
        if consultation.status == ConsultationStatus.DRAFT and has_real_content:
            await self.repo.update_consultation(consultation, status=ConsultationStatus.IN_PROGRESS, updated_by=actor_id)

        # Only log timeline/audit when content actually changed (idempotent
        # autosave) - first meaningful save always counts as a change since
        # `existing is None` or the diff check above catches it.
        if changed and (has_real_content or had_content_before):
            await self.visit_repo.add_timeline_event(
                clinic_id=clinic_id, visit_id=consultation.visit_id, event_type=VisitTimelineEventType.SOAP_SAVED,
                occurred_at=now, recorded_by=actor_id, note="SOAP note saved",
            )
            await self.audit_service.log_event(
                clinic_id=clinic_id, user_id=actor_id,
                action="consultation.soap_updated" if existing is not None else "consultation.soap_created",
                entity_type="soap_note", entity_id=str(note.id),
            )
        await self.session.commit()
        # Post-RC1 Phase 2 Milestone 2: Cloud Backup - best-effort, never
        # affects this already-committed save (see sync_queue_service.py).
        await sync_queue_service.enqueue(
            entity_type="soap_note", record_id=note.id,
            operation="update" if existing is not None else "create",
            payload=jsonable_encoder({"consultation_id": str(consultation_id), **fields}),
            clinic_id=clinic_id,
        )
        return await self.get_detail(consultation_id, clinic_id=clinic_id, current_user_id=current_user_id)

    # --- Diagnoses ---

    async def add_diagnosis(self, consultation_id: UUID, payload: dict, *, clinic_id: UUID, actor_id: UUID, current_user_id: UUID, can_edit: bool) -> ConsultationDetail:
        self._require_can_edit(can_edit)
        consultation = await self._require_consultation(consultation_id, clinic_id)
        diagnosis = await self.repo.add_diagnosis(consultation_id=consultation_id, clinic_id=clinic_id, actor_id=actor_id, **payload)
        now = datetime.now(UTC)
        await self.visit_repo.add_timeline_event(
            clinic_id=clinic_id, visit_id=consultation.visit_id, event_type=VisitTimelineEventType.DIAGNOSIS_ADDED,
            occurred_at=now, recorded_by=actor_id,
            note=f"Diagnosis added ({diagnosis.diagnosis_type.value})",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="consultation.diagnosis_added",
            entity_type="diagnosis", entity_id=str(diagnosis.id),
        )
        await self.session.commit()
        return await self.get_detail(consultation_id, clinic_id=clinic_id, current_user_id=current_user_id)

    async def update_diagnosis(self, consultation_id: UUID, diagnosis_id: UUID, payload: dict, *, clinic_id: UUID, actor_id: UUID, current_user_id: UUID, can_edit: bool) -> ConsultationDetail:
        self._require_can_edit(can_edit)
        await self._require_consultation(consultation_id, clinic_id)
        diagnosis = await self.repo.get_diagnosis(diagnosis_id, consultation_id, clinic_id)
        if diagnosis is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis not found")
        updates = {k: v for k, v in payload.items() if v is not None}
        await self.repo.update_diagnosis(diagnosis, **updates)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="consultation.diagnosis_updated",
            entity_type="diagnosis", entity_id=str(diagnosis.id),
        )
        await self.session.commit()
        return await self.get_detail(consultation_id, clinic_id=clinic_id, current_user_id=current_user_id)

    async def list_diagnoses(self, consultation_id: UUID, *, clinic_id: UUID) -> list[DiagnosisRead]:
        await self._require_consultation(consultation_id, clinic_id)
        rows = await self.repo.list_diagnoses(consultation_id, clinic_id)
        return [DiagnosisRead.model_validate(d) for d in rows]

    # --- Complete / sign ---

    def _transition(self, consultation: Consultation, new_status: ConsultationStatus) -> None:
        allowed = CONSULTATION_STATUS_TRANSITIONS.get(consultation.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot transition consultation from {consultation.status.value} to {new_status.value}.",
            )

    async def _enforce_required_sections(
        self, consultation: Consultation, *, clinic_id: UUID
    ) -> None:
        """Data-driven completion gate: reads THIS consultation's doctor's
        resolved workspace config (never a hard-coded doctor id/name
        anywhere) and, for every section marked required (which
        `resolve_workspace_config` guarantees is also visible - see its
        docstring), checks that section actually has data before allowing
        the consultation to complete. Hidden or not-required sections are
        never checked, matching "required flags are enforced only for
        visible sections" exactly via the same resolution the frontend
        renders from."""
        config = (
            consultation.doctor.effective_workspace_config
            if consultation.doctor
            else resolve_workspace_config(None)
        )
        sections = config["sections"]
        missing: list[str] = []

        if sections["vitals"]["required"]:
            soap = consultation.soap_note
            vital_fields = (
                "blood_pressure", "pulse_rate", "respiratory_rate",
                "temperature", "height_cm", "weight_kg", "oxygen_saturation",
            )
            has_vitals = bool(soap) and any(
                getattr(soap, field) not in (None, "") for field in vital_fields
            )
            if not has_vitals:
                missing.append("Vitals")

        if sections["diagnosis"]["required"]:
            diagnoses = await self.repo.list_diagnoses(consultation.id, clinic_id)
            if not diagnoses:
                missing.append("Diagnosis")

        if sections["prescription"]["required"] or sections["lab_requests"]["required"]:
            from app.repositories.clinical_orders_repository import ClinicalOrdersRepository

            orders_repo = ClinicalOrdersRepository(self.session)
            if sections["prescription"]["required"]:
                prescriptions = await orders_repo.list_prescriptions_for_consultation(
                    consultation.id, clinic_id
                )
                if not prescriptions:
                    missing.append("Prescription")
            if sections["lab_requests"]["required"]:
                orders = await orders_repo.list_orders_for_consultation(consultation.id, clinic_id)
                if not any(o.order_category == OrderCategory.LABORATORY for o in orders):
                    missing.append("Lab Requests")

        if sections["certificate"]["required"]:
            from app.repositories.medical_certificate_repository import MedicalCertificateRepository

            cert_repo = MedicalCertificateRepository(self.session)
            certs = await cert_repo.list_for_consultation(consultation.id, clinic_id)
            if not certs:
                missing.append("Medical Certificate")

        if sections["attachments"]["required"]:
            attachments = await self.repo.list_attachments(consultation.id, clinic_id)
            if not attachments:
                missing.append("Attachments")

        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Cannot complete consultation - required section(s) missing: "
                    f"{', '.join(missing)}."
                ),
            )

    async def complete_consultation(
        self, consultation_id: UUID, *, clinic_id: UUID, actor_id: UUID, current_user_id: UUID, can_edit: bool,
        consultation_fee: Decimal | None = None,
    ) -> ConsultationDetail:
        # Client Acceptance Revisions - Round 3 (item 12): the client asked to
        # remove the separate "Sign Consultation" step/button entirely so
        # "Mark as Complete" is the only completion action. `signed_at` and
        # ConsultationStatus.SIGNED are still read elsewhere (printable
        # documents, audit trail, `canEdit` gating), so rather than deleting
        # the concept, signing now happens automatically as part of
        # completion: the consultation goes straight to SIGNED with both
        # `completed_at` and `signed_at` stamped to the same timestamp.
        # `sign_consultation()` below is kept for backward compatibility
        # (nothing in the frontend calls it anymore) but is now a no-op path
        # in practice since complete_consultation() already reaches SIGNED.
        self._require_can_edit(can_edit)
        consultation = await self._require_consultation(consultation_id, clinic_id)
        already_closed = consultation.status in (ConsultationStatus.COMPLETED, ConsultationStatus.SIGNED)
        if not already_closed:
            await self._enforce_required_sections(consultation, clinic_id=clinic_id)
            self._transition(consultation, ConsultationStatus.COMPLETED)
        now = datetime.now(UTC)
        if not already_closed:
            await self.repo.update_consultation(consultation, status=ConsultationStatus.COMPLETED, completed_at=now, updated_by=actor_id)
            await self.visit_repo.add_timeline_event(
                clinic_id=clinic_id, visit_id=consultation.visit_id, event_type=VisitTimelineEventType.CONSULTATION_COMPLETED,
                occurred_at=now, recorded_by=actor_id, note="Consultation completed",
            )
            await self.audit_service.log_event(
                clinic_id=clinic_id, user_id=actor_id, action="consultation.completed",
                entity_type="consultation", entity_id=str(consultation.id),
            )
            # Auto-sign: fold the former separate "Sign Consultation" step
            # into completion so there is only one user-facing action.
            self._transition(consultation, ConsultationStatus.SIGNED)
            await self.repo.update_consultation(consultation, status=ConsultationStatus.SIGNED, signed_at=now, updated_by=actor_id)
            await self.visit_repo.add_timeline_event(
                clinic_id=clinic_id, visit_id=consultation.visit_id, event_type=VisitTimelineEventType.CONSULTATION_SIGNED,
                occurred_at=now, recorded_by=actor_id, note="Consultation signed (auto, on completion)",
            )
            await self.audit_service.log_event(
                clinic_id=clinic_id, user_id=actor_id, action="consultation.signed",
                entity_type="consultation", entity_id=str(consultation.id), metadata={"auto": True},
            )

        # Consultation -> Visit status sync (Phase 7 lesson): reflect the
        # completed clinical encounter onto Visit.status via the single
        # source-of-truth VisitService.change_status(). If the Visit is
        # already Completed (e.g. doctor used the Doctor Workspace button
        # first), this is a tolerated no-op, not an error.
        visit = await self.visit_repo.get_by_id_and_clinic(consultation.visit_id, clinic_id)
        if visit is not None and visit.status != VisitStatus.COMPLETED:
            from app.models.visit import VISIT_STATUS_TRANSITIONS
            if VisitStatus.COMPLETED in VISIT_STATUS_TRANSITIONS.get(visit.status, set()):
                await self.visit_service.change_status(
                    consultation.visit_id, clinic_id=clinic_id, actor_id=actor_id,
                    new_status=VisitStatus.COMPLETED, note="Consultation completed",
                )
                await self._sync_queue_status(
                    visit, clinic_id=clinic_id, actor_id=actor_id, note="Consultation completed"
                )
            # else: Visit is in a state (e.g. already Cancelled) where
            # Completed isn't legal - the Consultation stays the clinical
            # record of what happened, but we don't force an illegal Visit
            # transition; this mirrors DoctorWorkspaceService._sync_queue_status's
            # "don't force an illegal transition" tolerance.
        elif already_closed and visit is not None:
            # Idempotent re-complete call (e.g. autosave race, double-click):
            # Visit is already Completed, but the Queue might still be stuck
            # if this is the *first* time the sync actually runs for this
            # visit (e.g. an older consultation completed before this fix
            # shipped) - re-check and sync defensively.
            await self._sync_queue_status(
                visit, clinic_id=clinic_id, actor_id=actor_id, note="Consultation completed"
            )

        # Consultation -> Invoice sync (Phase 9): per the spec's workflow
        # diagram ("Doctor marks Consultation Complete -> Billing Draft
        # automatically created"), completing a consultation auto-creates a
        # Draft invoice for the visit. Idempotent by design (see
        # InvoiceService.create_draft_invoice_for_consultation) - safe to
        # call again on a repeat/idempotent complete() call.
        from app.services.invoice_service import InvoiceService

        invoice_service = InvoiceService(self.session)
        await invoice_service.create_draft_invoice_for_consultation(
            clinic_id=clinic_id, visit_id=consultation.visit_id, actor_id=actor_id, fee_override=consultation_fee,
        )

        await self.session.commit()
        return await self.get_detail(consultation_id, clinic_id=clinic_id, current_user_id=current_user_id)

    async def sign_consultation(self, consultation_id: UUID, *, clinic_id: UUID, actor_id: UUID, current_user_id: UUID, can_edit: bool) -> ConsultationDetail:
        self._require_can_edit(can_edit)
        consultation = await self._require_consultation(consultation_id, clinic_id)
        self._transition(consultation, ConsultationStatus.SIGNED)
        now = datetime.now(UTC)
        await self.repo.update_consultation(consultation, status=ConsultationStatus.SIGNED, signed_at=now, updated_by=actor_id)
        await self.visit_repo.add_timeline_event(
            clinic_id=clinic_id, visit_id=consultation.visit_id, event_type=VisitTimelineEventType.CONSULTATION_SIGNED,
            occurred_at=now, recorded_by=actor_id, note="Consultation signed",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="consultation.signed",
            entity_type="consultation", entity_id=str(consultation.id),
        )
        # Release the lock as a side effect of finalizing the document -
        # mirrors DoctorWorkspaceService.complete_consultation releasing the
        # visit lock once the encounter is fully closed out.
        await self.lock_repo.release_all_locks_for_visit(consultation.visit_id, clinic_id, released_at=now)
        await self.session.commit()
        return await self.get_detail(consultation_id, clinic_id=clinic_id, current_user_id=current_user_id)

    # --- Attachments ---
    #
    # Feature 2: real file storage (local disk, see
    # `api/v1/consultations.py`'s module-level `CONSULTATION_ATTACHMENTS_
    # UPLOAD_ROOT` and its docstring for why - superseded the old
    # `request_attachment_upload` presigned-URL-stub method below, which
    # never actually stored any file bytes anywhere).

    async def add_attachment_record(
        self, consultation_id: UUID, *, clinic_id: UUID, actor_id: UUID, attachment_type,
        file_name: str, stored_filename: str, file_size_bytes: int,
    ) -> ConsultationAttachment:
        """Inserts the DB row for a file the caller (the API layer) has
        already validated and written to disk. `stored_filename` is the
        on-disk filename only (not a URL) - resolving it back to a real
        path/URL is the API layer's job (`_attachment_to_read`), since this
        service has no notion of the authenticated file-serving route."""
        await self._require_consultation(consultation_id, clinic_id)
        attachment = await self.repo.add_attachment(
            consultation_id=consultation_id, clinic_id=clinic_id, uploaded_by=actor_id,
            attachment_type=attachment_type, file_name=file_name, file_url=stored_filename,
            file_size_bytes=file_size_bytes,
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="consultation.attachment_uploaded",
            entity_type="consultation_attachment", entity_id=str(attachment.id),
        )
        await self.session.commit()
        return attachment

    async def list_attachments(self, consultation_id: UUID, *, clinic_id: UUID) -> list[ConsultationAttachment]:
        await self._require_consultation(consultation_id, clinic_id)
        return await self.repo.list_attachments(consultation_id, clinic_id)

    async def get_attachment(self, consultation_id: UUID, attachment_id: UUID, *, clinic_id: UUID) -> ConsultationAttachment:
        await self._require_consultation(consultation_id, clinic_id)
        attachment = await self.repo.get_attachment(attachment_id, consultation_id, clinic_id)
        if attachment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
        return attachment

    # --- Timeline (reuses the Visit timeline) ---

    async def get_timeline(self, consultation_id: UUID, *, clinic_id: UUID):
        consultation = await self._require_consultation(consultation_id, clinic_id)
        return consultation.visit_id, await self.visit_service.get_timeline(consultation.visit_id, clinic_id=clinic_id)
