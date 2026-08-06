"""Clinical Orders (Phase 9): Laboratory/Radiology/Vaccination/Custom orders
created during an in-progress consultation. Procedures and Referrals are
deliberately their own tables (`models/procedure.py`, `models/referral.py`)
per the spec's DATABASE section listing them as top-level tables distinct
from `orders` - see those modules' docstrings for the full reasoning.

`order_items` uses a few nullable typed columns (exam_type/body_part/
clinical_indication) rather than a JSON `details` blob, since the spec is
explicit about field names for Imaging Orders ("Exam Type", "Body Part")
while Laboratory only needs `item_name` - typed columns are clearer/
queryable and the extra columns cost nothing for non-Imaging rows.
"""

import enum
import uuid

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class OrderCategory(str, enum.Enum):
    LABORATORY = "Laboratory"
    RADIOLOGY = "Radiology"
    PROCEDURE = "Procedure"
    REFERRAL = "Referral"
    VACCINATION = "Vaccination"
    CUSTOM = "Custom"


class OrderPriority(str, enum.Enum):
    ROUTINE = "Routine"
    STAT = "STAT"


class OrderStatus(str, enum.Enum):
    """Shared status enum across all order categories per spec's Laboratory
    Orders field list. Accepted simplification: "Collected" reads oddly for
    e.g. a Referral order, but keeping one enum avoids per-category status
    tables/branches for a future processing phase to build on uniformly."""

    REQUESTED = "Requested"
    COLLECTED = "Collected"
    PROCESSING = "Processing"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


ORDER_STATUS_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.REQUESTED: {OrderStatus.COLLECTED, OrderStatus.PROCESSING, OrderStatus.COMPLETED, OrderStatus.CANCELLED},
    OrderStatus.COLLECTED: {OrderStatus.PROCESSING, OrderStatus.COMPLETED, OrderStatus.CANCELLED},
    OrderStatus.PROCESSING: {OrderStatus.COMPLETED, OrderStatus.CANCELLED},
    OrderStatus.COMPLETED: set(),
    OrderStatus.CANCELLED: set(),
}


class Order(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "orders"

    consultation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    visit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True, index=True
    )

    order_number: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    order_category: Mapped[OrderCategory] = mapped_column(
        SAEnum(OrderCategory, name="order_category", values_callable=_enum_values), nullable=False
    )
    priority: Mapped[OrderPriority] = mapped_column(
        SAEnum(OrderPriority, name="order_priority", values_callable=_enum_values),
        nullable=False, default=OrderPriority.ROUTINE, server_default=OrderPriority.ROUTINE.value,
    )
    scheduled_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    clinical_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, name="order_status", values_callable=_enum_values),
        nullable=False, default=OrderStatus.REQUESTED, server_default=OrderStatus.REQUESTED.value,
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    consultation: Mapped["Consultation"] = relationship()
    doctor: Mapped["Doctor"] = relationship()
    patient: Mapped["Patient"] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Order id={self.id} number={self.order_number!r} category={self.order_category!r}>"


class OrderItem(UUIDPrimaryKeyMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "order_items"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    item_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Imaging-specific structured fields (nullable, only populated for Radiology orders).
    exam_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body_part: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clinical_indication: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<OrderItem id={self.id} item_name={self.item_name!r}>"
