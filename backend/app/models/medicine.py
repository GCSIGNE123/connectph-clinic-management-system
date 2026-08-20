"""Medicine Inventory: catalog (`Medicine`) + batch/lot tracking
(`MedicineBatch`), following the parent/child catalog shape already
established by `LaboratoryTemplate`/`LaboratoryTemplateParameter`.

Phase 1 scope: no stock movement ledger. `MedicineBatch.quantity_remaining`
was directly editable via the batch create/update API.

Phase 2 (this revision): `MedicineStockMovement` is now the authoritative
ledger for every quantity change AFTER a batch is created. Batch creation
still directly establishes the opening `quantity_received`/
`quantity_remaining` (no ledger entry is synthesized for that - see
`MedicineService.create_batch`'s docstring for the rationale); every
subsequent change - Received/Adjustment/Dispensed/Expired/Recalled - is a
`MedicineStockMovement` row, and `MedicineBatchUpdate` no longer accepts
`quantity_received`/`quantity_remaining` at all (removed from the schema),
so there is exactly one path to change a batch's quantity post-creation.
`MedicineBatch.quantity_remaining`/`quantity_received` remain as a
maintained read cache, always updated in the same DB transaction as the
`MedicineStockMovement` insert that changed them (see `MedicineService.
create_movement`).

`MedicineBatchStatus` is a computed/cached value, not user-authoritative
except for `RECALLED` (an explicit business action, settable either via the
Phase 1 direct-status-update path or, now, via a `RECALLED` movement).
`MedicineService` recomputes ACTIVE/EXPIRED/DEPLETED on every batch
create/update/movement and on every read, so this stays accurate with no
background job; a future daily job (Phase 3) can call the same recompute
helper instead of duplicating logic.
"""

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
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


class MedicineStockMovementType(str, enum.Enum):
    RECEIVED = "Received"
    ADJUSTMENT = "Adjustment"
    DISPENSED = "Dispensed"
    EXPIRED = "Expired"
    RECALLED = "Recalled"


class MedicineStockMovement(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, Base):
    """Append-only ledger entry for a `MedicineBatch` quantity change - the
    authoritative accounting trail Phase 2 introduces. Never updated or
    deleted after insert; mirrors `AuditLog`'s "append-only, TimestampMixin
    only (no soft-delete)" shape for the same reason - both are immutable
    history rows, not editable records.

    `reference_type`/`reference_id` exist for future compatibility (e.g. a
    later phase's prescription-to-dispensing integration attaching a
    `Dispensed` movement to a `prescription_item`) - Phase 2 never sets
    them; every movement created in this phase has both null.
    """

    __tablename__ = "medicine_stock_movements"

    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medicine_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    movement_type: Mapped[MedicineStockMovementType] = mapped_column(
        SAEnum(MedicineStockMovementType, name="medicine_stock_movement_type", values_callable=_enum_values, native_enum=False),
        nullable=False,
    )
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    # Snapshot of `quantity_remaining` immediately AFTER this movement was
    # applied - lets the ledger UI show "Resulting Quantity" per row without
    # replaying the whole history, and gives every row an immutable,
    # independently-verifiable record of the batch's quantity at that point
    # in time even if the cache on `MedicineBatch` is ever rebuilt.
    resulting_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    performed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reference_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    batch: Mapped["MedicineBatch"] = relationship()
    # Explicit target class name (rather than inferring from the `Mapped[]`
    # annotation) since `User` isn't imported into this module's namespace -
    # SQLAlchemy resolves a string target against its mapper registry
    # instead of this module's globals.
    performed_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[performed_by], viewonly=True)

    @property
    def performed_by_name(self) -> str | None:
        return self.performed_by_user.full_name if self.performed_by_user is not None else None

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MedicineStockMovement id={self.id} batch_id={self.batch_id} type={self.movement_type}>"
