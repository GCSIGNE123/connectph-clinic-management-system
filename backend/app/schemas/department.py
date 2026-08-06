"""Pydantic schemas for Department resources."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DepartmentBase(BaseModel):
    department_code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    color: str | None = Field(default=None, max_length=20)
    status: str = Field(default="Active", max_length=20)


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    department_code: str | None = Field(default=None, max_length=30)
    name: str | None = Field(default=None, max_length=150)
    description: str | None = None
    color: str | None = Field(default=None, max_length=20)
    status: str | None = Field(default=None, max_length=20)


class DepartmentRead(DepartmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    created_at: datetime
    updated_at: datetime


class DepartmentSearchParams(BaseModel):
    q: str | None = None
    status: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class DepartmentListResponse(BaseModel):
    items: list[DepartmentRead]
    total: int
    limit: int
    offset: int
