"""Pydantic schemas for the Holiday calendar."""

from datetime import date as date_, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class HolidayBase(BaseModel):
    holiday_name: str = Field(min_length=1, max_length=150)
    date: date_
    is_recurring: bool = False
    is_closed: bool = True
    is_half_day: bool = False
    branch_id: UUID | None = None


class HolidayCreate(HolidayBase):
    pass


class HolidayUpdate(BaseModel):
    holiday_name: str | None = Field(default=None, max_length=150)
    date: date_ | None = None
    is_recurring: bool | None = None
    is_closed: bool | None = None
    is_half_day: bool | None = None
    branch_id: UUID | None = None


class HolidayRead(HolidayBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    created_at: datetime
    updated_at: datetime


class HolidaySearchParams(BaseModel):
    year: int | None = None
    branch_id: UUID | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class HolidayListResponse(BaseModel):
    items: list[HolidayRead]
    total: int
    limit: int
    offset: int
