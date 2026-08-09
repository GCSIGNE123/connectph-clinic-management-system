"""Pydantic schemas for QueueSetting and PriorityType (pure configuration)."""

from datetime import datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class QueueSettingBase(BaseModel):
    branch_id: UUID | None = None
    # Post-RC1 (Multi-Department/Multi-Doctor TV Queue Display): these two
    # scope columns already existed on the `QueueSetting` model (department_id
    # since Phase 5) but were never exposed on the API schema - only the
    # clinic-wide (branch_id-only) row was reachable via `PUT /queue-settings`.
    # Both are additive/optional; omitting them (the pre-existing behaviour)
    # still upserts the clinic/branch-wide default row exactly as before.
    department_id: UUID | None = None
    doctor_id: UUID | None = None
    queue_prefix: str = Field(default="A", min_length=1, max_length=10)
    max_daily_queue: int = Field(default=200, ge=1, le=10000)
    reset_time: time
    allow_walkins: bool = True
    allow_priority_lane: bool = True


class QueueSettingCreate(QueueSettingBase):
    pass


class QueueSettingUpdate(BaseModel):
    queue_prefix: str | None = Field(default=None, min_length=1, max_length=10)
    max_daily_queue: int | None = Field(default=None, ge=1, le=10000)
    reset_time: time | None = None
    allow_walkins: bool | None = None
    allow_priority_lane: bool | None = None


class QueueSettingRead(QueueSettingBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    department_name: str | None = None
    doctor_name: str | None = None
    created_at: datetime
    updated_at: datetime


class QueueSettingListResponse(BaseModel):
    items: list[QueueSettingRead]
    total: int


class PriorityTypeBase(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    label: str = Field(min_length=1, max_length=100)
    enabled: bool = True


class PriorityTypeCreate(PriorityTypeBase):
    pass


class PriorityTypeUpdate(BaseModel):
    code: str | None = Field(default=None, max_length=30)
    label: str | None = Field(default=None, max_length=100)
    enabled: bool | None = None


class PriorityTypeRead(PriorityTypeBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    created_at: datetime
    updated_at: datetime


class PriorityTypeListResponse(BaseModel):
    items: list[PriorityTypeRead]
    total: int
