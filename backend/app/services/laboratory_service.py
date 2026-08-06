"""Laboratory Management service (Phase 10).

Workflow: Requested -> Collected -> Processing -> Completed -> Released (or
-> Cancelled from any non-terminal state). Every transition writes a
`visit_timeline_events` row and an `audit_logs` entry (see
`LABORATORY_ORDER_STATUS_TRANSITIONS` in `models/laboratory_order.py`).

Billing integration (idempotent): when a laboratory order transitions to
Completed and has a priced template, an invoice line item
(`InvoiceItemType.LABORATORY`) is added-or-updated on the visit's invoice
(auto-created via the same `InvoiceService.create_draft_invoice_for_consultation`
path Consultation-completion already uses - reused here rather than
duplicating invoice bootstrap logic). Idempotency key: `laboratory_orders
.invoice_item_id` - if already set, the existing invoice item is updated in
place (`InvoiceService.update_item`) instead of adding a new one, so
re-completing an order (e.g. after a correction) never double-charges.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.upload_validation import validate_document_upload
from app.models.invoice_item import InvoiceItemType
from app.models.laboratory_order import LABORATORY_ORDER_STATUS_TRANSITIONS, LaboratoryOrder, LaboratoryOrderStatus
from app.models.order import Order, OrderCategory, OrderStatus
from app.models.visit import VisitTimelineEventType
from app.repositories.clinical_orders_repository import ClinicalOrdersRepository
from app.repositories.laboratory_repository import LaboratoryRepository
from app.repositories.visit_repository import VisitRepository
from app.schemas.laboratory import LaboratoryOrderRead, LaboratoryResultRead, LaboratoryTemplateRead
from app.services.audit_service import AuditService
from app.services.invoice_service import InvoiceService

# Maps LaboratoryOrderStatus -> the underlying Phase 9 Order's OrderStatus.
# This is the same class of "reflect a child entity's status onto the
# parent" sync the app has needed three times before (Queue<->Visit in
# Phase 7, Consultation<->Visit in Phase 8, Order/Procedure/etc-created not
# invalidating the Visit timeline cache key in Phase 9) - here the *parent*
# is the Phase 9 `orders` row the Consultation page's Orders tab reads
# `OrderRead.status` from, and the *child* is this phase's own
# `laboratory_orders.status` (which has more granular states, including the
# terminal "Released" Phase 9 never needed). Both Completed and Released
# map to Order's terminal `Completed` since Phase 9's shared `OrderStatus`
# enum has no "Released" state - the Orders tab shows a lab order as
# Completed once results are entered, whether or not the lab has since
# clicked "Release" (a Laboratory Management-internal distinction the
# doctor-facing generic Orders tab doesn't need to represent).
_ORDER_STATUS_SYNC_MAP: dict[LaboratoryOrderStatus, OrderStatus] = {
    LaboratoryOrderStatus.REQUESTED: OrderStatus.REQUESTED,
    LaboratoryOrderStatus.COLLECTED: OrderStatus.COLLECTED,
    LaboratoryOrderStatus.PROCESSING: OrderStatus.PROCESSING,
    LaboratoryOrderStatus.COMPLETED: OrderStatus.COMPLETED,
    LaboratoryOrderStatus.RELEASED: OrderStatus.COMPLETED,
    LaboratoryOrderStatus.CANCELLED: OrderStatus.CANCELLED,
}


def _full_name(entity) -> str | None:
    if entity is None:
        return None
    parts = [entity.first_name, getattr(entity, "middle_name", None), entity.last_name, getattr(entity, "suffix", None)]
    return " ".join(p for p in parts if p)


def _to_read(lab_order: LaboratoryOrder) -> LaboratoryOrderRead:
    order: Order | None = lab_order.order
    return LaboratoryOrderRead(
        id=lab_order.id,
        order_id=lab_order.order_id,
        order_number=order.order_number if order else None,
        visit_id=lab_order.visit_id,
        visit_number=None,
        patient_id=lab_order.patient_id,
        patient_name=_full_name(lab_order.patient),
        doctor_id=lab_order.doctor_id,
        doctor_name=_full_name(lab_order.doctor),
        template_id=lab_order.template_id,
        test_type=lab_order.test_type,
        priority=order.priority.value if order else None,
        status=lab_order.status,
        scheduled_date=order.scheduled_date.isoformat() if order and order.scheduled_date else None,
        collected_at=lab_order.collected_at,
        collected_by=lab_order.collected_by,
        processing_started_at=lab_order.processing_started_at,
        completed_at=lab_order.completed_at,
        released_at=lab_order.released_at,
        released_by=lab_order.released_by,
        invoice_item_id=lab_order.invoice_item_id,
        created_at=lab_order.created_at,
        results=[LaboratoryResultRead.model_validate(r, from_attributes=True) for r in lab_order.results],
        attachments=[],
    )


class LaboratoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = LaboratoryRepository(session)
        self.visit_repo = VisitRepository(session)
        self.audit_service = AuditService(session)
        self.invoice_service = InvoiceService(session)
        self.orders_repo = ClinicalOrdersRepository(session)

    async def _sync_order_status(self, lab_order: LaboratoryOrder, *, clinic_id: UUID) -> None:
        """Mirrors `lab_order.status` onto the underlying Phase 9 `orders`
        row so the Consultation page's Orders tab (which reads `OrderRead
        .status`, a completely separate table from `laboratory_orders`)
        reflects the lab workflow's progress instead of staying stuck on
        `Requested` forever. Guarded to no-op silently if the Order can't be
        found or the mapped status isn't a legal transition from the
        Order's current status (e.g. it was independently cancelled) -
        `laboratory_orders.status` stays the source of truth for the lab
        workflow either way, same guarding philosophy as the Phase 7
        Queue<->Visit sync helper."""
        order = await self.orders_repo.get_order(lab_order.order_id, clinic_id)
        if order is None:
            return
        target = _ORDER_STATUS_SYNC_MAP.get(lab_order.status)
        if target is None or target == order.status:
            return
        from app.models.order import ORDER_STATUS_TRANSITIONS

        if target not in ORDER_STATUS_TRANSITIONS.get(order.status, set()):
            return
        await self.orders_repo.update_order(order, status=target)

    async def _require(self, laboratory_order_id: UUID, clinic_id: UUID) -> LaboratoryOrder:
        lab_order = await self.repo.get_by_id(laboratory_order_id, clinic_id)
        if lab_order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Laboratory order not found")
        return lab_order

    def _transition(self, lab_order: LaboratoryOrder, new_status: LaboratoryOrderStatus) -> None:
        allowed = LABORATORY_ORDER_STATUS_TRANSITIONS.get(lab_order.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot transition laboratory order from {lab_order.status.value} to {new_status.value}.",
            )

    # --- Creation (attaches to an existing Phase 9 Laboratory-category Order) ---

    async def create_from_order(self, order: Order, *, clinic_id: UUID, actor_id: UUID | None) -> LaboratoryOrder:
        """Idempotent: if a laboratory_orders row already exists for this
        order (e.g. called twice), returns the existing one rather than
        raising or duplicating - mirrors the invoice auto-creation
        idempotency pattern used across the app."""
        existing = await self.repo.get_by_order_id(order.id, clinic_id)
        if existing is not None:
            return existing

        test_type = order.items[0].item_name if order.items else "Laboratory Test"
        template_id = None
        # Best-effort match against an active template by exact name - lets
        # the doctor's free-text item name auto-link to a configured
        # template (pricing/turnaround/parameters) without requiring a
        # separate "select template" step in the Phase 9 order-creation UI.
        templates = await self.repo.list_templates(clinic_id, active_only=True)
        for t in templates:
            if t.test_name.strip().lower() == test_type.strip().lower():
                template_id = t.id
                break

        lab_order = await self.repo.create_laboratory_order(
            clinic_id=clinic_id, order_id=order.id, branch_id=order.branch_id, visit_id=order.visit_id,
            patient_id=order.patient_id, doctor_id=order.doctor_id, template_id=template_id, test_type=test_type,
            status=LaboratoryOrderStatus.REQUESTED,
        )
        await self.session.commit()
        return await self.repo.get_by_id(lab_order.id, clinic_id)

    # --- Reads ---

    async def get(self, laboratory_order_id: UUID, *, clinic_id: UUID) -> LaboratoryOrderRead:
        lab_order = await self._require(laboratory_order_id, clinic_id)
        return _to_read(lab_order)

    async def list_for_dashboard(self, *, clinic_id: UUID) -> list[LaboratoryOrderRead]:
        rows = await self.repo.list_for_clinic(clinic_id)
        return [_to_read(r) for r in rows]

    async def dashboard_stats(self, *, clinic_id: UUID) -> dict:
        today = datetime.now(UTC).date()
        return await self.repo.dashboard_counts(clinic_id, today=today)

    async def list_for_visit(self, visit_id: UUID, *, clinic_id: UUID) -> list[LaboratoryOrderRead]:
        rows = await self.repo.list_for_visit(visit_id, clinic_id)
        return [_to_read(r) for r in rows]

    async def list_for_patient(self, patient_id: UUID, *, clinic_id: UUID) -> list[LaboratoryOrderRead]:
        rows = await self.repo.list_for_patient(patient_id, clinic_id)
        return [_to_read(r) for r in rows]

    # --- Transitions ---

    async def collect_specimen(self, laboratory_order_id: UUID, *, clinic_id: UUID, actor_id: UUID) -> LaboratoryOrderRead:
        lab_order = await self._require(laboratory_order_id, clinic_id)
        self._transition(lab_order, LaboratoryOrderStatus.COLLECTED)
        now = datetime.now(UTC)
        await self.repo.update_laboratory_order(lab_order, status=LaboratoryOrderStatus.COLLECTED, collected_at=now, collected_by=actor_id)
        await self._sync_order_status(lab_order, clinic_id=clinic_id)
        await self.visit_repo.add_timeline_event(
            clinic_id=clinic_id, visit_id=lab_order.visit_id, event_type=VisitTimelineEventType.LAB_SPECIMEN_COLLECTED,
            occurred_at=now, recorded_by=actor_id, note=f"Specimen collected - {lab_order.test_type}",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="laboratory.specimen_collected",
            entity_type="laboratory_order", entity_id=str(lab_order.id),
        )
        await self.session.commit()
        return await self.get(laboratory_order_id, clinic_id=clinic_id)

    async def start_processing(self, laboratory_order_id: UUID, *, clinic_id: UUID, actor_id: UUID) -> LaboratoryOrderRead:
        lab_order = await self._require(laboratory_order_id, clinic_id)
        self._transition(lab_order, LaboratoryOrderStatus.PROCESSING)
        now = datetime.now(UTC)
        await self.repo.update_laboratory_order(lab_order, status=LaboratoryOrderStatus.PROCESSING, processing_started_at=now)
        await self._sync_order_status(lab_order, clinic_id=clinic_id)
        await self.visit_repo.add_timeline_event(
            clinic_id=clinic_id, visit_id=lab_order.visit_id, event_type=VisitTimelineEventType.LAB_PROCESSING_STARTED,
            occurred_at=now, recorded_by=actor_id, note=f"Processing started - {lab_order.test_type}",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="laboratory.processing_started",
            entity_type="laboratory_order", entity_id=str(lab_order.id),
        )
        await self.session.commit()
        return await self.get(laboratory_order_id, clinic_id=clinic_id)

    async def enter_results(
        self, laboratory_order_id: UUID, results: list[dict], *, clinic_id: UUID, actor_id: UUID
    ) -> LaboratoryOrderRead:
        lab_order = await self._require(laboratory_order_id, clinic_id)
        if lab_order.status not in {LaboratoryOrderStatus.COLLECTED, LaboratoryOrderStatus.PROCESSING, LaboratoryOrderStatus.COMPLETED}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot enter results while the order is {lab_order.status.value}.",
            )
        now = datetime.now(UTC)
        await self.repo.upsert_results(laboratory_order_id, clinic_id, results, actor_id=actor_id)
        # The `results` relationship on the already-loaded `lab_order`
        # instance is stale after the delete+recreate in `upsert_results`
        # (same session, different rows) - expire it so the final `get()`
        # re-fetches the fresh set instead of an empty/stale collection.
        self.session.expire(lab_order, ["results"])

        new_status = lab_order.status
        completed_at = lab_order.completed_at
        if lab_order.status != LaboratoryOrderStatus.COMPLETED:
            new_status = LaboratoryOrderStatus.COMPLETED
            completed_at = now
        await self.repo.update_laboratory_order(lab_order, status=new_status, completed_at=completed_at)
        await self._sync_order_status(lab_order, clinic_id=clinic_id)

        await self.visit_repo.add_timeline_event(
            clinic_id=clinic_id, visit_id=lab_order.visit_id, event_type=VisitTimelineEventType.LAB_RESULTS_ENTERED,
            occurred_at=now, recorded_by=actor_id, note=f"Results entered - {lab_order.test_type} ({len(results)} parameter(s))",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="laboratory.results_entered",
            entity_type="laboratory_order", entity_id=str(lab_order.id), metadata={"parameter_count": len(results)},
        )
        await self.session.commit()

        # Billing integration - fires once the order first reaches Completed.
        if completed_at == now:
            await self._sync_billing(lab_order, clinic_id=clinic_id, actor_id=actor_id)

        return await self.get(laboratory_order_id, clinic_id=clinic_id)

    async def release_results(self, laboratory_order_id: UUID, *, clinic_id: UUID, actor_id: UUID) -> LaboratoryOrderRead:
        lab_order = await self._require(laboratory_order_id, clinic_id)
        self._transition(lab_order, LaboratoryOrderStatus.RELEASED)
        now = datetime.now(UTC)
        await self.repo.update_laboratory_order(lab_order, status=LaboratoryOrderStatus.RELEASED, released_at=now, released_by=actor_id)
        await self._sync_order_status(lab_order, clinic_id=clinic_id)
        await self.visit_repo.add_timeline_event(
            clinic_id=clinic_id, visit_id=lab_order.visit_id, event_type=VisitTimelineEventType.LAB_RESULTS_RELEASED,
            occurred_at=now, recorded_by=actor_id, note=f"Results released - {lab_order.test_type}",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="laboratory.results_released",
            entity_type="laboratory_order", entity_id=str(lab_order.id),
        )
        await self.session.commit()
        return await self.get(laboratory_order_id, clinic_id=clinic_id)

    async def cancel_order(self, laboratory_order_id: UUID, *, clinic_id: UUID, actor_id: UUID) -> LaboratoryOrderRead:
        lab_order = await self._require(laboratory_order_id, clinic_id)
        self._transition(lab_order, LaboratoryOrderStatus.CANCELLED)
        now = datetime.now(UTC)
        await self.repo.update_laboratory_order(lab_order, status=LaboratoryOrderStatus.CANCELLED)
        await self._sync_order_status(lab_order, clinic_id=clinic_id)
        await self.visit_repo.add_timeline_event(
            clinic_id=clinic_id, visit_id=lab_order.visit_id, event_type=VisitTimelineEventType.LAB_ORDER_CANCELLED,
            occurred_at=now, recorded_by=actor_id, note=f"Laboratory order cancelled - {lab_order.test_type}",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="laboratory.order_cancelled",
            entity_type="laboratory_order", entity_id=str(lab_order.id),
        )
        await self.session.commit()
        return await self.get(laboratory_order_id, clinic_id=clinic_id)

    # --- Billing integration (idempotent) ---

    async def _sync_billing(self, lab_order: LaboratoryOrder, *, clinic_id: UUID, actor_id: UUID | None) -> None:
        if lab_order.template_id is None or lab_order.template is None:
            return
        price = Decimal(str(lab_order.template.default_price or 0))
        if price <= 0:
            return

        invoice = await self.invoice_service.create_draft_invoice_for_consultation(
            clinic_id=clinic_id, visit_id=lab_order.visit_id, actor_id=actor_id
        )

        if lab_order.invoice_item_id is not None:
            existing_item = await self.invoice_service.repo.get_item(lab_order.invoice_item_id, invoice.id, clinic_id)
            if existing_item is not None:
                await self.invoice_service.update_item(
                    invoice.id, existing_item.id,
                    {"description": lab_order.test_type, "unit_price": price, "quantity": Decimal("1")},
                    clinic_id=clinic_id, actor_id=actor_id,
                )
                return

        # Identify the newly-added line via a fresh, explicit "ids before"
        # query issued right before the add (NOT by matching `description`,
        # and NOT by reusing the `invoice.items` collection already cached
        # on this session's identity-mapped `Invoice` object - both were
        # tried and both broke: two different laboratory orders for the
        # same test share the same description, AND the cached collection
        # can still reflect a snapshot from an earlier call in the same
        # request, so a same-session diff against it silently attributed a
        # *different* order's invoice_item_id to this one - found live
        # while testing two CBC orders on the same visit).
        await self.session.refresh(invoice, attribute_names=["items"])
        before_ids = {i.id for i in invoice.items}
        detail = await self.invoice_service.add_item(
            invoice.id,
            {
                "description": lab_order.test_type, "item_type": InvoiceItemType.LABORATORY,
                "quantity": Decimal("1"), "unit_price": price, "discount_amount": Decimal("0"),
            },
            clinic_id=clinic_id, actor_id=actor_id,
        )
        new_item = next((i for i in detail.items if i.id not in before_ids), None)
        if new_item is not None:
            await self.repo.update_laboratory_order(lab_order, invoice_item_id=new_item.id)
            await self.session.commit()

    # --- Attachments ---

    async def add_attachment(
        self, laboratory_order_id: UUID, payload: dict, *, clinic_id: UUID, actor_id: UUID | None
    ) -> LaboratoryOrder:
        lab_order = await self._require(laboratory_order_id, clinic_id)
        # Phase 16: same real gap as consultation attachments - no
        # server-side validation of the client-declared file name/size
        # existed before this. Lab result scans/attachments are documents,
        # not photos, so use the document allow-list/size limit.
        validate_document_upload(file_name=payload["file_name"], file_size_bytes=payload.get("file_size_bytes"))
        file_url = f"https://storage.stub.connectph.dev/laboratory/{laboratory_order_id}/{payload['file_name']}"
        await self.repo.add_attachment(
            clinic_id=clinic_id, laboratory_order_id=lab_order.id, attachment_type=payload["attachment_type"],
            file_name=payload["file_name"], file_url=file_url, file_size_bytes=payload.get("file_size_bytes"),
            uploaded_by=actor_id,
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="laboratory.attachment_added",
            entity_type="laboratory_order", entity_id=str(lab_order.id),
        )
        await self.session.commit()
        return await self._require(laboratory_order_id, clinic_id)

    async def list_attachments(self, laboratory_order_id: UUID, *, clinic_id: UUID) -> list:
        await self._require(laboratory_order_id, clinic_id)
        return await self.repo.list_attachments(laboratory_order_id, clinic_id)

    # --- Templates ---

    async def create_template(self, payload: dict, *, clinic_id: UUID) -> LaboratoryTemplateRead:
        parameters = payload.pop("parameters", [])
        template = await self.repo.create_template(clinic_id=clinic_id, parameters=parameters, **payload)
        await self.session.commit()
        return LaboratoryTemplateRead.model_validate(template, from_attributes=True)

    async def list_templates(self, *, clinic_id: UUID, active_only: bool = False) -> list[LaboratoryTemplateRead]:
        rows = await self.repo.list_templates(clinic_id, active_only=active_only)
        return [LaboratoryTemplateRead.model_validate(r, from_attributes=True) for r in rows]

    async def update_template(self, template_id: UUID, payload: dict, *, clinic_id: UUID) -> LaboratoryTemplateRead:
        template = await self.repo.get_template(template_id, clinic_id)
        if template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Laboratory template not found")
        parameters = payload.pop("parameters", None)
        updates = {k: v for k, v in payload.items() if v is not None}
        template = await self.repo.update_template(template, parameters=parameters, **updates)
        await self.session.commit()
        return LaboratoryTemplateRead.model_validate(template, from_attributes=True)
