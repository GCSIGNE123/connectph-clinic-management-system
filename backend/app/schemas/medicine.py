"""Pydantic schemas for the Medicine Inventory Phase 1 resources (Medicine
catalog + MedicineBatch)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.medicine import MedicineBatchStatus


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


class MedicineSearchParams(BaseModel):
    q: str | None = None
    is_active: bool | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class MedicineListResponse(BaseModel):
    items: list[MedicineRead]
    total: int
    limit: int
    offset: int


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
    other `*Update` schemas). `quantity_received`/`quantity_remaining`
    cross-validation is enforced in `MedicineService` against the batch's
    resulting merged values, since either field alone may be omitted here."""

    batch_number: str | None = Field(default=None, min_length=1, max_length=100)
    quantity_received: int | None = Field(default=None, ge=0)
    quantity_remaining: int | None = Field(default=None, ge=0)
    expiry_date: date | None = None
    received_date: date | None = None
    supplier: str | None = Field(default=None, max_length=255)
    cost_per_unit: Decimal | None = Field(default=None, ge=0)
    # Manual override only meaningful for RECALLED (see model docstring) -
    # any other value is rejected in the service layer since ACTIVE/EXPIRED/
    # DEPLETED are always computed, never set directly by a client.
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
