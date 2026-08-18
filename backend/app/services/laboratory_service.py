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

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice_item import InvoiceItemType
from app.models.laboratory_attachment import LaboratoryAttachment
from app.models.laboratory_order import LABORATORY_ORDER_STATUS_TRANSITIONS, LaboratoryOrder, LaboratoryOrderStatus
from app.models.laboratory_reference_range import LaboratoryReferenceRange
from app.models.laboratory_result import LaboratoryResultType
from app.models.laboratory_template import DEFAULT_LABORATORY_TEMPLATES, LaboratoryTemplateParameter
from app.models.order import Order, OrderCategory, OrderStatus
from app.models.patient import Patient
from app.models.queue import QUEUE_STATUS_TRANSITIONS, QueueStatus
from app.models.user import User
from app.models.visit import VisitTimelineEventType
from app.repositories.clinical_orders_repository import ClinicalOrdersRepository
from app.repositories.laboratory_repository import LaboratoryRepository
from app.repositories.visit_repository import VisitRepository
from app.schemas.laboratory import LaboratoryAttachmentRead, LaboratoryOrderRead, LaboratoryResultRead, LaboratoryTemplateRead
from app.services.audit_service import AuditService
from app.services.invoice_service import InvoiceService
from app.services.laboratory_interpretation import interpret_result
from app.services.queue_service import QueueService
from app.services import sync_queue_service

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


def attachment_to_read(attachment: LaboratoryAttachment) -> LaboratoryAttachmentRead:
    """Feature 4: builds the API-facing `file_url` as a path into
    `GET /laboratory/orders/{id}/attachments/{id}/file` (see
    `api/v1/laboratory.py::get_attachment_file`), rather than exposing the
    raw on-disk stored filename kept in the `file_url` column - same
    reasoning/shape as `consultation_service.py`'s `attachment_to_read`.
    Shared by `_to_read`, `list_attachments`, and the upload endpoint so
    every place a laboratory order's attachments are serialized resolves
    to the same real, authenticated, viewable URL."""
    return LaboratoryAttachmentRead(
        id=attachment.id,
        attachment_type=attachment.attachment_type,
        file_name=attachment.file_name,
        file_url=f"/laboratory/orders/{attachment.laboratory_order_id}/attachments/{attachment.id}/file",
        file_size_bytes=attachment.file_size_bytes,
        uploaded_by=attachment.uploaded_by,
        created_at=attachment.created_at,
    )


def _to_read(lab_order: LaboratoryOrder) -> LaboratoryOrderRead:
    order: Order | None = lab_order.order
    return LaboratoryOrderRead(
        id=lab_order.id,
        order_id=lab_order.order_id,
        order_number=order.order_number if order else None,
        visit_id=lab_order.visit_id,
        visit_number=None,
        queue_number=lab_order.visit.queue.queue_number if lab_order.visit and lab_order.visit.queue else None,
        patient_id=lab_order.patient_id,
        patient_name=_full_name(lab_order.patient),
        doctor_id=lab_order.doctor_id,
        doctor_name=_full_name(lab_order.doctor),
        template_id=lab_order.template_id,
        template=LaboratoryTemplateRead.model_validate(lab_order.template, from_attributes=True) if lab_order.template else None,
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
        updated_at=lab_order.updated_at,
        results=[LaboratoryResultRead.model_validate(r, from_attributes=True) for r in lab_order.results],
        attachments=[attachment_to_read(a) for a in lab_order.attachments],
    )


def build_sync_payload(lab_order: LaboratoryOrder) -> dict:
    """Sync-queue JSON payload for a laboratory order, shared by any caller
    that commits a `LaboratoryOrder` itself and enqueues the sync job
    afterward (see `ClinicalOrdersService.create_order`, which calls this
    via `sync_queue_service.enqueue_lazy` only AFTER its own commit has
    succeeded) - keeps the field mapping in exactly one place (`_to_read`)."""
    return _to_read(lab_order).model_dump(mode="json")


class LaboratoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = LaboratoryRepository(session)
        self.visit_repo = VisitRepository(session)
        self.audit_service = AuditService(session)
        self.invoice_service = InvoiceService(session)
        self.orders_repo = ClinicalOrdersRepository(session)
        self.queue_service = QueueService(session)

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
        idempotency pattern used across the app.

        Deliberately does NOT commit and does NOT enqueue a sync job -
        this is always invoked from `ClinicalOrdersService.create_order()`
        while the parent `Order` is still in the SAME uncommitted
        transaction. The caller commits both rows together in one
        `session.commit()` and enqueues the sync job (via
        `build_sync_payload` below) only after that single commit
        succeeds. Previously this method committed independently, which
        meant a failure anywhere between the `Order`'s own (earlier)
        commit and this row's commit - e.g. the daily order-number
        counter's first-of-day race - could leave a committed `Order`
        with no matching `LaboratoryOrder`: the doctor saw the Order after
        a refresh, but the Laboratory Technician's worklist correctly
        showed nothing, because the row genuinely never existed."""
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

        return await self.repo.create_laboratory_order(
            clinic_id=clinic_id, order_id=order.id, branch_id=order.branch_id, visit_id=order.visit_id,
            patient_id=order.patient_id, doctor_id=order.doctor_id, template_id=template_id, test_type=test_type,
            status=LaboratoryOrderStatus.REQUESTED,
        )

    # --- Reads ---

    async def get(self, laboratory_order_id: UUID, *, clinic_id: UUID) -> LaboratoryOrderRead:
        lab_order = await self._require(laboratory_order_id, clinic_id)
        order_read = _to_read(lab_order)
        await self._overlay_resolved_ranges(order_read, lab_order, clinic_id=clinic_id)
        return order_read

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

    @staticmethod
    def _resolve_interpretation(result: dict) -> dict:
        """Feature 3: fills in `interpretation` via `interpret_result()`
        when the client left it unset (None) - an explicit client-supplied
        value (whether it matches what would've been computed, or is a
        deliberate clinician override) is always respected as-is and never
        recalculated/overwritten here. `expected_normal_text` is popped
        off regardless of outcome - it's a transient input only, not a
        column on `LaboratoryResult` (see schema docstring)."""
        result = dict(result)
        expected_normal_text = result.pop("expected_normal_text", None)
        if result.get("interpretation") is None:
            result["interpretation"] = interpret_result(
                result_type=result.get("result_type"),
                numeric_value=result.get("numeric_value"),
                text_value=result.get("text_value"),
                range_low=result.get("range_low"),
                range_high=result.get("range_high"),
                expected_normal_text=expected_normal_text,
            )
        return result

    async def enter_results(
        self,
        laboratory_order_id: UUID,
        results: list[dict],
        *,
        clinic_id: UUID,
        actor_id: UUID,
        expected_updated_at: datetime | None = None,
    ) -> LaboratoryOrderRead:
        lab_order = await self._require(laboratory_order_id, clinic_id)
        if lab_order.status not in {LaboratoryOrderStatus.COLLECTED, LaboratoryOrderStatus.PROCESSING, LaboratoryOrderStatus.COMPLETED}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot enter results while the order is {lab_order.status.value}.",
            )
        # Phase 4I: optimistic-concurrency guard against the lost-update
        # race `upsert_results`' replace-all semantics otherwise allow - if
        # the client's snapshot is stale (someone else saved in between),
        # reject rather than silently overwrite their save. Skipped
        # entirely when the client doesn't supply a token (backward
        # compatible with any caller that predates this check).
        if expected_updated_at is not None and lab_order.updated_at != expected_updated_at:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This order was updated by someone else since you opened it. Reload and try again.",
            )
        now = datetime.now(UTC)
        results = [await self._apply_resolved_range_to_result(lab_order, r) for r in results]
        results = [self._resolve_interpretation(r) for r in results]
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

        # Phase 6: billing sync must run BEFORE the response snapshot is
        # read, not after - `_sync_billing` sets `lab_order.invoice_item_id`
        # and commits, but the old ordering took the `get()` snapshot first,
        # so the response the client actually received always had a stale
        # (null, on first completion) `invoice_item_id` even though the
        # invoice line item really was created moments later in the same
        # request. Root cause of the persistent
        # test_completing_priced_order_creates_invoice_line_item /
        # test_billing_sync_idempotent_on_resubmit failures - a genuine
        # ordering defect, not a test/environment issue.
        if completed_at == now:
            await self._sync_billing(lab_order, clinic_id=clinic_id, actor_id=actor_id)

        result_read = await self.get(laboratory_order_id, clinic_id=clinic_id)
        await sync_queue_service.enqueue_lazy(
            entity_type="laboratory_result", record_id=laboratory_order_id, operation="update",
            clinic_id=clinic_id, build_payload=lambda: result_read.model_dump(mode="json"),
        )

        return result_read

    async def _sync_queue_on_release(self, lab_order: LaboratoryOrder, *, clinic_id: UUID, actor_id: UUID) -> None:
        """Mirrors a Released LaboratoryOrder onto its Visit's linked
        Reception Queue ticket, if any - a Laboratory-only queue ticket is
        Called but never enters a doctor consultation, so nothing else
        ever moves it off the TV/queue display; releasing the lab result
        is the natural "this patient's visit here is finished" signal for
        that ticket. Mirrors `DoctorWorkspaceService._sync_queue_status`'s
        exact pattern: never mutates `Queue.status` directly, always goes
        through `QueueService.change_status()` (so history/audit/broadcast/
        sync-queue all fire through the one existing mechanism); no-ops if
        there's no linked queue, the queue is already Completed
        (idempotent - a second `release_results` call can't even reach
        here since `_transition` above already rejects re-releasing an
        already-Released order, but this stays independently safe), or the
        transition isn't currently legal (e.g. the ticket was independently
        cancelled/skipped by Reception - the queue ticket owns its own
        status, this sync never forces an illegal transition onto it).
        Only Called->Completed is affected; a doctor/consultation ticket
        already reaches Completed via Serving (see `_VISIT_TO_QUEUE_STATUS`
        in doctor_workspace_service.py) and is untouched by this."""
        visit = lab_order.visit
        if visit is None or visit.queue_id is None:
            return
        queue = visit.queue
        if queue is None or queue.status == QueueStatus.COMPLETED:
            return
        if QueueStatus.COMPLETED not in QUEUE_STATUS_TRANSITIONS.get(queue.status, set()):
            return
        actor = await self.session.get(User, actor_id)
        if actor is None:
            return
        await self.queue_service.change_status(
            visit.queue_id, clinic_id=clinic_id, actor=actor, new_status=QueueStatus.COMPLETED,
            note="Laboratory results released",
        )

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
        await self._sync_queue_on_release(lab_order, clinic_id=clinic_id, actor_id=actor_id)
        released_read = await self.get(laboratory_order_id, clinic_id=clinic_id)
        await sync_queue_service.enqueue_lazy(
            entity_type="laboratory_order", record_id=laboratory_order_id, operation="update",
            clinic_id=clinic_id, build_payload=lambda: released_read.model_dump(mode="json"),
        )
        return released_read

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

    async def add_attachment_record(
        self, laboratory_order_id: UUID, *, clinic_id: UUID, actor_id: UUID | None, attachment_type,
        file_name: str, stored_filename: str, file_size_bytes: int,
    ) -> LaboratoryAttachment:
        """Feature 4: inserts the DB row for a file the caller (the API
        layer) has already validated and written to disk under the
        existing persistent `/app/var` volume - same split of
        responsibility as `ConsultationService.add_attachment_record`.
        `stored_filename` is the on-disk filename only (not a URL);
        resolving it to a real authenticated URL is `attachment_to_read`'s
        job, since this service has no notion of the file-serving route."""
        lab_order = await self._require(laboratory_order_id, clinic_id)
        attachment = await self.repo.add_attachment(
            clinic_id=clinic_id, laboratory_order_id=lab_order.id, attachment_type=attachment_type,
            file_name=file_name, file_url=stored_filename, file_size_bytes=file_size_bytes, uploaded_by=actor_id,
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="laboratory.attachment_added",
            entity_type="laboratory_order", entity_id=str(lab_order.id),
        )
        await self.session.commit()
        return attachment

    async def list_attachments(self, laboratory_order_id: UUID, *, clinic_id: UUID) -> list[LaboratoryAttachment]:
        await self._require(laboratory_order_id, clinic_id)
        return await self.repo.list_attachments(laboratory_order_id, clinic_id)

    async def get_attachment(self, laboratory_order_id: UUID, attachment_id: UUID, *, clinic_id: UUID) -> LaboratoryAttachment:
        await self._require(laboratory_order_id, clinic_id)
        attachment = await self.repo.get_attachment(attachment_id, laboratory_order_id, clinic_id)
        if attachment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
        return attachment

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

    async def seed_default_templates(self, *, clinic_id: UUID, actor_id: UUID) -> list[LaboratoryTemplateRead]:
        """Feature 3 starter templates (CBC, Urinalysis) - same opt-in,
        explicitly-invoked-per-clinic pattern as `DEFAULT_SERVICES`/
        `ClinicServiceCatalogService.seed_defaults` (never auto-run).
        Structure only (parameter names/units) - no reference ranges are
        seeded; skips any test_name that already exists for this clinic so
        it's safe to call more than once."""
        existing = await self.repo.list_templates(clinic_id, active_only=False)
        existing_names = {t.test_name.strip().lower() for t in existing}
        created = []
        for entry in DEFAULT_LABORATORY_TEMPLATES:
            if entry["test_name"].strip().lower() in existing_names:
                continue
            parameters = entry["parameters"]
            fields = {k: v for k, v in entry.items() if k != "parameters"}
            template = await self.repo.create_template(clinic_id=clinic_id, parameters=parameters, **fields)
            created.append(template)
        if created:
            await self.audit_service.log_event(
                clinic_id=clinic_id, user_id=actor_id, action="laboratory.default_templates_seeded",
                entity_type="laboratory_template", metadata={"count": len(created), "test_names": [t.test_name for t in created]},
            )
            await self.session.commit()
        return [LaboratoryTemplateRead.model_validate(t, from_attributes=True) for t in created]

    # --- Reference Ranges (Phase 2A - Structured Result Backend Foundation) ---
    # Additive companion to each LaboratoryTemplateParameter's own default
    # range_low/range_high/expected_normal_text (unchanged). Not yet wired
    # into `enter_results`/`_resolve_interpretation` above - see this
    # module's Phase 2A note there and `laboratory_repository.py`'s
    # `resolve_reference_range` docstring.

    async def _require_template_parameter(self, template_parameter_id: UUID, clinic_id: UUID):
        stmt = select(LaboratoryTemplateParameter).where(
            LaboratoryTemplateParameter.id == template_parameter_id,
            LaboratoryTemplateParameter.clinic_id == clinic_id,
        )
        parameter = (await self.session.execute(stmt)).scalar_one_or_none()
        if parameter is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Laboratory template parameter not found")
        return parameter

    async def create_reference_range(
        self, template_parameter_id: UUID, payload: dict, *, clinic_id: UUID, actor_id: UUID
    ) -> LaboratoryReferenceRange:
        await self._require_template_parameter(template_parameter_id, clinic_id)
        reference_range = await self.repo.create_reference_range(
            clinic_id=clinic_id, template_parameter_id=template_parameter_id, created_by=actor_id, **payload
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="laboratory.reference_range_created",
            entity_type="laboratory_reference_range", entity_id=str(reference_range.id),
            metadata={"template_parameter_id": str(template_parameter_id)},
        )
        await self.session.commit()
        return reference_range

    async def list_reference_ranges(
        self, template_parameter_id: UUID, *, clinic_id: UUID, active_only: bool = False
    ) -> list[LaboratoryReferenceRange]:
        await self._require_template_parameter(template_parameter_id, clinic_id)
        return await self.repo.list_reference_ranges_for_parameter(template_parameter_id, clinic_id, active_only=active_only)

    async def set_reference_range_active(
        self, reference_range_id: UUID, is_active: bool, *, clinic_id: UUID, actor_id: UUID
    ) -> LaboratoryReferenceRange:
        reference_range = await self.repo.get_reference_range(reference_range_id, clinic_id)
        if reference_range is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Laboratory reference range not found")
        reference_range = await self.repo.update_reference_range(reference_range, is_active=is_active)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id,
            action="laboratory.reference_range_activated" if is_active else "laboratory.reference_range_deactivated",
            entity_type="laboratory_reference_range", entity_id=str(reference_range.id),
        )
        await self.session.commit()
        return reference_range

    @staticmethod
    def _age_years(birth_date: date, *, as_of: date) -> int:
        years = as_of.year - birth_date.year
        if (as_of.month, as_of.day) < (birth_date.month, birth_date.day):
            years -= 1
        return years

    @staticmethod
    def _format_resolved_range_text(range_low: Decimal | None, range_high: Decimal | None, qualitative_expected: str | None) -> str | None:
        """A `LaboratoryReferenceRange` has no free-text `normal_range`
        column of its own (only structured range_low/range_high/
        qualitative_expected) - the template parameter's own `normal_range`
        is a separate, human-authored display string. When a demographic-
        specific range is actually resolved, synthesize a display string
        from its structured bounds so the existing "Normal Range" field the
        frontend already renders (unchanged UI) reflects the range that's
        actually in effect, not a stale template-wide description."""
        if range_low is not None and range_high is not None:
            return f"{range_low}-{range_high}"
        if qualitative_expected is not None:
            return qualitative_expected
        return None

    async def _resolved_parameter_range(
        self, parameter: LaboratoryTemplateParameter, patient: Patient | None, *, clinic_id: UUID
    ) -> tuple[Decimal | None, Decimal | None, str | None, str | None]:
        """Phase 2B: THE single authoritative range-resolution call, used by
        both `get()` (so Result Entry's prefill - which only ever reads
        `order.template.parameters[i].range_low/range_high/
        expected_normal_text/normal_range`, unchanged since Phase 2A - sees
        the resolved value) and `enter_results` (so the range
        interpretation/storage is based on, and the range persisted to
        `LaboratoryResult`, are the same resolved value the technician was
        shown). Neither the frontend nor any other backend code path
        computes or overrides a range independently. `patient` should
        already be the order's own eager-loaded `Patient` (no extra query)
        - `None` (shouldn't happen for a real order, but defensively
        handled) skips straight to the template default. Precedence: an
        active, demographic-matching `LaboratoryReferenceRange` if one
        exists, else the template parameter's own default - identical rule
        as `resolve_reference_range_for_patient`, just reusing the
        already-loaded Patient instead of re-querying it.

        Returns `(range_low, range_high, expected_normal_text, normal_range_display)`
        - the 4th element is only non-None when an actual
        `LaboratoryReferenceRange` was matched (see
        `_format_resolved_range_text`); `None` means "caller should leave
        the template parameter's own free-text normal_range untouched" -
        exactly today's fallback behavior."""
        if patient is not None:
            age_years = self._age_years(patient.birth_date, as_of=datetime.now(UTC).date())
            reference_range = await self.repo.resolve_reference_range(
                parameter.id, clinic_id, sex=patient.gender, age_years=age_years
            )
            if reference_range is not None:
                display_text = self._format_resolved_range_text(
                    reference_range.range_low, reference_range.range_high, reference_range.qualitative_expected
                )
                return reference_range.range_low, reference_range.range_high, reference_range.qualitative_expected, display_text
        return parameter.range_low, parameter.range_high, parameter.expected_normal_text, None

    async def _overlay_resolved_ranges(
        self, order_read: LaboratoryOrderRead, lab_order: LaboratoryOrder, *, clinic_id: UUID
    ) -> None:
        """Phase 2B: overlays the patient-resolved range (see
        `_resolved_parameter_range`) onto each parameter of the read
        model's embedded template, in place - the ONLY place this happens
        for a read/display path. Only mutates this in-memory response
        object, never the template/parameter rows themselves, so every
        other order for the same template (a different patient) resolves
        independently on its own next read."""
        if order_read.template is None or lab_order.template is None or lab_order.patient is None:
            return
        resolved_by_id = {
            parameter.id: await self._resolved_parameter_range(parameter, lab_order.patient, clinic_id=clinic_id)
            for parameter in lab_order.template.parameters
        }
        for param_read in order_read.template.parameters:
            resolved = resolved_by_id.get(param_read.id)
            if resolved is None:
                continue
            range_low, range_high, expected_normal_text, display_text = resolved
            param_read.range_low, param_read.range_high, param_read.expected_normal_text = range_low, range_high, expected_normal_text
            if display_text is not None:
                param_read.normal_range = display_text

    @staticmethod
    def _validate_categorical_value(parameter: LaboratoryTemplateParameter, result: dict) -> None:
        """Phase 3: the backend, not the browser, is the enforcement point
        for a Categorical parameter's allowed values - a hand-crafted
        request submitting an unconfigured value (or no value at all) for
        a parameter that DOES have `options` configured is rejected with a
        400, exactly as a malicious/modified client bypassing the
        frontend's `<Select>` must be. A parameter with no `options`
        configured (or a non-Categorical parameter) has nothing to
        validate against and is left alone - same "never guess/never
        invent a constraint that wasn't configured" principle used
        throughout this module (range/critical-value resolution)."""
        if parameter.result_type != LaboratoryResultType.CATEGORICAL:
            return
        options = parameter.options
        if not options:
            return
        structured_value = result.get("structured_value")
        selected = structured_value.get("value") if isinstance(structured_value, dict) else None
        if selected is None or selected not in options:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"'{result.get('parameter_name')}' must be one of: {', '.join(str(o) for o in options)}."
                ),
            )

    async def _apply_resolved_range_to_result(self, lab_order: LaboratoryOrder, result: dict) -> dict:
        """Phase 2B: the `enter_results` counterpart to `_overlay_resolved_ranges`
        - re-resolves the authoritative range for the submitted parameter
        (matched by name against the order's linked template, same
        case-insensitive-exact-match convention `create_from_order` already
        uses to link a template in the first place) and overwrites whatever
        range_low/range_high/expected_normal_text arrived in the request
        with it, so interpretation and the persisted `LaboratoryResult` are
        always based on the backend's own resolution - never a value the
        frontend merely echoed back. A parameter with no template match
        (untemplated order, or a free-text/ad-hoc row with no matching
        template parameter name) is left exactly as submitted - unchanged
        fallback behavior for every order without a usable template match,
        identical to pre-Phase-2B.

        Phase 3: also validates a matched Categorical parameter's submitted
        `structured_value` against its configured `options` (see
        `_validate_categorical_value`) - the same single per-parameter
        match this method already does for range resolution is reused,
        not a second lookup/engine."""
        if lab_order.template is None:
            return result
        parameter_name = (result.get("parameter_name") or "").strip().lower()
        parameter = next(
            (p for p in lab_order.template.parameters if p.parameter_name.strip().lower() == parameter_name), None
        )
        if parameter is None:
            return result
        self._validate_categorical_value(parameter, result)
        range_low, range_high, expected_normal_text, display_text = await self._resolved_parameter_range(
            parameter, lab_order.patient, clinic_id=lab_order.clinic_id
        )
        result = dict(result)
        result["range_low"] = range_low
        result["range_high"] = range_high
        result["expected_normal_text"] = expected_normal_text
        if display_text is not None:
            result["normal_range"] = display_text
        return result

    async def resolve_reference_range_for_patient(
        self, template_parameter_id: UUID, patient_id: UUID, *, clinic_id: UUID
    ) -> LaboratoryReferenceRange | None:
        """Phase 2A foundation: resolves the demographic-specific reference
        range that applies to `patient_id` for this parameter, per the
        future precedence rule (see `laboratory_repository.py`'s
        `resolve_reference_range` docstring) - `None` means "no matching
        override; caller should fall back to the template parameter's own
        default range_low/range_high/expected_normal_text", exactly as
        every result-entry call already does today. Does not itself change
        any existing behavior - callable standalone ahead of being wired
        into the live result-entry path in a future phase."""
        await self._require_template_parameter(template_parameter_id, clinic_id)
        stmt = select(Patient).where(Patient.id == patient_id, Patient.clinic_id == clinic_id)
        patient = (await self.session.execute(stmt)).scalar_one_or_none()
        if patient is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
        age_years = self._age_years(patient.birth_date, as_of=datetime.now(UTC).date())
        return await self.repo.resolve_reference_range(
            template_parameter_id, clinic_id, sex=patient.gender, age_years=age_years
        )
