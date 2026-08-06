"""Invoice model (Phase 9 - Billing & Cashier).

`Invoice` sits on top of `Visit`/`Consultation` the same way `Visit` sits on
top of `Queue` and `Consultation` sits on top of `Visit`. Per the product's
workflow diagram ("Doctor marks Consultation Complete -> Billing Draft
automatically created"), a Draft invoice is created automatically by
`InvoiceService.create_draft_invoice_for_consultation()`, called from
`ConsultationService.complete_consultation()` - see that service's docstring
for the exact sync pattern being mirrored.

Consultation -> Invoice sync decision: on consultation completion, a Draft
invoice is created (idempotent - if one already exists for the visit, it is
reused, not duplicated) with a single Consultation Fee line item priced from
`Doctor.consultation_fee` if set, else the `services` catalog row matching
the visit's `service_id` (`ClinicService.default_price`), else a zero-priced
placeholder line the cashier can edit. The invoice starts `Draft` and flips
to `PendingPayment` once it has at least one item (see
`InvoiceService.create_draft_invoice_for_consultation`).

Payment -> Visit sync decision: when an invoice transitions to `Paid` (see
`PaymentService.record_payment`), the linked Visit is transitioned to
`VisitStatus.COMPLETED` if it is not already terminal - this is the "Visit
Closed" terminal step of the spec's workflow diagram
("... -> Payment -> Receipt -> Visit Closed"). Since Visit is normally
already `Completed` by the time billing happens (consultation completion
already closes the Visit per the Phase 8 sync), this is usually a no-op;
it only has a real effect for the rarer race where payment is recorded
before/without the Visit being explicitly closed, and it never forces an
illegal transition (mirrors the tolerant pattern from
`ConsultationService._sync_queue_status`).
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class InvoiceStatus(str, enum.Enum):
    DRAFT = "Draft"
    PENDING_PAYMENT = "PendingPayment"
    PARTIALLY_PAID = "PartiallyPaid"
    PAID = "Paid"
    CANCELLED = "Cancelled"


# Legal forward transitions for an invoice.
INVOICE_STATUS_TRANSITIONS: dict[InvoiceStatus, set[InvoiceStatus]] = {
    InvoiceStatus.DRAFT: {InvoiceStatus.PENDING_PAYMENT, InvoiceStatus.CANCELLED},
    InvoiceStatus.PENDING_PAYMENT: {InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID, InvoiceStatus.CANCELLED},
    InvoiceStatus.PARTIALLY_PAID: {InvoiceStatus.PAID, InvoiceStatus.PENDING_PAYMENT, InvoiceStatus.CANCELLED},
    InvoiceStatus.PAID: {InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PENDING_PAYMENT},  # void-payment backward moves
    InvoiceStatus.CANCELLED: set(),
}


class Invoice(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "invoices"

    invoice_number: Mapped[str] = mapped_column(String(30), nullable=False)
    visit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True, index=True
    )

    invoice_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[InvoiceStatus] = mapped_column(
        SAEnum(InvoiceStatus, name="invoice_status", values_callable=_enum_values),
        nullable=False,
        default=InvoiceStatus.DRAFT,
        server_default=InvoiceStatus.DRAFT.value,
        index=True,
    )

    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    discount_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    tax_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    balance_due: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    visit: Mapped["Visit"] = relationship()
    branch: Mapped["Branch"] = relationship()
    patient: Mapped["Patient"] = relationship()
    doctor: Mapped["Doctor | None"] = relationship()
    items: Mapped[list["InvoiceItem"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    discounts: Mapped[list["Discount"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Invoice id={self.id} invoice_number={self.invoice_number!r} status={self.status!r}>"
