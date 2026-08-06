"""Receptionist Shift Management (Phase 21).

A `Shift` tracks a front-desk cash-handling session for a single
receptionist: opening cash count, opened/closed timestamps, and the actual
cash count entered at close. Summary figures (cash collections, non-cash
collections, discounts, refunds, expected/actual cash) are deliberately NOT
stored as running totals on this row - they are computed at read time from
the existing `Payment`/`Discount`/`Refund` rows within the shift's
`opened_at`..`closed_at` (or ..now, while open) window. This avoids a whole
class of running-total drift bugs (a voided payment, a late refund, a retried
request) that a synchronously-maintained counter would be exposed to - the
same "compute at read time from the source-of-truth ledger" principle
already used elsewhere in this codebase (e.g. Invoice.balance_due-style
derivations), just applied to a per-shift window instead of a per-invoice one.
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
from app.db.mixins import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class ShiftStatus(str, enum.Enum):
    OPEN = "Open"
    CLOSED = "Closed"


class Shift(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "shifts"

    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    receptionist_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    opening_cash: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_cash_count: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[ShiftStatus] = mapped_column(
        SAEnum(ShiftStatus, name="shift_status", values_callable=_enum_values),
        nullable=False,
        default=ShiftStatus.OPEN,
        server_default=ShiftStatus.OPEN.value,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    receptionist: Mapped["User"] = relationship(foreign_keys=[receptionist_user_id])  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Shift id={self.id} receptionist_user_id={self.receptionist_user_id} status={self.status!r}>"
