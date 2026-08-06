"""Pydantic schemas for Branch resources."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class BranchBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=50)
    contact_number: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    manager_id: UUID | None = None
    status: str = Field(default="Active", max_length=20)


class BranchCreate(BranchBase):
    pass


class BranchUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    code: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=50)
    contact_number: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    manager_id: UUID | None = None
    status: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None


class BranchRead(BranchBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class BranchSearchParams(BaseModel):
    q: str | None = None
    status: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class BranchListResponse(BaseModel):
    items: list[BranchRead]
    total: int
    limit: int
    offset: int
