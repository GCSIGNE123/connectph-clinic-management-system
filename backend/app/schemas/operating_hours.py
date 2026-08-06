"""Pydantic schemas for OperatingHours (weekly schedule per branch)."""

from datetime import datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OperatingHoursBase(BaseModel):
    branch_id: UUID
    day_of_week: int = Field(ge=0, le=6, description="0=Monday .. 6=Sunday")
    opening_time: time | None = None
    closing_time: time | None = None
    lunch_break_start: time | None = None
    lunch_break_end: time | None = None
    is_closed: bool = False


class OperatingHoursCreate(OperatingHoursBase):
    pass


class OperatingHoursUpdate(BaseModel):
    opening_time: time | None = None
    closing_time: time | None = None
    lunch_break_start: time | None = None
    lunch_break_end: time | None = None
    is_closed: bool | None = None


class OperatingHoursRead(OperatingHoursBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    created_at: datetime
    updated_at: datetime


class OperatingHoursListResponse(BaseModel):
    items: list[OperatingHoursRead]
    total: int
