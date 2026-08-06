"""Pydantic schemas for the ClinicService (services catalog) resource."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ClinicServiceBase(BaseModel):
    service_code: str = Field(min_length=1, max_length=30)
    service_name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    default_price: Decimal = Field(default=Decimal("0"), ge=0)
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    department_id: UUID | None = None
    status: str = Field(default="Active", max_length=20)


class ClinicServiceCreate(ClinicServiceBase):
    pass


class ClinicServiceUpdate(BaseModel):
    service_code: str | None = Field(default=None, max_length=30)
    service_name: str | None = Field(default=None, max_length=150)
    description: str | None = None
    default_price: Decimal | None = Field(default=None, ge=0)
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    department_id: UUID | None = None
    status: str | None = Field(default=None, max_length=20)


class ClinicServiceRead(ClinicServiceBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    created_at: datetime
    updated_at: datetime


class ClinicServiceSearchParams(BaseModel):
    q: str | None = None
    department_id: UUID | None = None
    status: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ClinicServiceListResponse(BaseModel):
    items: list[ClinicServiceRead]
    total: int
    limit: int
    offset: int
