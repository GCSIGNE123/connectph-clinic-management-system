"""Billing & Cashier endpoints (Phase 9, revised Phase 20).

Role gating (see `core/dependencies.py`): Cashier/Owner/Administrator can
create/edit invoice items and void payments. Administrator (and Owner) only
for refund approval. Doctor gets view-only.

Phase 20 (Client Acceptance Revisions, items 1/2): Receptionist can now also
apply discounts and record payments (previously read-only for Billing) -
this was a deliberate, client-requested permission change, not merely a bug
fix. Receptionist still cannot void a payment or approve a refund - those
remain restricted to Cashier/Owner/Administrator and Owner/Administrator
respectively.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_db,
    require_billing_discount_role,
    require_billing_manage_role,
    require_billing_payment_record_role,
    require_billing_refund_role,
    require_billing_view_role,
    require_billing_void_role,
    require_clinic_context,
)
from app.models.clinic import Clinic
from app.models.user import User
from app.repositories.invoice_repository import InvoiceRepository
from app.schemas.billing import (
    BillingHistoryItem,
    CashierDashboard,
    DiscountApply,
    InvoiceDetail,
    InvoiceItemCreate,
    InvoiceItemUpdate,
    InvoiceListResponse,
    InvoiceSearchParams,
    LaboratoryInvoiceCreate,
    PaymentCreate,
    ReceiptPayload,
    RecentPayment,
    SplitPaymentCreate,
)
from app.services.invoice_service import InvoiceService
from app.services.payment_service import PaymentService
from app.services.receipt_service import ReceiptService

router = APIRouter(tags=["billing"])


# --- Invoice creation (internal/test trigger - real trigger is consultation completion) ---

@router.post("/consultations/{consultation_id}/invoice", response_model=InvoiceDetail)
async def create_invoice_for_consultation(
    consultation_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_billing_manage_role),
) -> InvoiceDetail:
    service = InvoiceService(db)
    return await service.create_invoice_for_consultation_endpoint(consultation_id, clinic_id=clinic_id, actor_id=current_user.id)


# --- Invoices ---

@router.get("/invoices", response_model=InvoiceListResponse)
async def list_invoices(
    q: str | None = None,
    status_: str | None = Query(default=None, alias="status"),
    date_from: date | None = None,
    date_to: date | None = None,
    cashier_id: UUID | None = None,
    limit: int = 20,
    offset: int = 0,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_billing_view_role),
) -> InvoiceListResponse:
    from app.models.invoice import InvoiceStatus

    params = InvoiceSearchParams(
        q=q, status=InvoiceStatus(status_) if status_ else None, date_from=date_from, date_to=date_to,
        cashier_id=cashier_id, limit=limit, offset=offset,
    )
    service = InvoiceService(db)
    items, total = await service.list_invoices(clinic_id=clinic_id, params=params)
    return InvoiceListResponse(items=items, total=total)


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetail)
async def get_invoice(
    invoice_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_billing_view_role),
) -> InvoiceDetail:
    service = InvoiceService(db)
    return await service.get_invoice(invoice_id, clinic_id=clinic_id)


@router.get("/visits/{visit_id}/invoice", response_model=InvoiceDetail | None)
async def get_invoice_for_visit(
    visit_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_billing_view_role),
) -> InvoiceDetail | None:
    service = InvoiceService(db)
    return await service.get_invoice_for_visit(visit_id, clinic_id=clinic_id)


@router.post("/visits/{visit_id}/laboratory-invoice", response_model=InvoiceDetail)
async def create_laboratory_invoice_for_visit(
    visit_id: UUID,
    payload: LaboratoryInvoiceCreate | None = None,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_billing_payment_record_role),
) -> InvoiceDetail:
    """Laboratory pay-first workflow (Reception): creates (or returns the
    existing) invoice for a draft Laboratory Visit created via
    `POST /visits/pre-queue`, so it can be paid via the existing
    `POST /invoices/{invoice_id}/payments` before the Queue ticket is
    raised via `POST /queues`. Gated on `require_billing_payment_record_role`
    (Owner/Administrator/Cashier/Receptionist) rather than the stricter
    `require_billing_manage_role` (no Receptionist) - a Receptionist is the
    one who runs this walk-in flow at the counter, and this endpoint only
    ever creates system-priced Laboratory line items, not arbitrary invoice
    editing.

    Multi-Service Laboratory Pay-First: an optional body
    `{"service_ids": [...]}"` creates one Laboratory line item per service
    (in that order) instead of the single line item derived from the draft
    Visit's own `service_id`. Omitting the body (or `service_ids`) preserves
    the original single-service behavior exactly."""
    service = InvoiceService(db)
    service_ids = payload.service_ids if payload is not None else None
    return await service.create_laboratory_invoice_for_visit_endpoint(
        visit_id, clinic_id=clinic_id, actor_id=current_user.id, service_ids=service_ids
    )


@router.get("/patients/{patient_id}/billing-history")
async def get_billing_history(
    patient_id: UUID,
    limit: int = 50,
    offset: int = 0,
    date_from: date | None = None,
    date_to: date | None = None,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_billing_view_role),
):
    service = InvoiceService(db)
    items, total = await service.get_billing_history_for_patient(
        clinic_id=clinic_id, patient_id=patient_id, limit=limit, offset=offset, date_from=date_from, date_to=date_to
    )
    return {"items": items, "total": total}


# --- Invoice items ---

@router.post("/invoices/{invoice_id}/items", response_model=InvoiceDetail)
async def add_invoice_item(
    invoice_id: UUID,
    payload: InvoiceItemCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_billing_manage_role),
) -> InvoiceDetail:
    service = InvoiceService(db)
    return await service.add_item(invoice_id, payload.model_dump(), clinic_id=clinic_id, actor_id=current_user.id)


@router.patch("/invoices/{invoice_id}/items/{item_id}", response_model=InvoiceDetail)
async def update_invoice_item(
    invoice_id: UUID,
    item_id: UUID,
    payload: InvoiceItemUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_billing_manage_role),
) -> InvoiceDetail:
    service = InvoiceService(db)
    return await service.update_item(invoice_id, item_id, payload.model_dump(exclude_unset=True), clinic_id=clinic_id, actor_id=current_user.id)


@router.delete("/invoices/{invoice_id}/items/{item_id}", response_model=InvoiceDetail)
async def remove_invoice_item(
    invoice_id: UUID,
    item_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_billing_manage_role),
) -> InvoiceDetail:
    service = InvoiceService(db)
    return await service.remove_item(invoice_id, item_id, clinic_id=clinic_id, actor_id=current_user.id)


# --- Discounts ---

@router.post("/invoices/{invoice_id}/discounts", response_model=InvoiceDetail)
async def apply_discount(
    invoice_id: UUID,
    payload: DiscountApply,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_billing_discount_role),
) -> InvoiceDetail:
    service = InvoiceService(db)
    return await service.apply_discount(invoice_id, payload.model_dump(), clinic_id=clinic_id, actor_id=current_user.id)


@router.delete("/invoices/{invoice_id}/discounts/{discount_id}", response_model=InvoiceDetail)
async def remove_discount(
    invoice_id: UUID,
    discount_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_billing_discount_role),
) -> InvoiceDetail:
    service = InvoiceService(db)
    return await service.remove_discount(invoice_id, discount_id, clinic_id=clinic_id, actor_id=current_user.id)


# --- Payments ---

@router.post("/invoices/{invoice_id}/payments", response_model=InvoiceDetail)
async def record_payment(
    invoice_id: UUID,
    payload: SplitPaymentCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_billing_payment_record_role),
) -> InvoiceDetail:
    service = PaymentService(db)
    return await service.record_payment(
        invoice_id, [p.model_dump() for p in payload.payments], clinic_id=clinic_id, actor_id=current_user.id
    )


@router.post("/payments/{payment_id}/void", response_model=InvoiceDetail)
async def void_payment(
    payment_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_billing_void_role),
) -> InvoiceDetail:
    service = PaymentService(db)
    return await service.void_payment(payment_id, clinic_id=clinic_id, actor_id=current_user.id)


# --- Refunds (Administrator/Owner only - architecture only, no UI) ---

@router.post("/payments/{payment_id}/refund")
async def create_refund(
    payment_id: UUID,
    amount: Decimal,
    reason: str | None = None,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_billing_refund_role),
):
    service = PaymentService(db)
    return await service.create_refund(payment_id, clinic_id=clinic_id, amount=amount, reason=reason, actor_id=current_user.id)


@router.post("/refunds/{refund_id}/approve")
async def approve_refund(
    refund_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_billing_refund_role),
):
    service = PaymentService(db)
    return await service.approve_refund(refund_id, clinic_id=clinic_id, actor_id=current_user.id)


# --- Receipt ---

@router.get("/invoices/{invoice_id}/receipt", response_model=ReceiptPayload)
async def get_receipt(
    invoice_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_billing_view_role),
) -> ReceiptPayload:
    clinic = await db.get(Clinic, clinic_id)
    service = ReceiptService(db)
    return await service.build_receipt_payload(invoice_id, clinic_id=clinic_id, clinic_name=clinic.name if clinic else "Clinic")


@router.post("/invoices/{invoice_id}/receipt/print", response_model=ReceiptPayload)
async def print_receipt(
    invoice_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_billing_view_role),
) -> ReceiptPayload:
    clinic = await db.get(Clinic, clinic_id)
    service = ReceiptService(db)
    payload = await service.build_receipt_payload(invoice_id, clinic_id=clinic_id, clinic_name=clinic.name if clinic else "Clinic")
    await service.record_print(invoice_id, clinic_id=clinic_id, actor_id=current_user.id)
    return payload


# --- Cashier dashboard ---

@router.get("/billing/dashboard", response_model=CashierDashboard)
async def cashier_dashboard(
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_billing_view_role),
) -> CashierDashboard:
    repo = InvoiceRepository(db)
    now = datetime.now(UTC)
    day_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
    day_end = day_start + timedelta(days=1)

    pending = await repo.count_pending_payments(clinic_id)
    paid_today = await repo.count_paid_today(clinic_id, day_start, day_end)
    revenue_today = await repo.sum_todays_revenue(clinic_id, day_start, day_end)
    outstanding = await repo.sum_outstanding_balance(clinic_id)
    refunds_pending = await repo.count_pending_refunds(clinic_id)
    recent = await repo.recent_payments(clinic_id, limit=10)

    return CashierDashboard(
        pending_payments=pending,
        paid_today=paid_today,
        todays_revenue=revenue_today,
        outstanding_balance=outstanding,
        refunds_pending=refunds_pending,
        recent_payments=[
            RecentPayment(
                id=p.id, invoice_number=p.invoice.invoice_number if p.invoice else "",
                patient_name=p.invoice.patient.full_name if p.invoice and p.invoice.patient else None,
                amount=p.amount, payment_method=p.payment_method, paid_at=p.paid_at,
            )
            for p in recent
        ],
    )
