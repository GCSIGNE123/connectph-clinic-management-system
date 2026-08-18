"""Clinical Orders & Prescriptions service (Phase 9).

Layers on top of Consultation the same way `ConsultationService` layers on
top of Visit: creating an Order/Procedure/Referral/Prescription during an
in-progress consultation does NOT change `Consultation.status` or
`Visit.status` itself (per the spec's SOAP -> Diagnosis -> Clinical Orders
-> Prescription -> Complete Consultation workflow, orders/prescriptions are
just *recorded during* an in-progress consultation) - but every creation
IS written to the same `visit_timeline_events` table Phase 7/8 use (via
`VisitRepository.add_timeline_event`) and to `AuditService`, exactly
mirroring `ConsultationService.add_diagnosis()`'s pattern, so it shows up
correctly in the Visit's timeline/tabs and read-only history everywhere
Diagnosis already does. This directly applies the Phase 7/8 lesson about
not forgetting to reflect a new child entity onto the parent's visible
state.
"""

from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderCategory
from app.models.visit import VisitTimelineEventType
from app.repositories.clinical_orders_repository import ClinicalOrdersRepository
from app.repositories.consultation_repository import ConsultationRepository
from app.repositories.visit_repository import VisitRepository
from app.schemas.clinical_orders import (
    OrderCreate,
    OrderRead,
    PrescriptionCreate,
    PrescriptionCreateResponse,
    PrescriptionRead,
    ProcedureCreate,
    ProcedureRead,
    ReferralCreate,
    ReferralRead,
)
from app.services.audit_service import AuditService
from app.services.clinical_number_generator import OrderNumberGenerator, PrescriptionNumberGenerator
from app.services import sync_queue_service


class ClinicalOrdersService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ClinicalOrdersRepository(session)
        self.consultation_repo = ConsultationRepository(session)
        self.visit_repo = VisitRepository(session)
        self.audit_service = AuditService(session)

    async def _require_consultation(self, consultation_id: UUID, clinic_id: UUID):
        consultation = await self.consultation_repo.get_by_id(consultation_id, clinic_id)
        if consultation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")
        return consultation

    def _require_can_edit(self, can_edit: bool) -> None:
        if not can_edit:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have edit access to this consultation.")

    async def _snapshot_doctor_signature(self, doctor_id: UUID | None, *, clinic_id: UUID) -> str | None:
        """Doctor E-Signature: copies the doctor's CURRENT `signature_url`
        at issuance time into the document row - a deliberate, one-time
        snapshot, not a live join (see migration 0036's docstring). Neither
        Referral nor Prescription has a separate "finalize" step - creation
        IS issuance for both, so this is called directly from
        `create_referral`/`create_prescription`. Returns None gracefully
        (no fabricated signature) if the doctor has none configured, or if
        the visit has no assigned doctor at all."""
        if doctor_id is None:
            return None
        from app.models.doctor import Doctor

        doctor = await self.session.get(Doctor, doctor_id)
        if doctor is None or doctor.clinic_id != clinic_id:
            return None
        return doctor.signature_url

    # --- Allergy conflict checking (architecture-only, Phase 9) ---

    def check_allergy_conflicts(self, patient_id: UUID, items: list[dict]) -> list[str]:
        """Placeholder for a future allergy-vs-medicine conflict check.

        There is no drug/allergy database in this phase - a real
        implementation needs a formulary with active-ingredient mappings
        and a patient allergy list to cross-reference. Always returns an
        empty list today; kept as a named hook so a future phase can wire
        real logic in without touching call sites in `create_prescription`.
        """
        return []

    # --- Prescription validation (warnings, non-blocking) ---

    def _validate_prescription_items(self, items: list[dict]) -> list[str]:
        warnings: list[str] = []
        seen_medicines: dict[str, int] = {}
        for item in items:
            name = (item.get("medicine") or "").strip().lower()
            if name:
                seen_medicines[name] = seen_medicines.get(name, 0) + 1
            if not item.get("dosage"):
                warnings.append(f"Missing dosage for '{item.get('medicine', '')}'.")
            if not item.get("duration"):
                warnings.append(f"Missing duration for '{item.get('medicine', '')}'.")
        for name, count in seen_medicines.items():
            if count > 1:
                warnings.append(f"Duplicate medicine entry: '{name}' appears {count} times.")
        return warnings

    # --- Orders ---

    async def create_order(
        self, consultation_id: UUID, payload: OrderCreate, *, clinic_id: UUID, actor_id: UUID, can_edit: bool
    ) -> OrderRead:
        self._require_can_edit(can_edit)
        consultation = await self._require_consultation(consultation_id, clinic_id)
        generator = OrderNumberGenerator(self.session)
        order_number = await generator.next_number(clinic_id)

        items = [item.model_dump() for item in payload.items]
        order = await self.repo.create_order(
            clinic_id=clinic_id, consultation_id=consultation_id, visit_id=consultation.visit_id,
            branch_id=consultation.branch_id, patient_id=consultation.patient_id, doctor_id=consultation.doctor_id,
            order_number=order_number, order_category=payload.order_category, priority=payload.priority,
            scheduled_date=payload.scheduled_date, clinical_notes=payload.clinical_notes,
            created_by=actor_id, updated_by=actor_id, items=items,
        )

        now = datetime.now(UTC)
        await self.visit_repo.add_timeline_event(
            clinic_id=clinic_id, visit_id=consultation.visit_id, event_type=VisitTimelineEventType.ORDER_CREATED,
            occurred_at=now, recorded_by=actor_id,
            note=f"Order created ({payload.order_category.value}) - {order_number}",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="clinical_orders.order_created",
            entity_type="order", entity_id=str(order.id), metadata={"order_number": order_number},
        )

        # Phase 10 / Post-RC1: a Laboratory- or Vaccination-category order
        # automatically gets its own category-specific workflow record
        # attached, so it shows up on that module's dashboard immediately
        # with no extra step for the doctor. See
        # `services/laboratory_service.py::create_from_order` for the full
        # design rationale (separate table vs. extending `orders` in
        # place).
        #
        # Created here, in the SAME uncommitted transaction as the Order
        # above, and committed together in the single `session.commit()`
        # below. Previously each of these ran its OWN follow-up
        # `session.commit()` after the Order's own (earlier) commit had
        # already happened - so any failure in the follow-up step (e.g.
        # the daily order-number counter's first-of-day race, now fixed in
        # `clinical_number_generator.py`, or any other error) could leave
        # a durably committed `Order` with no matching
        # `LaboratoryOrder`/`VaccinationAdministration` row: the doctor saw
        # the Order after a refresh, but the Laboratory Technician's
        # worklist (or the Vaccination dashboard) correctly showed
        # nothing, because that row genuinely never existed. A single
        # commit for the whole operation means any failure anywhere above
        # rolls back everything - the Order included - instead of leaving
        # this split state.
        lab_order = None
        vaccination_record = None
        if payload.order_category == OrderCategory.LABORATORY:
            from app.services.laboratory_service import LaboratoryService

            lab_order = await LaboratoryService(self.session).create_from_order(order, clinic_id=clinic_id, actor_id=actor_id)

        if payload.order_category == OrderCategory.VACCINATION:
            from app.services.vaccination_service import VaccinationService

            vaccination_record = await VaccinationService(self.session).create_from_order(order, clinic_id=clinic_id, actor_id=actor_id)

        await self.session.commit()

        # Post-RC1 Phase 2 Milestone 2: Cloud Backup - best-effort, never
        # affects this already-committed create (see sync_queue_service.py).
        # Enqueued only AFTER the commit above has actually succeeded, and
        # via `enqueue_lazy` so a payload-serialization failure can't turn
        # this already-successful create into a 500 either (see
        # `sync_queue_service.enqueue_lazy`'s docstring).
        if lab_order is not None:
            from app.services.laboratory_service import build_sync_payload as build_lab_sync_payload

            await sync_queue_service.enqueue_lazy(
                entity_type="laboratory_order", record_id=lab_order.id, operation="create",
                clinic_id=clinic_id, build_payload=lambda: build_lab_sync_payload(lab_order),
            )
        if vaccination_record is not None:
            from app.services.vaccination_service import build_sync_payload as build_vaccination_sync_payload

            await sync_queue_service.enqueue_lazy(
                entity_type="vaccination_administration", record_id=vaccination_record.id, operation="create",
                clinic_id=clinic_id, build_payload=lambda: build_vaccination_sync_payload(vaccination_record),
            )

        return OrderRead.model_validate(order)

    async def list_orders(self, consultation_id: UUID, *, clinic_id: UUID) -> list[OrderRead]:
        await self._require_consultation(consultation_id, clinic_id)
        rows = await self.repo.list_orders_for_consultation(consultation_id, clinic_id)
        return [OrderRead.model_validate(o) for o in rows]

    async def list_orders_for_visit(self, visit_id: UUID, *, clinic_id: UUID, category: OrderCategory | None = None) -> list[OrderRead]:
        rows = await self.repo.list_orders_for_visit(visit_id, clinic_id, category=category)
        return [OrderRead.model_validate(o) for o in rows]

    async def update_order_status(self, order_id: UUID, new_status, *, clinic_id: UUID, actor_id: UUID, can_edit: bool) -> OrderRead:
        self._require_can_edit(can_edit)
        order = await self.repo.get_order(order_id, clinic_id)
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
        from app.models.order import ORDER_STATUS_TRANSITIONS

        if new_status not in ORDER_STATUS_TRANSITIONS.get(order.status, set()) and new_status != order.status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot transition order from {order.status.value} to {new_status.value}.",
            )
        await self.repo.update_order(order, status=new_status, updated_by=actor_id)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="clinical_orders.order_status_updated",
            entity_type="order", entity_id=str(order.id), metadata={"status": new_status.value},
        )
        await self.session.commit()
        return OrderRead.model_validate(order)

    # --- Procedures ---

    async def create_procedure(
        self, consultation_id: UUID, payload: ProcedureCreate, *, clinic_id: UUID, actor_id: UUID, can_edit: bool
    ) -> ProcedureRead:
        self._require_can_edit(can_edit)
        consultation = await self._require_consultation(consultation_id, clinic_id)
        procedure = await self.repo.create_procedure(
            clinic_id=clinic_id, consultation_id=consultation_id, visit_id=consultation.visit_id,
            branch_id=consultation.branch_id, patient_id=consultation.patient_id, doctor_id=consultation.doctor_id,
            procedure_name=payload.procedure_name, procedure_date=payload.procedure_date, notes=payload.notes,
            created_by=actor_id, updated_by=actor_id,
        )
        now = datetime.now(UTC)
        await self.visit_repo.add_timeline_event(
            clinic_id=clinic_id, visit_id=consultation.visit_id, event_type=VisitTimelineEventType.PROCEDURE_CREATED,
            occurred_at=now, recorded_by=actor_id, note=f"Procedure created - {payload.procedure_name}",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="clinical_orders.procedure_created",
            entity_type="procedure", entity_id=str(procedure.id),
        )
        await self.session.commit()
        return ProcedureRead.model_validate(procedure)

    async def list_procedures(self, consultation_id: UUID, *, clinic_id: UUID) -> list[ProcedureRead]:
        await self._require_consultation(consultation_id, clinic_id)
        rows = await self.repo.list_procedures_for_consultation(consultation_id, clinic_id)
        return [ProcedureRead.model_validate(p) for p in rows]

    async def list_procedures_for_visit(self, visit_id: UUID, *, clinic_id: UUID) -> list[ProcedureRead]:
        rows = await self.repo.list_procedures_for_visit(visit_id, clinic_id)
        return [ProcedureRead.model_validate(p) for p in rows]

    # --- Referrals ---

    async def create_referral(
        self, consultation_id: UUID, payload: ReferralCreate, *, clinic_id: UUID, actor_id: UUID, can_edit: bool
    ) -> ReferralRead:
        self._require_can_edit(can_edit)
        consultation = await self._require_consultation(consultation_id, clinic_id)
        signature_snapshot = await self._snapshot_doctor_signature(consultation.doctor_id, clinic_id=clinic_id)
        referral = await self.repo.create_referral(
            clinic_id=clinic_id, consultation_id=consultation_id, visit_id=consultation.visit_id,
            branch_id=consultation.branch_id, patient_id=consultation.patient_id, doctor_id=consultation.doctor_id,
            referred_to=payload.referred_to, reason=payload.reason, notes=payload.notes,
            doctor_signature_snapshot_url=signature_snapshot,
            created_by=actor_id, updated_by=actor_id,
        )
        now = datetime.now(UTC)
        await self.visit_repo.add_timeline_event(
            clinic_id=clinic_id, visit_id=consultation.visit_id, event_type=VisitTimelineEventType.REFERRAL_CREATED,
            occurred_at=now, recorded_by=actor_id, note=f"Referral created - {payload.referred_to}",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="clinical_orders.referral_created",
            entity_type="referral", entity_id=str(referral.id),
        )
        await self.session.commit()
        return ReferralRead.model_validate(referral)

    async def list_referrals(self, consultation_id: UUID, *, clinic_id: UUID) -> list[ReferralRead]:
        await self._require_consultation(consultation_id, clinic_id)
        rows = await self.repo.list_referrals_for_consultation(consultation_id, clinic_id)
        return [ReferralRead.model_validate(r) for r in rows]

    async def get_referral(self, referral_id: UUID, *, clinic_id: UUID):
        referral = await self.repo.get_referral(referral_id, clinic_id)
        if referral is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referral not found")
        return referral

    async def list_referrals_for_visit(self, visit_id: UUID, *, clinic_id: UUID) -> list[ReferralRead]:
        rows = await self.repo.list_referrals_for_visit(visit_id, clinic_id)
        return [ReferralRead.model_validate(r) for r in rows]

    # --- Prescriptions ---

    async def create_prescription(
        self, consultation_id: UUID, payload: PrescriptionCreate, *, clinic_id: UUID, actor_id: UUID, can_edit: bool
    ) -> PrescriptionCreateResponse:
        self._require_can_edit(can_edit)
        consultation = await self._require_consultation(consultation_id, clinic_id)

        items = [item.model_dump() for item in payload.items]
        warnings = self._validate_prescription_items(items)
        warnings.extend(self.check_allergy_conflicts(consultation.patient_id, items))

        generator = PrescriptionNumberGenerator(self.session)
        prescription_number = await generator.next_number(clinic_id)
        signature_snapshot = await self._snapshot_doctor_signature(consultation.doctor_id, clinic_id=clinic_id)

        prescription = await self.repo.create_prescription(
            clinic_id=clinic_id, consultation_id=consultation_id, visit_id=consultation.visit_id,
            branch_id=consultation.branch_id, patient_id=consultation.patient_id, doctor_id=consultation.doctor_id,
            prescription_number=prescription_number, status=payload.status,
            doctor_signature_snapshot_url=signature_snapshot,
            created_by=actor_id, updated_by=actor_id, items=items,
        )

        now = datetime.now(UTC)
        await self.visit_repo.add_timeline_event(
            clinic_id=clinic_id, visit_id=consultation.visit_id, event_type=VisitTimelineEventType.PRESCRIPTION_CREATED,
            occurred_at=now, recorded_by=actor_id, note=f"Prescription created - {prescription_number}",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="clinical_orders.prescription_created",
            entity_type="prescription", entity_id=str(prescription.id),
            metadata={"prescription_number": prescription_number, "warnings": warnings},
        )
        await self.session.commit()
        read = PrescriptionRead.model_validate(prescription)
        # Post-RC1 Phase 2 Milestone 2: Cloud Backup - best-effort, never
        # affects this already-committed create (see sync_queue_service.py).
        await sync_queue_service.enqueue_lazy(
            entity_type="prescription", record_id=prescription.id, operation="create",
            clinic_id=clinic_id, build_payload=lambda: read.model_dump(mode="json"),
        )
        return PrescriptionCreateResponse(prescription=read, warnings=warnings)

    async def get_prescription(self, prescription_id: UUID, *, clinic_id: UUID):
        prescription = await self.repo.get_prescription(prescription_id, clinic_id)
        if prescription is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prescription not found")
        return prescription

    async def list_prescriptions(self, consultation_id: UUID, *, clinic_id: UUID) -> list[PrescriptionRead]:
        await self._require_consultation(consultation_id, clinic_id)
        rows = await self.repo.list_prescriptions_for_consultation(consultation_id, clinic_id)
        return [PrescriptionRead.model_validate(p) for p in rows]

    async def list_prescriptions_for_visit(self, visit_id: UUID, *, clinic_id: UUID) -> list[PrescriptionRead]:
        rows = await self.repo.list_prescriptions_for_visit(visit_id, clinic_id)
        return [PrescriptionRead.model_validate(p) for p in rows]

    async def list_prescriptions_for_patient(self, patient_id: UUID, *, clinic_id: UUID) -> list[PrescriptionRead]:
        rows = await self.repo.list_prescriptions_for_patient(patient_id, clinic_id)
        return [PrescriptionRead.model_validate(p) for p in rows]
