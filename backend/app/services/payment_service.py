"""Payment service (Phase 9 - Billing & Cashier).

Payment -> Visit sync design decision (Phase 7/8 lesson applied): when a
payment (or the last of a split-payment set) brings an invoice's
`amount_paid >= grand_total`, the invoice transitions to `Paid`, and this
service then calls `VisitService.change_status(..., VisitStatus.COMPLETED)`
if the linked Visit is not already `Completed`/terminal - this is the
"Visit Closed" terminal step of the spec's workflow diagram
("Consultation -> Billing -> Payment -> Receipt -> Visit Closed"). In
practice the Visit is normally already `Completed` by the time billing
happens (Phase 8's Consultation->Visit sync already closes it), so this is
usually a no-op; it only has a real effect for the edge case where payment
completes before/without that earlier sync running, and - mirroring
`ConsultationService._sync_queue_status`'s tolerance - it never raises if
the transition isn't legal (e.g. Visit already Cancelled), it just skips it.

Void-payment: recomputes `amount_paid`/`balance_due`/`status` backward from
the remaining Completed payments (not just decrementing), so voiding is safe
even if multiple payments/voids happen out of order.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment import Payment, PaymentStatus
from app.models.visit import VISIT_STATUS_TRANSITIONS, VisitStatus
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.visit_repository import VisitRepository
from app.schemas.billing import InvoiceDetail
from app.services.audit_service import AuditService
from app.services.invoice_service import _to_detail
from app.services.shift_service import enforce_receptionist_open_shift
from app.services.visit_service import VisitService


class PaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = InvoiceRepository(session)
        self.visit_repo = VisitRepository(session)
        self.visit_service = VisitService(session)
        self.audit_service = AuditService(session)

    async def _require_invoice(self, invoice_id: UUID, clinic_id: UUID) -> Invoice:
        invoice = await self.repo.get_by_id(invoice_id, clinic_id)
        if invoice is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
        return invoice

    def _recompute_amount_paid(self, invoice: Invoice) -> None:
        paid = sum(
            (Decimal(str(p.amount)) for p in invoice.payments if p.status == PaymentStatus.COMPLETED), Decimal("0")
        )
        invoice.amount_paid = paid
        invoice.balance_due = max(Decimal(str(invoice.grand_total)) - paid, Decimal("0"))
        if paid <= 0:
            if invoice.status in (InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID):
                invoice.status = InvoiceStatus.PENDING_PAYMENT
        elif paid < Decimal(str(invoice.grand_total)):
            invoice.status = InvoiceStatus.PARTIALLY_PAID
        else:
            invoice.status = InvoiceStatus.PAID

    async def _sync_visit_on_paid(self, invoice: Invoice, *, actor_id: UUID | None) -> None:
        visit = await self.visit_repo.get_by_id_and_clinic(invoice.visit_id, invoice.clinic_id)
        if visit is None or visit.status == VisitStatus.COMPLETED:
            return
        if VisitStatus.COMPLETED in VISIT_STATUS_TRANSITIONS.get(visit.status, set()):
            await self.visit_service.change_status(
                invoice.visit_id, clinic_id=invoice.clinic_id, actor_id=actor_id,
                new_status=VisitStatus.COMPLETED, note="Invoice paid in full",
            )
        # else: Visit is in a state where Completed isn't legal (e.g.
        # already Cancelled) - don't force an illegal transition, mirroring
        # the tolerant pattern from ConsultationService._sync_queue_status.

    async def record_payment(
        self, invoice_id: UUID, payments: list[dict], *, clinic_id: UUID, actor_id: UUID
    ) -> InvoiceDetail:
        # Item 7 (Shift Enforcement): checked before touching the invoice at
        # all, so a blocked Receptionist never creates a partial payment
        # record.
        await enforce_receptionist_open_shift(self.session, clinic_id=clinic_id, actor_id=actor_id)

        invoice = await self._require_invoice(invoice_id, clinic_id)
        if invoice.status in (InvoiceStatus.DRAFT, InvoiceStatus.CANCELLED):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot record a payment against a {invoice.status.value} invoice.",
            )
        total_new = sum((Decimal(str(p["amount"])) for p in payments), Decimal("0"))
        current_balance = Decimal(str(invoice.balance_due))
        if total_new > current_balance:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Payment amount ({total_new}) exceeds the remaining balance ({current_balance}).",
            )
        now = datetime.now(UTC)
        for p in payments:
            await self.repo.add_payment(
                invoice_id, clinic_id, payment_method=p["payment_method"], amount=Decimal(str(p["amount"])),
                reference_number=p.get("reference_number"), status=PaymentStatus.COMPLETED,
                received_by=actor_id, paid_at=now,
            )
        await self.session.refresh(invoice, attribute_names=["payments"])
        self._recompute_amount_paid(invoice)
        invoice.updated_by = actor_id
        await self.session.flush()

        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="invoice.payment_received", entity_type="invoice",
            entity_id=str(invoice_id), metadata={"amount": str(total_new), "count": len(payments)},
        )

        if invoice.status == InvoiceStatus.PAID:
            await self._sync_visit_on_paid(invoice, actor_id=actor_id)

        await self.session.commit()
        return _to_detail(await self.repo.get_by_id(invoice_id, clinic_id))

    async def void_payment(self, payment_id: UUID, *, clinic_id: UUID, actor_id: UUID) -> InvoiceDetail:
        payment = await self.repo.get_payment(payment_id, clinic_id)
        if payment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
        if payment.status == PaymentStatus.VOIDED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment is already voided.")

        invoice = await self._require_invoice(payment.invoice_id, clinic_id)
        payment.status = PaymentStatus.VOIDED
        payment.voided_at = datetime.now(UTC)
        payment.voided_by = actor_id
        await self.session.flush()
        await self.session.refresh(invoice, attribute_names=["payments"])
        self._recompute_amount_paid(invoice)
        invoice.updated_by = actor_id
        await self.session.flush()

        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="invoice.payment_voided", entity_type="invoice",
            entity_id=str(invoice.id), metadata={"payment_id": str(payment_id)},
        )
        await self.session.commit()
        return _to_detail(await self.repo.get_by_id(invoice.id, clinic_id))

    # --- Refund (architecture-only per spec: model + stub, no UI/workflow) ---

    async def create_refund(self, payment_id: UUID, *, clinic_id: UUID, amount: Decimal, reason: str | None, actor_id: UUID) -> dict:
        from app.models.payment import Refund

        payment = await self.repo.get_payment(payment_id, clinic_id)
        if payment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
        refund = Refund(clinic_id=clinic_id, payment_id=payment_id, amount=amount, reason=reason, status="Pending")
        self.session.add(refund)
        await self.session.flush()
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="refund.requested", entity_type="refund", entity_id=str(refund.id),
        )
        await self.session.commit()
        return {"id": refund.id, "status": refund.status, "amount": refund.amount}

    async def approve_refund(self, refund_id: UUID, *, clinic_id: UUID, actor_id: UUID) -> dict:
        from app.models.payment import Refund

        refund = await self.session.get(Refund, refund_id)
        if refund is None or refund.clinic_id != clinic_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refund not found")
        refund.status = "Approved"
        refund.approved_by = actor_id
        await self.session.flush()
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="refund.approved", entity_type="refund", entity_id=str(refund.id),
        )
        await self.session.commit()
        return {"id": refund.id, "status": refund.status}
