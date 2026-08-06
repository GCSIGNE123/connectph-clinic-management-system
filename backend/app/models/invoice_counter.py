"""Concurrency-safe counter backing `InvoiceNumberGenerator` - mirrors
`VisitCounter`/`QueueCounter` (see `services/invoice_number_generator.py`)."""

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class InvoiceCounter(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "invoice_counters"
    __table_args__ = (UniqueConstraint("clinic_id", "counter_date", name="uq_invoice_counter_clinic_date"),)

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    counter_date: Mapped[date] = mapped_column(Date, nullable=False)
    next_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<InvoiceCounter clinic_id={self.clinic_id} date={self.counter_date} next={self.next_number}>"
