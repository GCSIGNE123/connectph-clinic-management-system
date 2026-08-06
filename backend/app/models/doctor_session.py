"""Doctor Session Control (Client Acceptance Revisions Round 3, item 14).

A `DoctorSession` is a lightweight, per-doctor-per-day "actively accepting
queue calls" flag - pressing "Start Receiving Patients" opens one for today;
there is nothing to configure or accumulate on it (no cash, no totals), it
is purely a gate: Reception is only allowed to `Call` a Waiting ticket for a
doctor who has an open session for today. Modeled as its own small table
(mirroring `Shift`'s "one open per X at a time" pattern - see
`models/shift.py` and migration `0020_shift_management.py`) rather than
overloading `Doctor.status` (which already means something else - whether
the doctor account itself is Active/Inactive, not "receiving patients right
now") or building a new generic `ConsultationSession` concept - no such
generic concept exists anywhere else in this codebase to reuse (checked
`doctor_workspace_service.py`, `consultation_service.py` first, per the
task's own "check first before adding new schema" guidance).

One row per (clinic, doctor, session_date); a DB partial unique index (see
the migration) enforces at most one *open* (`ended_at IS NULL`) session per
doctor at a time, mirroring `Shift`'s `ix_shifts_one_open_per_receptionist`.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class DoctorSession(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, Base):
    """A doctor's "actively receiving patients" window for a single day."""

    __tablename__ = "doctor_sessions"
    __table_args__ = (
        UniqueConstraint("clinic_id", "doctor_id", "session_date", name="uq_doctor_session_clinic_doctor_date"),
    )

    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    doctor: Mapped["Doctor"] = relationship()  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DoctorSession id={self.id} doctor_id={self.doctor_id} date={self.session_date} active={self.ended_at is None}>"
