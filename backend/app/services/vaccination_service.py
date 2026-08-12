"""Vaccination Administration service (Post-RC1).

Mirrors `services/laboratory_service.py`'s "attach a workflow record to a
Phase 9 Order" pattern. The key difference from Laboratory: administering a
vaccination is a single-step action (record what was given, by whom, and
mark it Administered) rather than a multi-stage Collected/Processing/
Completed/Released pipeline, and any Nurse/Receptionist/Doctor/Owner/
Administrator may perform it - not just the ordering doctor (enforced by
`VACCINATION_ADMINISTER_ROLES` at the API layer, not here).
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderStatus
from app.models.vaccination_administration import VaccinationAdministration, VaccinationStatus
from app.repositories.clinical_orders_repository import ClinicalOrdersRepository
from app.repositories.vaccination_repository import VaccinationRepository
from app.schemas.vaccination import VaccinationAdministerRequest, VaccinationAdministrationRead
from app.services import sync_queue_service
from app.services.audit_service import AuditService


def _to_read(record: VaccinationAdministration) -> VaccinationAdministrationRead:
    return VaccinationAdministrationRead.model_validate(record)


class VaccinationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = VaccinationRepository(session)
        self.orders_repo = ClinicalOrdersRepository(session)
        self.audit_service = AuditService(session)

    # --- Creation (attaches to an existing Phase 9 Vaccination-category Order) ---

    async def create_from_order(self, order: Order, *, clinic_id: UUID, actor_id: UUID | None) -> VaccinationAdministration:
        """Idempotent: if a vaccination_administrations row already exists
        for this order, returns the existing one - mirrors
        `LaboratoryService.create_from_order`'s idempotency guarantee."""
        existing = await self.repo.get_by_order_id(order.id, clinic_id)
        if existing is not None:
            return existing

        vaccine_name = order.items[0].item_name if order.items else "Vaccination"
        record = await self.repo.create(
            clinic_id=clinic_id, order_id=order.id, branch_id=order.branch_id, visit_id=order.visit_id,
            patient_id=order.patient_id, doctor_id=order.doctor_id, vaccine_name=vaccine_name,
            status=VaccinationStatus.REQUESTED,
        )
        await self.session.commit()
        refreshed = await self.repo.get_by_id(record.id, clinic_id)
        # Post-RC1 Phase 2 Milestone 2: Cloud Backup - best-effort, never
        # affects this already-committed create (see sync_queue_service.py).
        await sync_queue_service.enqueue(
            entity_type="vaccination_administration", record_id=refreshed.id, operation="create",
            payload=_to_read(refreshed).model_dump(mode="json"), clinic_id=clinic_id,
        )
        return refreshed

    # --- Reads ---

    async def list_for_clinic(self, clinic_id: UUID, *, status_filter: VaccinationStatus | None = None) -> list[VaccinationAdministrationRead]:
        rows = await self.repo.list_for_clinic(clinic_id, status=status_filter)
        return [_to_read(r) for r in rows]

    async def list_for_patient(self, patient_id: UUID, clinic_id: UUID) -> list[VaccinationAdministrationRead]:
        rows = await self.repo.list_for_patient(patient_id, clinic_id)
        return [_to_read(r) for r in rows]

    # --- Administer ---

    async def administer(
        self, vaccination_id: UUID, payload: VaccinationAdministerRequest, *, clinic_id: UUID, actor_id: UUID
    ) -> VaccinationAdministrationRead:
        record = await self.repo.get_by_id(vaccination_id, clinic_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vaccination record not found")
        if record.status != VaccinationStatus.REQUESTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot administer a vaccination in status {record.status.value}.",
            )

        now = datetime.now(UTC)
        await self.repo.update(
            record,
            vaccine_name=payload.vaccine_name or record.vaccine_name,
            dose=payload.dose, lot_number=payload.lot_number, site=payload.site, route=payload.route,
            notes=payload.notes, administered_at=payload.administered_at or now, administered_by=actor_id,
            status=VaccinationStatus.ADMINISTERED,
        )

        # Mirror the underlying Order's own status forward too, so it reads
        # correctly everywhere an Order is listed (Doctor Workspace's
        # Clinical Orders tab, visit timeline, etc.) - same "keep the parent
        # Order in sync" requirement `LaboratoryService` follows.
        order = await self.orders_repo.get_order(record.order_id, clinic_id)
        if order is not None and order.status != OrderStatus.COMPLETED:
            await self.orders_repo.update_order(order, status=OrderStatus.COMPLETED, updated_by=actor_id)

        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="vaccination.administered",
            entity_type="vaccination_administration", entity_id=str(record.id),
            metadata={"vaccine_name": record.vaccine_name},
        )
        await self.session.commit()
        refreshed = await self.repo.get_by_id(record.id, clinic_id)
        read = _to_read(refreshed)
        await sync_queue_service.enqueue(
            entity_type="vaccination_administration", record_id=refreshed.id, operation="update",
            payload=read.model_dump(mode="json"), clinic_id=clinic_id,
        )
        return read

    async def cancel(self, vaccination_id: UUID, *, clinic_id: UUID, actor_id: UUID) -> VaccinationAdministrationRead:
        record = await self.repo.get_by_id(vaccination_id, clinic_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vaccination record not found")
        if record.status != VaccinationStatus.REQUESTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel a vaccination in status {record.status.value}.",
            )
        await self.repo.update(record, status=VaccinationStatus.CANCELLED)
        order = await self.orders_repo.get_order(record.order_id, clinic_id)
        if order is not None and order.status != OrderStatus.CANCELLED:
            await self.orders_repo.update_order(order, status=OrderStatus.CANCELLED, updated_by=actor_id)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="vaccination.cancelled",
            entity_type="vaccination_administration", entity_id=str(record.id),
        )
        await self.session.commit()
        return _to_read(await self.repo.get_by_id(record.id, clinic_id))
