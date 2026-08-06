"""Doctor model + doctor weekly availability schedule.

`DoctorSchedule` is architecture-only (a weekly availability window per
doctor/branch/day) - it deliberately has no notion of appointment slots or
bookings; that belongs to the future Appointments module.
"""

import enum
import uuid
from decimal import Decimal

from datetime import date as date_type

from sqlalchemy import (
    Date,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy import Boolean
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class DoctorStatus(str, enum.Enum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"
    ON_LEAVE = "On Leave"


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class Doctor(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "doctors"
    __table_args__ = (UniqueConstraint("clinic_id", "doctor_code", name="uq_doctor_clinic_code"),)

    doctor_code: Mapped[str] = mapped_column(String(30), nullable=False)

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    suffix: Mapped[str | None] = mapped_column(String(20), nullable=True)

    prc_license: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ptr_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    specialization: Mapped[str | None] = mapped_column(String(150), nullable=True)

    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )

    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    signature_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contact_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    consultation_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    status: Mapped[DoctorStatus] = mapped_column(
        SAEnum(DoctorStatus, name="doctor_status", values_callable=_enum_values),
        nullable=False,
        default=DoctorStatus.ACTIVE,
        server_default=DoctorStatus.ACTIVE.value,
        index=True,
    )

    department: Mapped["Department | None"] = relationship()
    branch: Mapped["Branch | None"] = relationship()
    schedules: Mapped[list["DoctorSchedule"]] = relationship(back_populates="doctor", cascade="all, delete-orphan")

    @property
    def full_name(self) -> str:
        parts = [self.first_name, self.middle_name, self.last_name, self.suffix]
        return " ".join(p for p in parts if p)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Doctor id={self.id} doctor_code={self.doctor_code!r}>"


class DoctorSchedule(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    """A weekly availability window for a doctor at a branch.

    Phase 4 shipped this as architecture-only (no slot/booking logic). Phase
    11 (Appointment Management) extends it additively - in place, rather
    than creating a parallel table - with the fields the Time Slot Engine
    needs: lunch break, slot duration, a soft daily cap, and support for a
    non-recurring date-bounded override (`is_recurring=False` +
    `effective_from`/`effective_to`) layered on top of the recurring weekly
    row. See docs/DATABASE.md for the rationale.
    """

    __tablename__ = "doctor_schedules"

    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 0=Monday .. 6=Sunday
    start_time: Mapped[str] = mapped_column(Time, nullable=False)
    end_time: Mapped[str] = mapped_column(Time, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Phase 11 additions ---
    lunch_break_start: Mapped[str | None] = mapped_column(Time, nullable=True)
    lunch_break_end: Mapped[str | None] = mapped_column(Time, nullable=True)
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15, server_default="15")
    max_patients_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default="true")
    effective_from: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date_type | None] = mapped_column(Date, nullable=True)

    doctor: Mapped["Doctor"] = relationship(back_populates="schedules")
    branch: Mapped["Branch | None"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DoctorSchedule id={self.id} doctor_id={self.doctor_id} day={self.day_of_week}>"
