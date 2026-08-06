"""Invoice-level discount (Phase 9 - Billing & Cashier).

Applied at the invoice level (not per-line-item) since a clinic-wide
discount (SeniorCitizen/PWD/Employee) typically applies to the whole bill,
not individual services - documented design choice per spec's "clinic-wide
discount" phrasing.
"""

import enum
import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class DiscountType(str, enum.Enum):
    SENIOR_CITIZEN = "SeniorCitizen"
    PWD = "PWD"
    EMPLOYEE = "Employee"
    CUSTOM = "Custom"


class DiscountCalculationType(str, enum.Enum):
    PERCENTAGE = "Percentage"
    FIXED_AMOUNT = "FixedAmount"


class Discount(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "discounts"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    discount_type: Mapped[DiscountType] = mapped_column(
        SAEnum(DiscountType, name="discount_type", values_callable=_enum_values), nullable=False
    )
    calculation_type: Mapped[DiscountCalculationType] = mapped_column(
        SAEnum(DiscountCalculationType, name="discount_calculation_type", values_callable=_enum_values), nullable=False
    )
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    invoice: Mapped["Invoice"] = relationship(back_populates="discounts")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Discount id={self.id} type={self.discount_type!r} amount={self.amount}>"
