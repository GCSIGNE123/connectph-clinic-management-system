"""Pydantic schemas for the Phase 3 notification system."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    type: str
    title: str
    body: str
    entity_type: str | None
    entity_id: UUID | None
    created_at: datetime
    is_read: bool


class NotificationListResponse(BaseModel):
    items: list[NotificationRead]
    total: int


class NotificationUnreadCountResponse(BaseModel):
    unread_count: int


class NotificationMarkAllReadResponse(BaseModel):
    marked_count: int
