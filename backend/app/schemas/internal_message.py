"""Pydantic schemas for internal staff messaging (Phase 20, item 14)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InternalMessageCreate(BaseModel):
    recipient_id: UUID
    body: str = Field(min_length=1, max_length=2000)


class InternalMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sender_id: UUID
    sender_name: str | None = None
    recipient_id: UUID
    recipient_name: str | None = None
    body: str
    read_at: datetime | None = None
    created_at: datetime


class InternalMessageListResponse(BaseModel):
    items: list[InternalMessageRead]
    total: int
    unread_count: int


class ConversationUnread(BaseModel):
    """Per-conversation unread breakdown (item 6): lets the UI preserve
    other conversations' unread indicators when one conversation is opened,
    instead of only exposing a single clinic-wide total."""

    other_user_id: UUID
    other_user_name: str | None = None
    unread_count: int
    last_message_at: datetime
