"""Pydantic schemas for Consultation Room resources."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConsultationRoomBase(BaseModel):
    room_name: str = Field(min_length=1, max_length=150)
    room_number: str | None = Field(default=None, max_length=30)
    department_id: UUID | None = None
    branch_id: UUID | None = None
    status: str = Field(default="Active", max_length=20)


class ConsultationRoomCreate(ConsultationRoomBase):
    pass


class ConsultationRoomUpdate(BaseModel):
    room_name: str | None = Field(default=None, max_length=150)
    room_number: str | None = Field(default=None, max_length=30)
    department_id: UUID | None = None
    branch_id: UUID | None = None
    status: str | None = Field(default=None, max_length=20)


class ConsultationRoomRead(ConsultationRoomBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    created_at: datetime
    updated_at: datetime


class ConsultationRoomSearchParams(BaseModel):
    q: str | None = None
    department_id: UUID | None = None
    branch_id: UUID | None = None
    status: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ConsultationRoomListResponse(BaseModel):
    items: list[ConsultationRoomRead]
    total: int
    limit: int
    offset: int
