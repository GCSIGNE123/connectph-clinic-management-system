"""Concurrency-safe daily counter backing `VisitNumberGenerator`.

One row per (clinic, branch, counter_date). Selected with
`SELECT ... FOR UPDATE` inside the caller's transaction so concurrent
visit-creation requests for the same bucket serialize on this row.
"""

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, UUIDPrimaryKeyMixin


class VisitCounter(UUIDPrimaryKeyMixin, TenantMixin, Base):
    __tablename__ = "visit_counters"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    counter_date: Mapped[date] = mapped_column(Date, nullable=False)
    next_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    __table_args__ = (
        UniqueConstraint("clinic_id", "branch_id", "counter_date", name="uq_visit_counter_clinic_branch_date"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<VisitCounter clinic_id={self.clinic_id} next={self.next_number}>"
