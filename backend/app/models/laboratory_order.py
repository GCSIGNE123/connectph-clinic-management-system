"""Laboratory Orders (Phase 10) - the laboratory department's own workflow
record layered 1:1 on top of a Phase 9 `Order` (order_category=Laboratory).
See the migration docstring (`alembic/versions/0011_laboratory_management.py`)
for the full design rationale on why this is a separate table rather than
extending `orders` in place.

Status machine: Requested -> Collected -> Processing -> Completed -> Released,
or -> Cancelled from any non-terminal state. "Released" is the
Laboratory-role-only final step that makes results visible/final to the
doctor and patient history (spec's "Enter Results -> Doctor Reviews" step
order: results are entered while status is Processing/Completed, then
explicitly Released as a distinct action - not automatically final on entry).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class LaboratoryOrderStatus(str, enum.Enum):
    REQUESTED = "Requested"
    COLLECTED = "Collected"
    PROCESSING = "Processing"
    COMPLETED = "Completed"
    RELEASED = "Released"
    CANCELLED = "Cancelled"


LABORATORY_ORDER_STATUS_TRANSITIONS: dict[LaboratoryOrderStatus, set[LaboratoryOrderStatus]] = {
    LaboratoryOrderStatus.REQUESTED: {LaboratoryOrderStatus.COLLECTED, LaboratoryOrderStatus.CANCELLED},
    LaboratoryOrderStatus.COLLECTED: {LaboratoryOrderStatus.PROCESSING, LaboratoryOrderStatus.CANCELLED},
    LaboratoryOrderStatus.PROCESSING: {LaboratoryOrderStatus.COMPLETED, LaboratoryOrderStatus.CANCELLED},
    LaboratoryOrderStatus.COMPLETED: {LaboratoryOrderStatus.RELEASED, LaboratoryOrderStatus.CANCELLED},
    LaboratoryOrderStatus.RELEASED: set(),
    LaboratoryOrderStatus.CANCELLED: set(),
}


class LaboratoryOrder(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "laboratory_orders"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    visit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("visits.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    doctor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True, index=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("laboratory_templates.id", ondelete="SET NULL"), nullable=True)

    test_type: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[LaboratoryOrderStatus] = mapped_column(
        SAEnum(LaboratoryOrderStatus, name="laboratory_order_status", values_callable=_enum_values),
        nullable=False, default=LaboratoryOrderStatus.REQUESTED, server_default=LaboratoryOrderStatus.REQUESTED.value,
    )

    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    invoice_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoice_items.id", ondelete="SET NULL"), nullable=True
    )

    order: Mapped["Order"] = relationship()
    patient: Mapped["Patient"] = relationship()
    doctor: Mapped["Doctor"] = relationship()
    template: Mapped["LaboratoryTemplate"] = relationship()
    results: Mapped[list["LaboratoryResult"]] = relationship(back_populates="laboratory_order", cascade="all, delete-orphan")
    attachments: Mapped[list["LaboratoryAttachment"]] = relationship(back_populates="laboratory_order", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LaboratoryOrder id={self.id} test_type={self.test_type!r} status={self.status!r}>"
