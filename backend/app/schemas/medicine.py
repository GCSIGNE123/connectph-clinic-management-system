"""Pydantic schemas for the Medicine Inventory resources: Medicine catalog,
MedicineBatch (Phase 1), and MedicineStockMovement (Phase 2)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.medicine import MedicineBatchStatus, MedicineStockMovementType


class MedicineBase(BaseModel):
    generic_name: str = Field(min_length=1, max_length=255)
    brand_name: str | None = Field(default=None, max_length=255)
    strength: str | None = Field(default=None, max_length=50)
    dosage_form: str | None = Field(default=None, max_length=50)
    unit: str | None = Field(default=None, max_length=30)
    reorder_level: int | None = Field(default=None, ge=0)
    is_active: bool = True


class MedicineCreate(MedicineBase):
    pass


class MedicineUpdate(BaseModel):
    generic_name: str | None = Field(default=None, min_length=1, max_length=255)
    brand_name: str | None = Field(default=None, max_length=255)
    strength: str | None = Field(default=None, max_length=50)
    dosage_form: str | None = Field(default=None, max_length=50)
    unit: str | None = Field(default=None, max_length=30)
    reorder_level: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class MedicineRead(MedicineBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    created_at: datetime
    updated_at: datetime
    # Phase 3: medicine-level stock/expiry summary, computed by aggregating
    # this medicine's batches (see `medicine_service._summarize_stock_status`)
    # - NOT a stored column. One medicine can have both an expired batch and
    # a perfectly good one; this reflects the most urgent applicable state
    # rather than naively calling the whole medicine "Expired". Optional/
    # unset only when the caller didn't ask for it to be computed.
    stock_status: str | None = None


class MedicineSearchParams(BaseModel):
    q: str | None = None
    is_active: bool | None = None
    # "in_stock" | "low_stock" | "near_expiry" | "expired" | "out_of_stock"
    stock_status: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class MedicineListResponse(BaseModel):
    items: list[MedicineRead]
    total: int
    limit: int
    offset: int


class MedicineStatsResponse(BaseModel):
    """Medicine-level counts (not batch-level) for the dashboard stat cards
    and the Medicine Inventory page's filter chips - see
    `medicine_service.get_stats`."""

    expiring_soon: int
    expired: int
    low_stock: int
    out_of_stock: int


class MedicineBatchBase(BaseModel):
    batch_number: str = Field(min_length=1, max_length=100)
    quantity_received: int = Field(ge=0)
    quantity_remaining: int = Field(ge=0)
    expiry_date: date
    received_date: date | None = None
    supplier: str | None = Field(default=None, max_length=255)
    cost_per_unit: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _quantity_remaining_not_over_received(self) -> "MedicineBatchBase":
        if self.quantity_remaining > self.quantity_received:
            raise ValueError("quantity_remaining cannot exceed quantity_received")
        return self


class MedicineBatchCreate(MedicineBatchBase):
    pass


class MedicineBatchUpdate(BaseModel):
    """All fields optional (PATCH-style via PUT, matching this codebase's
    other `*Update` schemas).

    Phase 2: `quantity_received`/`quantity_remaining` are deliberately NOT
    accepted here anymore (they were in Phase 1) - now that
    `MedicineStockMovement` exists, every post-creation quantity change must
    go through `POST .../batches/{batch_id}/movements` so it is ledgered and
    auditable. This is the one intentional behavior change from Phase 1's
    "Edit Batch" form; see the Phase 2 report."""

    batch_number: str | None = Field(default=None, min_length=1, max_length=100)
    expiry_date: date | None = None
    received_date: date | None = None
    supplier: str | None = Field(default=None, max_length=255)
    cost_per_unit: Decimal | None = Field(default=None, ge=0)
    # Manual override only meaningful for RECALLED (see model docstring) -
    # any other value is rejected in the service layer since ACTIVE/EXPIRED/
    # DEPLETED are always computed, never set directly by a client. Kept as
    # an alternative to a RECALLED movement for a no-quantity-change recall
    # (e.g. flagging a batch before any units have actually been pulled).
    status: MedicineBatchStatus | None = None


class MedicineBatchRead(MedicineBatchBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    medicine_id: UUID
    status: MedicineBatchStatus
    created_at: datetime
    updated_at: datetime


class MedicineBatchListResponse(BaseModel):
    items: list[MedicineBatchRead]
    total: int


class MedicineStockMovementCreate(BaseModel):
    """`reference_type`/`reference_id` are intentionally NOT accepted here -
    they exist on the model only for a future phase's integration (e.g.
    prescription dispensing) to set internally; a Phase 2 client can never
    set them. The backend computes `resulting_quantity`; a client cannot
    supply it."""

    movement_type: MedicineStockMovementType
    quantity_delta: int = Field(description="Signed quantity change. Must not be zero.")
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _quantity_delta_not_zero(self) -> "MedicineStockMovementCreate":
        if self.quantity_delta == 0:
            raise ValueError("quantity_delta cannot be zero")
        return self


class MedicineStockMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    batch_id: UUID
    movement_type: MedicineStockMovementType
    quantity_delta: int
    resulting_quantity: int
    reason: str | None
    performed_by: UUID | None
    performed_by_name: str | None
    reference_type: str | None
    reference_id: UUID | None
    created_at: datetime


class MedicineStockMovementListResponse(BaseModel):
    items: list[MedicineStockMovementRead]
    total: int
