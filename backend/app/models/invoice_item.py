"""Invoice line item (Phase 9 - Billing & Cashier)."""

import enum
import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class InvoiceItemType(str, enum.Enum):
    CONSULTATION_FEE = "ConsultationFee"
    FOLLOW_UP_FEE = "FollowUpFee"
    MEDICAL_CERTIFICATE = "MedicalCertificate"
    LABORATORY = "Laboratory"
    XRAY = "XRay"
    PROCEDURE = "Procedure"
    VACCINATION = "Vaccination"
    CUSTOM = "Custom"


class InvoiceItem(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "invoice_items"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    item_type: Mapped[InvoiceItemType] = mapped_column(
        SAEnum(InvoiceItemType, name="invoice_item_type", values_callable=_enum_values),
        nullable=False,
        default=InvoiceItemType.CUSTOM,
        server_default=InvoiceItemType.CUSTOM.value,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=1, server_default="1")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    invoice: Mapped["Invoice"] = relationship(back_populates="items")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<InvoiceItem id={self.id} description={self.description!r} line_total={self.line_total}>"
