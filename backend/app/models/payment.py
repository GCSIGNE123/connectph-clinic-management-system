"""Payment model (Phase 9 - Billing & Cashier).

`payment_method` is a plain enum (not a lookup table) - the product spec
lists a closed set ("Cash, GCash, Bank Transfer, Credit Card, Debit Card")
that doesn't vary per clinic, so a configurable lookup table would be
over-engineering for what is effectively a fixed enum. Split payments are
represented as multiple `payments` rows against the same `invoice_id`.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class PaymentMethod(str, enum.Enum):
    CASH = "Cash"
    GCASH = "GCash"
    BANK_TRANSFER = "BankTransfer"
    CREDIT_CARD = "CreditCard"
    DEBIT_CARD = "DebitCard"


class PaymentStatus(str, enum.Enum):
    COMPLETED = "Completed"
    VOIDED = "Voided"


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "payments"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        SAEnum(PaymentMethod, name="payment_method", values_callable=_enum_values), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, name="payment_status", values_callable=_enum_values),
        nullable=False,
        default=PaymentStatus.COMPLETED,
        server_default=PaymentStatus.COMPLETED.value,
        index=True,
    )
    received_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    invoice: Mapped["Invoice"] = relationship(back_populates="payments")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Payment id={self.id} amount={self.amount} status={self.status!r}>"


class Refund(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, LegacyMixin, Base):
    """Architecture-only per spec: model + migration exist, no UI/full workflow."""

    __tablename__ = "refunds"

    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Pending", server_default="Pending")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    payment: Mapped["Payment"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Refund id={self.id} amount={self.amount} status={self.status!r}>"
