"""Pydantic schemas for the Legacy Migration Wizard (Phase 14)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.migration_batch import (
    MigrationBatchStatus,
    MigrationEntityProgressStatus,
    MigrationEntityType,
    MigrationIssueResolution,
    MigrationIssueSeverity,
    MigrationIssueType,
    MigrationLogLevel,
    MigrationSourceType,
    MigrationTransformType,
)


class MigrationBatchCreate(BaseModel):
    source_type: MigrationSourceType
    source_description: str | None = Field(default=None, max_length=2000)


class MigrationBatchRead(BaseModel):
    id: UUID
    clinic_id: UUID
    source_type: MigrationSourceType
    source_description: str | None
    status: MigrationBatchStatus
    started_at: datetime | None
    completed_at: datetime | None
    total_records_found: int | None
    total_records_imported: int
    total_duplicates: int
    total_warnings: int
    total_errors: int
    current_entity: MigrationEntityType | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MigrationEntityProgressRead(BaseModel):
    entity_type: MigrationEntityType
    status: MigrationEntityProgressStatus
    records_found: int
    records_imported: int
    records_skipped: int
    records_failed: int
    last_processed_offset: int

    model_config = {"from_attributes": True}


class MigrationStatusResponse(BaseModel):
    batch: MigrationBatchRead
    entities: list[MigrationEntityProgressRead]
    elapsed_seconds: float | None = None
    estimated_seconds_remaining: float | None = None


class MigrationFieldMappingRead(BaseModel):
    id: UUID
    entity_type: MigrationEntityType
    source_field: str
    destination_field: str | None
    transform_type: MigrationTransformType
    transform_config: dict[str, Any] | None
    is_ignored: bool

    model_config = {"from_attributes": True}


class MigrationFieldMappingUpsert(BaseModel):
    entity_type: MigrationEntityType
    source_field: str
    destination_field: str | None = None
    transform_type: MigrationTransformType = MigrationTransformType.NONE
    transform_config: dict[str, Any] | None = None
    is_ignored: bool = False


class MigrationFieldMappingBulkUpdate(BaseModel):
    mappings: list[MigrationFieldMappingUpsert]


class MigrationValidationIssueRead(BaseModel):
    id: UUID
    entity_type: MigrationEntityType
    source_row_identifier: str
    issue_type: MigrationIssueType
    severity: MigrationIssueSeverity
    message: str
    resolution: MigrationIssueResolution | None

    model_config = {"from_attributes": True}


class MigrationIssueResolveRequest(BaseModel):
    resolution: MigrationIssueResolution


class MigrationPreviewResponse(BaseModel):
    entity_type: MigrationEntityType
    rows_to_import: int
    rows_to_skip: int
    warnings: int
    errors: int


class MigrationLogRead(BaseModel):
    log_level: MigrationLogLevel
    entity_type: MigrationEntityType | None
    message: str
    details: dict[str, Any] | None
    logged_at: datetime

    model_config = {"from_attributes": True}


class MigrationVerificationEntityReport(BaseModel):
    entity_type: MigrationEntityType
    expected: int
    imported: int
    matches: bool


class MigrationVerificationReport(BaseModel):
    batch_id: UUID
    generated_at: datetime
    entities: list[MigrationVerificationEntityReport]
    relationship_issues: list[str]
    overall_ok: bool
