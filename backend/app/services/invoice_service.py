"""Invoice service (Phase 9 - Billing & Cashier).

Consultation -> Invoice sync (called from `ConsultationService.complete_consultation()`,
mirroring exactly how `VisitService`/`QueueService` call into each other -
see that module's docstring): `create_draft_invoice_for_consultation()` is
idempotent - if a non-cancelled invoice already exists for the visit, it is
returned as-is rather than duplicated (guards against double-complete races,
the same lesson Phase 8 already learned for Consultation/Visit/Queue sync).

Pricing for the auto-added Consultation Fee line item: prefers
`Doctor.consultation_fee` (more specific - a per-doctor fee) when set and
positive, falling back to the visit's `ClinicService.default_price` (the
service-catalog price for whatever service the visit was booked for), and
finally a zero-priced placeholder line if neither is available - the
cashier can then edit the price manually via `update_item`.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinic_service import ClinicService
from app.models.doctor import Doctor
from app.models.invoice import INVOICE_STATUS_TRANSITIONS, Invoice, InvoiceStatus
from app.models.invoice_item import InvoiceItemType
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.visit_repository import VisitRepository
from app.schemas.billing import (
    BillingHistoryItem,
    DiscountRead,
    InvoiceDetail,
    InvoiceItemRead,
    InvoiceListItem,
    InvoiceRead,
    PaymentRead,
)
from app.services.audit_service import AuditService
from app.services.invoice_number_generator import InvoiceNumberGenerator

NON_EDITABLE_STATUSES = {InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID, InvoiceStatus.CANCELLED}


def _full_name(entity) -> str:
    parts = [entity.first_name, getattr(entity, "middle_name", None), entity.last_name, getattr(entity, "suffix", None)]
    return " ".join(p for p in parts if p)


def _to_read(inv: Invoice) -> InvoiceRead:
    return InvoiceRead.model_validate(inv, from_attributes=True)


def _to_list_item(inv: Invoice) -> InvoiceListItem:
    return InvoiceListItem(
        id=inv.id, invoice_number=inv.invoice_number, visit_id=inv.visit_id,
        visit_number=inv.visit.visit_number if inv.visit else None,
        patient_id=inv.patient_id, patient_name=inv.patient.full_name if inv.patient else None,
        patient_number=inv.patient.patient_number if inv.patient else None,
        doctor_id=inv.doctor_id, doctor_name=_full_name(inv.doctor) if inv.doctor else None,
        invoice_date=inv.invoice_date, status=inv.status, grand_total=inv.grand_total,
        amount_paid=inv.amount_paid, balance_due=inv.balance_due, created_at=inv.created_at,
    )


def _to_detail(inv: Invoice) -> InvoiceDetail:
    base = _to_read(inv).model_dump()
    return InvoiceDetail(
        **base,
        patient_name=inv.patient.full_name if inv.patient else None,
        patient_number=inv.patient.patient_number if inv.patient else None,
        doctor_name=_full_name(inv.doctor) if inv.doctor else None,
        visit_number=inv.visit.visit_number if inv.visit else None,
        branch_name=inv.branch.name if inv.branch else None,
        items=[InvoiceItemRead.model_validate(i, from_attributes=True) for i in inv.items],
        discounts=[DiscountRead.model_validate(d, from_attributes=True) for d in inv.discounts],
        payments=[PaymentRead.model_validate(p, from_attributes=True) for p in inv.payments],
    )


class InvoiceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = InvoiceRepository(session)
        self.visit_repo = VisitRepository(session)
        self.number_generator = InvoiceNumberGenerator(session)
        self.audit_service = AuditService(session)

    async def _require_invoice(self, invoice_id: UUID, clinic_id: UUID) -> Invoice:
        invoice = await self.repo.get_by_id(invoice_id, clinic_id)
        if invoice is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
        return invoice

    def _recompute_totals(self, invoice: Invoice) -> None:
        subtotal = sum((Decimal(str(i.unit_price)) * Decimal(str(i.quantity)) for i in invoice.items), Decimal("0"))
        item_discounts = sum((Decimal(str(i.discount_amount)) for i in invoice.items), Decimal("0"))
        invoice_discounts = sum((Decimal(str(d.amount)) for d in invoice.discounts), Decimal("0"))
        discount_total = item_discounts + invoice_discounts
        grand_total = max(subtotal - discount_total, Decimal("0"))
        amount_paid = Decimal(str(invoice.amount_paid or 0))
        invoice.subtotal = subtotal
        invoice.discount_total = discount_total
        invoice.grand_total = grand_total
        invoice.balance_due = max(grand_total - amount_paid, Decimal("0"))

    def _maybe_advance_to_pending(self, invoice: Invoice) -> None:
        if invoice.status == InvoiceStatus.DRAFT and len(invoice.items) > 0:
            invoice.status = InvoiceStatus.PENDING_PAYMENT

    # --- Auto-creation on consultation completion ---

    async def create_draft_invoice_for_consultation(
        self, *, clinic_id: UUID, visit_id: UUID, actor_id: UUID | None, fee_override: Decimal | None = None
    ) -> Invoice:
        """Idempotent: returns the existing invoice for this visit if one
        already exists (any non-cancelled status), otherwise creates a new
        Draft invoice with a single auto-priced Consultation Fee line item."""
        existing = await self.repo.get_latest_for_visit(visit_id, clinic_id)
        if existing is not None and existing.status != InvoiceStatus.CANCELLED:
            return existing

        visit = await self.visit_repo.get_with_relations(visit_id, clinic_id)
        if visit is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found")

        today = datetime.now(UTC).date()
        invoice_number = await self.number_generator.next_number(clinic_id, today)
        invoice = await self.repo.create_invoice(
            clinic_id=clinic_id, visit_id=visit_id, branch_id=visit.branch_id, patient_id=visit.patient_id,
            doctor_id=visit.doctor_id, invoice_number=invoice_number, invoice_date=today, actor_id=actor_id,
        )

        # Price precedence (Phase 20 item 9 adds the first tier): a Doctor-set
        # fee override entered AT consultation-complete time (`fee_override`,
        # threaded through from `POST /consultations/{id}/complete`'s
        # optional body) > Doctor.consultation_fee (the doctor's standing
        # per-visit default) > ClinicService.default_price > 0.
        unit_price = Decimal("0")
        description = "Consultation Fee"
        if fee_override is not None and fee_override >= 0:
            unit_price = Decimal(str(fee_override))
        if unit_price == 0 and visit.doctor_id is not None:
            doctor = await self.session.get(Doctor, visit.doctor_id)
            if doctor is not None and doctor.consultation_fee and doctor.consultation_fee > 0:
                unit_price = Decimal(str(doctor.consultation_fee))
        if unit_price == 0 and visit.service_id is not None:
            svc = await self.session.get(ClinicService, visit.service_id)
            if svc is not None:
                unit_price = Decimal(str(svc.default_price or 0))
                description = svc.service_name

        await self.repo.add_item(
            invoice.id, clinic_id, description=description, item_type=InvoiceItemType.CONSULTATION_FEE,
            quantity=Decimal("1"), unit_price=unit_price, discount_amount=Decimal("0"), line_total=unit_price,
        )
        await self.session.refresh(invoice, attribute_names=["items", "discounts", "payments"])
        self._recompute_totals(invoice)
        self._maybe_advance_to_pending(invoice)
        await self.session.flush()

        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="invoice.created", entity_type="invoice",
            entity_id=str(invoice.id), metadata={"invoice_number": invoice_number, "visit_id": str(visit_id)},
        )
        await self.session.commit()
        return await self.repo.get_by_id(invoice.id, clinic_id)

    async def create_draft_invoice_for_laboratory_visit(
        self, *, clinic_id: UUID, visit_id: UUID, actor_id: UUID | None
    ) -> Invoice:
        """Laboratory pay-first workflow: the invoice for a walk-in
        Laboratory ticket, created against the draft Visit
        (`VisitService.create_draft_visit_for_pre_queue`) BEFORE any Queue
        ticket exists, so the receptionist can collect payment first (see
        `QueueService._create_queue_for_paid_lab_visit`, the payment-gated
        counterpart to `_create_queue_for_draft_visit`).

        Deliberately a separate method from `create_draft_invoice_for_consultation`
        rather than a generalization of it: that method's pricing precedence
        (Doctor.consultation_fee override, always item_type=ConsultationFee)
        is consultation-specific and already covered by its own tests/callers
        - duplicating its small bootstrap (invoice number, Draft row) here is
        safer than reshaping a heavily-depended-on method for a second use
        case.

        Idempotent: returns the existing non-cancelled invoice for this visit
        if one already exists, exactly like `create_draft_invoice_for_consultation`
        - a retried "prepare payment" call never creates a duplicate invoice.

        Zero-priced services: if the resolved `ClinicService.default_price`
        is 0 (unset), the single Laboratory line item is still added (so the
        invoice/receipt reflects what was ordered), but the invoice is
        advanced straight to `Paid` with zero owed - there is nothing to
        collect, and requiring a $0 payment record would just be busywork.
        A clinic that wants payment enforcement for a given lab test should
        price that service in the catalog.
        """
        existing = await self.repo.get_latest_for_visit(visit_id, clinic_id)
        if existing is not None and existing.status != InvoiceStatus.CANCELLED:
            return existing

        visit = await self.visit_repo.get_with_relations(visit_id, clinic_id)
        if visit is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found")
        if visit.service_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Visit has no service to invoice.")

        service = await self.session.get(ClinicService, visit.service_id)
        if service is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
        unit_price = Decimal(str(service.default_price or 0))

        today = datetime.now(UTC).date()
        invoice_number = await self.number_generator.next_number(clinic_id, today)
        invoice = await self.repo.create_invoice(
            clinic_id=clinic_id, visit_id=visit_id, branch_id=visit.branch_id, patient_id=visit.patient_id,
            doctor_id=visit.doctor_id, invoice_number=invoice_number, invoice_date=today, actor_id=actor_id,
        )
        await self.repo.add_item(
            invoice.id, clinic_id, description=service.service_name, item_type=InvoiceItemType.LABORATORY,
            quantity=Decimal("1"), unit_price=unit_price, discount_amount=Decimal("0"), line_total=unit_price,
        )
        await self.session.refresh(invoice, attribute_names=["items", "discounts", "payments"])
        self._recompute_totals(invoice)
        self._maybe_advance_to_pending(invoice)
        if invoice.grand_total == 0:
            invoice.status = InvoiceStatus.PAID
        await self.session.flush()

        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="invoice.created", entity_type="invoice",
            entity_id=str(invoice.id), metadata={"invoice_number": invoice_number, "visit_id": str(visit_id), "source": "laboratory_pay_first"},
        )
        await self.session.commit()
        return await self.repo.get_by_id(invoice.id, clinic_id)

    async def create_laboratory_invoice_for_visit_endpoint(
        self, visit_id: UUID, *, clinic_id: UUID, actor_id: UUID | None
    ) -> InvoiceDetail:
        """`POST /visits/{visit_id}/laboratory-invoice` - thin wrapper
        returning the full detail shape the frontend's payment step needs
        (items/payments), matching `create_invoice_for_consultation_endpoint`'s
        own wrapper convention below."""
        invoice = await self.create_draft_invoice_for_laboratory_visit(
            clinic_id=clinic_id, visit_id=visit_id, actor_id=actor_id
        )
        return _to_detail(await self.repo.get_by_id(invoice.id, clinic_id))

    async def create_invoice_for_consultation_endpoint(self, consultation_id: UUID, *, clinic_id: UUID, actor_id: UUID | None) -> InvoiceDetail:
        """Mostly-internal/test trigger endpoint - resolves the visit from the
        consultation then delegates to the same auto-creation path used by
        `ConsultationService.complete_consultation()`."""
        from app.repositories.consultation_repository import ConsultationRepository

        consultation = await ConsultationRepository(self.session).get_by_id(consultation_id, clinic_id)
        if consultation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")
        invoice = await self.create_draft_invoice_for_consultation(
            clinic_id=clinic_id, visit_id=consultation.visit_id, actor_id=actor_id
        )
        return _to_detail(invoice)

    # --- Items ---

    def _require_editable(self, invoice: Invoice) -> None:
        if invoice.status in NON_EDITABLE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot edit invoice items once the invoice is {invoice.status.value}.",
            )

    async def add_item(self, invoice_id: UUID, payload: dict, *, clinic_id: UUID, actor_id: UUID | None) -> InvoiceDetail:
        invoice = await self._require_invoice(invoice_id, clinic_id)
        self._require_editable(invoice)
        unit_price = Decimal(str(payload["unit_price"]))
        quantity = Decimal(str(payload["quantity"]))
        discount_amount = Decimal(str(payload.get("discount_amount") or 0))
        line_total = max(unit_price * quantity - discount_amount, Decimal("0"))
        await self.repo.add_item(
            invoice_id, clinic_id, description=payload["description"], item_type=payload["item_type"],
            quantity=quantity, unit_price=unit_price, discount_amount=discount_amount,
            tax_amount=payload.get("tax_amount"), line_total=line_total, notes=payload.get("notes"),
        )
        await self.session.refresh(invoice, attribute_names=["items", "discounts", "payments"])
        self._recompute_totals(invoice)
        self._maybe_advance_to_pending(invoice)
        invoice.updated_by = actor_id
        await self.session.flush()
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="invoice.edited", entity_type="invoice", entity_id=str(invoice_id),
            metadata={"change": "item_added"},
        )
        await self.session.commit()
        return _to_detail(await self.repo.get_by_id(invoice_id, clinic_id))

    async def update_item(self, invoice_id: UUID, item_id: UUID, payload: dict, *, clinic_id: UUID, actor_id: UUID | None) -> InvoiceDetail:
        invoice = await self._require_invoice(invoice_id, clinic_id)
        self._require_editable(invoice)
        item = await self.repo.get_item(item_id, invoice_id, clinic_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice item not found")
        updates = {k: v for k, v in payload.items() if v is not None}
        for k, v in list(updates.items()):
            if k in {"quantity", "unit_price", "discount_amount", "tax_amount"}:
                updates[k] = Decimal(str(v))
        await self.repo.update_item(item, **updates)
        new_qty = Decimal(str(item.quantity))
        new_price = Decimal(str(item.unit_price))
        new_disc = Decimal(str(item.discount_amount))
        item.line_total = max(new_qty * new_price - new_disc, Decimal("0"))
        await self.session.flush()
        await self.session.refresh(invoice, attribute_names=["items", "discounts", "payments"])
        self._recompute_totals(invoice)
        invoice.updated_by = actor_id
        await self.session.flush()
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="invoice.edited", entity_type="invoice", entity_id=str(invoice_id),
            metadata={"change": "item_updated", "item_id": str(item_id)},
        )
        await self.session.commit()
        return _to_detail(await self.repo.get_by_id(invoice_id, clinic_id))

    async def remove_item(self, invoice_id: UUID, item_id: UUID, *, clinic_id: UUID, actor_id: UUID | None) -> InvoiceDetail:
        invoice = await self._require_invoice(invoice_id, clinic_id)
        self._require_editable(invoice)
        item = await self.repo.get_item(item_id, invoice_id, clinic_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice item not found")
        await self.repo.delete_item(item)
        await self.session.refresh(invoice, attribute_names=["items", "discounts", "payments"])
        self._recompute_totals(invoice)
        if len(invoice.items) == 0 and invoice.status == InvoiceStatus.PENDING_PAYMENT:
            invoice.status = InvoiceStatus.DRAFT
        invoice.updated_by = actor_id
        await self.session.flush()
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="invoice.edited", entity_type="invoice", entity_id=str(invoice_id),
            metadata={"change": "item_removed", "item_id": str(item_id)},
        )
        await self.session.commit()
        return _to_detail(await self.repo.get_by_id(invoice_id, clinic_id))

    # --- Discounts ---

    async def apply_discount(self, invoice_id: UUID, payload: dict, *, clinic_id: UUID, actor_id: UUID | None) -> InvoiceDetail:
        invoice = await self._require_invoice(invoice_id, clinic_id)
        self._require_editable(invoice)
        value = Decimal(str(payload["value"]))
        calc_type = payload["calculation_type"]
        subtotal_now = sum((Decimal(str(i.unit_price)) * Decimal(str(i.quantity)) for i in invoice.items), Decimal("0"))
        if calc_type.value == "Percentage":
            amount = (subtotal_now * value / Decimal("100")).quantize(Decimal("0.01"))
        else:
            amount = value
        await self.repo.add_discount(
            invoice_id, clinic_id, discount_type=payload["discount_type"], calculation_type=calc_type,
            value=value, amount=amount, reason=payload.get("reason"), approved_by=actor_id,
        )
        await self.session.refresh(invoice, attribute_names=["items", "discounts", "payments"])
        self._recompute_totals(invoice)
        invoice.updated_by = actor_id
        await self.session.flush()
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="invoice.discount_applied", entity_type="invoice",
            entity_id=str(invoice_id),
            metadata={
                "discount_type": payload["discount_type"].value,
                "amount": str(amount),
                "reason": payload.get("reason"),
            },
        )
        await self.session.commit()
        return _to_detail(await self.repo.get_by_id(invoice_id, clinic_id))

    async def remove_discount(self, invoice_id: UUID, discount_id: UUID, *, clinic_id: UUID, actor_id: UUID | None) -> InvoiceDetail:
        invoice = await self._require_invoice(invoice_id, clinic_id)
        self._require_editable(invoice)
        discount = await self.repo.get_discount(discount_id, invoice_id, clinic_id)
        if discount is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discount not found")
        removed_amount = str(discount.amount)
        removed_type = discount.discount_type.value if hasattr(discount.discount_type, "value") else discount.discount_type
        removed_reason = discount.reason
        await self.repo.delete_discount(discount)
        await self.session.refresh(invoice, attribute_names=["items", "discounts", "payments"])
        self._recompute_totals(invoice)
        invoice.updated_by = actor_id
        await self.session.flush()
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="invoice.discount_removed", entity_type="invoice",
            entity_id=str(invoice_id),
            metadata={
                "discount_id": str(discount_id),
                "discount_type": removed_type,
                "amount": removed_amount,
                "reason": removed_reason,
            },
        )
        await self.session.commit()
        return _to_detail(await self.repo.get_by_id(invoice_id, clinic_id))

    # --- Reads ---

    async def get_invoice(self, invoice_id: UUID, *, clinic_id: UUID) -> InvoiceDetail:
        invoice = await self._require_invoice(invoice_id, clinic_id)
        return _to_detail(invoice)

    async def get_invoice_for_visit(self, visit_id: UUID, *, clinic_id: UUID) -> InvoiceDetail | None:
        invoice = await self.repo.get_latest_for_visit(visit_id, clinic_id)
        return _to_detail(invoice) if invoice else None

    async def list_invoices(self, *, clinic_id: UUID, params) -> tuple[list[InvoiceListItem], int]:
        rows, total = await self.repo.search(clinic_id, params)
        return [_to_list_item(r) for r in rows], total

    async def get_billing_history_for_patient(self, *, clinic_id: UUID, patient_id: UUID, limit: int = 50, offset: int = 0) -> tuple[list[BillingHistoryItem], int]:
        rows, total = await self.repo.list_for_patient(clinic_id, patient_id, limit=limit, offset=offset)
        items = [
            BillingHistoryItem(
                id=r.id, invoice_number=r.invoice_number, invoice_date=r.invoice_date, grand_total=r.grand_total,
                status=r.status, visit_id=r.visit_id, visit_number=r.visit.visit_number if r.visit else None,
            )
            for r in rows
        ]
        return items, total
