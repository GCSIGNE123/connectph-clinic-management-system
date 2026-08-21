"""Pydantic schemas for Billing & Cashier (Phase 9)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.discount import DiscountCalculationType, DiscountType
from app.models.invoice import InvoiceStatus
from app.models.invoice_item import InvoiceItemType
from app.models.payment import PaymentMethod, PaymentStatus


class LaboratoryInvoiceCreate(BaseModel):
    """Body for `POST /visits/{visit_id}/laboratory-invoice` (Multi-Service
    Laboratory Pay-First). `service_ids` is optional and defaults to `None`
    - an omitted/empty body preserves the original single-service behavior
    (`InvoiceService.create_draft_invoice_for_laboratory_visit` falls back
    to the draft Visit's own `service_id`), so every existing caller/test
    that posts no body keeps working unchanged. When provided, one
    Laboratory line item is created per service id, in the given order."""

    service_ids: list[UUID] | None = None

    @field_validator("service_ids")
    @classmethod
    def _no_duplicate_services(cls, value: list[UUID] | None) -> list[UUID] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("Duplicate Laboratory service selected.")
        return value


# --- Invoice items ---

class InvoiceItemCreate(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    item_type: InvoiceItemType = InvoiceItemType.CUSTOM
    quantity: Decimal = Decimal("1")
    unit_price: Decimal = Decimal("0")
    discount_amount: Decimal = Decimal("0")
    tax_amount: Decimal | None = None
    notes: str | None = None


class InvoiceItemUpdate(BaseModel):
    description: str | None = None
    item_type: InvoiceItemType | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    discount_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    notes: str | None = None


class InvoiceItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_id: UUID
    description: str
    item_type: InvoiceItemType
    quantity: Decimal
    unit_price: Decimal
    discount_amount: Decimal
    tax_amount: Decimal | None
    line_total: Decimal
    notes: str | None


# --- Discounts ---

class DiscountApply(BaseModel):
    discount_type: DiscountType
    calculation_type: DiscountCalculationType
    value: Decimal = Field(gt=0)
    reason: str | None = None


class DiscountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_id: UUID
    discount_type: DiscountType
    calculation_type: DiscountCalculationType
    value: Decimal
    amount: Decimal
    reason: str | None
    approved_by: UUID | None
    created_at: datetime


# --- Payments ---

class PaymentCreate(BaseModel):
    payment_method: PaymentMethod
    amount: Decimal = Field(gt=0)
    reference_number: str | None = None


class SplitPaymentCreate(BaseModel):
    payments: list[PaymentCreate] = Field(min_length=1)


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_id: UUID
    payment_method: PaymentMethod
    amount: Decimal
    reference_number: str | None
    status: PaymentStatus
    received_by: UUID | None
    received_by_name: str | None = None
    paid_at: datetime
    voided_at: datetime | None
    voided_by: UUID | None


# --- Invoice ---

class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_number: str
    visit_id: UUID
    clinic_id: UUID
    branch_id: UUID
    patient_id: UUID
    doctor_id: UUID | None
    invoice_date: date
    status: InvoiceStatus
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal | None
    grand_total: Decimal
    amount_paid: Decimal
    balance_due: Decimal
    created_at: datetime
    updated_at: datetime


class InvoiceDetail(InvoiceRead):
    patient_name: str | None = None
    patient_number: str | None = None
    doctor_name: str | None = None
    visit_number: str | None = None
    branch_name: str | None = None
    items: list[InvoiceItemRead] = []
    discounts: list[DiscountRead] = []
    payments: list[PaymentRead] = []


class InvoiceListItem(BaseModel):
    id: UUID
    invoice_number: str
    visit_id: UUID
    visit_number: str | None = None
    patient_id: UUID
    patient_name: str | None = None
    patient_number: str | None = None
    doctor_id: UUID | None
    doctor_name: str | None = None
    invoice_date: date
    status: InvoiceStatus
    grand_total: Decimal
    amount_paid: Decimal
    balance_due: Decimal
    created_at: datetime


class InvoiceSearchParams(BaseModel):
    q: str | None = None
    status: InvoiceStatus | None = None
    date_from: date | None = None
    date_to: date | None = None
    cashier_id: UUID | None = None
    limit: int = 20
    offset: int = 0


class InvoiceListResponse(BaseModel):
    items: list[InvoiceListItem]
    total: int


# --- Receipt ---

class ReceiptItemLine(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


class ReceiptPayload(BaseModel):
    invoice_id: UUID
    invoice_number: str
    receipt_number: str
    clinic_name: str
    branch_name: str | None = None
    patient_name: str | None = None
    visit_number: str | None = None
    cashier_name: str | None = None
    printed_at: datetime
    items: list[ReceiptItemLine]
    discounts: list[DiscountRead]
    subtotal: Decimal
    discount_total: Decimal
    grand_total: Decimal
    amount_paid: Decimal
    balance_due: Decimal
    payments: list[PaymentRead]


# --- Cashier dashboard ---

class RecentPayment(BaseModel):
    id: UUID
    invoice_number: str
    patient_name: str | None
    amount: Decimal
    payment_method: PaymentMethod
    paid_at: datetime


class CashierDashboard(BaseModel):
    pending_payments: int
    paid_today: int
    todays_revenue: Decimal
    outstanding_balance: Decimal
    refunds_pending: int
    recent_payments: list[RecentPayment]


class BillingHistoryItem(BaseModel):
    id: UUID
    invoice_number: str
    invoice_date: date
    grand_total: Decimal
    status: InvoiceStatus
    visit_id: UUID
    visit_number: str | None = None
