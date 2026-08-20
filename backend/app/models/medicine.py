"""Medicine Inventory Phase 1: catalog (`Medicine`) + batch/lot tracking
(`MedicineBatch`), following the parent/child catalog shape already
established by `LaboratoryTemplate`/`LaboratoryTemplateParameter`.

Phase 1 scope only - no stock movement ledger yet. `MedicineBatch.
quantity_remaining` is directly editable via the batch create/update API
(see `MedicineService`); it is deliberately named the same as what Phase 2's
ledger would derive/maintain, and every mutation funnels through
`MedicineService`, so a future ledger-backed rewrite can replace the direct
write with a ledger-sum recompute without changing callers or the schema
shape. See the Phase 1 investigation report for the full rationale.

`MedicineBatchStatus` is a computed/cached value, not user-authoritative
except for `RECALLED` (an explicit business action). `MedicineService`
recomputes ACTIVE/EXPIRED/DEPLETED on every batch create/update and on every
read, so Phase 1 needs no background job to keep it accurate; a future daily
job (Phase 3) can call the same recompute helper instead of duplicating logic.
"""

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class MedicineBatchStatus(str, enum.Enum):
    ACTIVE = "Active"
    EXPIRED = "Expired"
    DEPLETED = "Depleted"
    RECALLED = "Recalled"


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class Medicine(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    """Medicine catalog (master data) - one row per generic/brand/strength
    combination a clinic stocks. Not linked to `Prescription`/
    `PrescriptionItem` in this phase (see investigation report section K)."""

    __tablename__ = "medicines"

    generic_name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    strength: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dosage_form: Mapped[str | None] = mapped_column(String(50), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reorder_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    batches: Mapped[list["MedicineBatch"]] = relationship(
        back_populates="medicine", cascade="all, delete-orphan", order_by="MedicineBatch.expiry_date"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Medicine id={self.id} generic_name={self.generic_name!r}>"


class MedicineBatch(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    """A specific stocked batch/lot of a `Medicine`, with its own expiry.

    `clinic_id` (from `TenantMixin`) is carried directly on this table too,
    not just derived via `medicine_id` - same redundant-but-enforced-tenancy
    pattern as `LaboratoryTemplateParameter`, so a batch can never be
    attached to another clinic's medicine (checked in `MedicineService`,
    backed by this column existing for query/index purposes)."""

    __tablename__ = "medicine_batches"
    __table_args__ = (
        UniqueConstraint("clinic_id", "medicine_id", "batch_number", name="uq_medicine_batch_clinic_medicine_number"),
    )

    medicine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medicines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_number: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity_received: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    quantity_remaining: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    supplier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cost_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[MedicineBatchStatus] = mapped_column(
        SAEnum(MedicineBatchStatus, name="medicine_batch_status", values_callable=_enum_values, native_enum=False),
        nullable=False, default=MedicineBatchStatus.ACTIVE, server_default=MedicineBatchStatus.ACTIVE.value,
    )

    medicine: Mapped["Medicine"] = relationship(back_populates="batches")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MedicineBatch id={self.id} batch_number={self.batch_number!r}>"
