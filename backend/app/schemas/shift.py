"""Pydantic schemas for Receptionist Shift Management (Phase 21)."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.shift import ShiftStatus


class ShiftCreate(BaseModel):
    opening_cash: Decimal = Field(ge=0)
    branch_id: UUID | None = None


class ShiftClose(BaseModel):
    actual_cash_count: Decimal = Field(ge=0)
    notes: str | None = Field(default=None, max_length=1000)


class ShiftSummary(BaseModel):
    """Live-computed figures from `Payment`/`Discount`/`Refund` rows within
    the shift's `opened_at`..(`closed_at` or now) window. Never stored."""

    cash_collections: Decimal = Decimal("0")
    gcash_collections: Decimal = Decimal("0")
    card_collections: Decimal = Decimal("0")
    other_collections: Decimal = Decimal("0")
    total_collections: Decimal = Decimal("0")
    discounts_given: Decimal = Decimal("0")
    cash_refunds: Decimal = Decimal("0")
    non_cash_refunds: Decimal = Decimal("0")
    total_refunds: Decimal = Decimal("0")
    payment_count: int = 0
    discount_count: int = 0
    refund_count: int = 0
    expected_cash: Decimal = Decimal("0")


class ShiftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    branch_id: UUID | None = None
    receptionist_user_id: UUID
    receptionist_name: str | None = None
    opening_cash: Decimal
    opened_at: datetime
    closed_at: datetime | None = None
    actual_cash_count: Decimal | None = None
    status: ShiftStatus
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ShiftDetail(ShiftRead):
    summary: ShiftSummary
    expected_cash: Decimal | None = None
    cash_difference: Decimal | None = None
