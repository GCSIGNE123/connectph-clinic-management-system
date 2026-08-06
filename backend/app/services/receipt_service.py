"""Receipt generation (Phase 9 - Billing & Cashier).

Design decision: no persisted `receipts` table - a receipt is a computed,
printable projection of an invoice + its payments, generated on demand by
`build_receipt_payload()`. `receipt_number` is derived deterministically
from the invoice number (`invoice_number` + `-R1`) rather than backed by its
own counter, since a receipt always corresponds 1:1 to "the current paid
state of this invoice" and doesn't need independent identity/history beyond
what the invoice + `audit_logs` "Receipt Printed" entries already provide.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.invoice_repository import InvoiceRepository
from app.schemas.billing import DiscountRead, PaymentRead, ReceiptItemLine, ReceiptPayload
from app.services.audit_service import AuditService


class ReceiptService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = InvoiceRepository(session)
        self.audit_service = AuditService(session)

    async def build_receipt_payload(self, invoice_id: UUID, *, clinic_id: UUID, clinic_name: str) -> ReceiptPayload:
        invoice = await self.repo.get_by_id(invoice_id, clinic_id)
        if invoice is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

        return ReceiptPayload(
            invoice_id=invoice.id,
            invoice_number=invoice.invoice_number,
            receipt_number=f"{invoice.invoice_number}-R1",
            clinic_name=clinic_name,
            branch_name=invoice.branch.name if invoice.branch else None,
            patient_name=invoice.patient.full_name if invoice.patient else None,
            visit_number=invoice.visit.visit_number if invoice.visit else None,
            cashier_name=None,
            printed_at=datetime.now(UTC),
            items=[
                ReceiptItemLine(description=i.description, quantity=i.quantity, unit_price=i.unit_price, line_total=i.line_total)
                for i in invoice.items
            ],
            discounts=[DiscountRead.model_validate(d, from_attributes=True) for d in invoice.discounts],
            subtotal=invoice.subtotal,
            discount_total=invoice.discount_total,
            grand_total=invoice.grand_total,
            amount_paid=invoice.amount_paid,
            balance_due=invoice.balance_due,
            payments=[PaymentRead.model_validate(p, from_attributes=True) for p in invoice.payments],
        )

    async def record_print(self, invoice_id: UUID, *, clinic_id: UUID, actor_id: UUID) -> None:
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="invoice.receipt_printed", entity_type="invoice",
            entity_id=str(invoice_id),
        )
        await self.session.commit()
