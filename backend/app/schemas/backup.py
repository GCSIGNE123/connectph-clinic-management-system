"""Schemas for the Post-RC1 Phase 2 Milestone 2 Cloud Backup API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class BackupUploadRequest(BaseModel):
    clinic_id: UUID
    record_id: UUID
    operation: str  # "create" | "update" | "delete"
    payload: dict[str, Any]


class BackupUploadResponse(BaseModel):
    id: UUID
    entity_type: str
    record_id: UUID
    synced_at: datetime
