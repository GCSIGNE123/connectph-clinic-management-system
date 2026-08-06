"""Legacy Migration Wizard endpoints (Phase 14).

Role gating: Owner and Administrator ONLY (`require_migration_role`) -
the strictest gate in the project, matching Phase 12's analytics gate.
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_clinic_context, require_migration_role
from app.db.session import AsyncSessionLocal
from app.models.migration_batch import (
    MIGRATION_ENTITY_ORDER,
    MigrationBatch,
    MigrationBatchStatus,
    MigrationEntityProgress,
    MigrationEntityProgressStatus,
    MigrationEntityType,
    MigrationFieldMapping,
    MigrationSourceType,
    MigrationValidationIssue,
)
from app.models.user import User
from app.schemas.migration import (
    MigrationBatchCreate,
    MigrationBatchRead,
    MigrationEntityProgressRead,
    MigrationFieldMappingBulkUpdate,
    MigrationFieldMappingRead,
    MigrationIssueResolveRequest,
    MigrationLogRead,
    MigrationPreviewResponse,
    MigrationStatusResponse,
    MigrationValidationIssueRead,
    MigrationVerificationReport,
)
from app.services.audit_service import AuditService
from app.services.migration.mapping_service import MappingService, suggest_mappings
from app.services.migration.migration_service import IMPLEMENTED_ENTITIES, MigrationService
from app.services.migration.source_adapters.registry import get_adapter

router = APIRouter(prefix="/migration", tags=["migration"])

UPLOAD_ROOT = Path(__file__).resolve().parents[3] / "var" / "migration_uploads"


def _entity_from_filename(filename: str) -> MigrationEntityType | None:
    stem = Path(filename).stem.lower()
    for entity in MigrationEntityType:
        if entity.value.lower() == stem or entity.value.lower().rstrip("s") == stem:
            return entity
    return None


def _connection_config_for_batch(batch: MigrationBatch) -> dict[str, Any]:
    if not batch.uploaded_file_path:
        return {}
    manifest = json.loads(batch.uploaded_file_path)
    if batch.source_type == MigrationSourceType.EXCEL:
        return {"file": manifest["file"]}
    return {"files": {k: v for k, v in manifest.get("files", {}).items()}}


async def _get_batch_or_404(service: MigrationService, batch_id: UUID, clinic_id: UUID) -> MigrationBatch:
    batch = await service.get_batch(batch_id, clinic_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Migration batch not found")
    return batch


@router.post("/batches", response_model=MigrationBatchRead, status_code=status.HTTP_201_CREATED)
async def create_batch(
    payload: MigrationBatchCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    current_user: User = Depends(require_migration_role),
    db: AsyncSession = Depends(get_db),
) -> MigrationBatch:
    service = MigrationService(db)
    return await service.create_batch(
        clinic_id=clinic_id, actor=current_user, source_type=payload.source_type, source_description=payload.source_description
    )


@router.get("/batches", response_model=list[MigrationBatchRead])
async def list_batches(
    clinic_id: UUID = Depends(require_clinic_context),
    current_user: User = Depends(require_migration_role),
    db: AsyncSession = Depends(get_db),
) -> list[MigrationBatch]:
    service = MigrationService(db)
    return await service.list_batches(clinic_id)


@router.post("/batches/{batch_id}/upload", response_model=MigrationBatchRead)
async def upload_source(
    batch_id: UUID,
    files: list[UploadFile] = File(...),
    clinic_id: UUID = Depends(require_clinic_context),
    current_user: User = Depends(require_migration_role),
    db: AsyncSession = Depends(get_db),
) -> MigrationBatch:
    service = MigrationService(db)
    batch = await _get_batch_or_404(service, batch_id, clinic_id)
    if batch.source_type not in (MigrationSourceType.CSV, MigrationSourceType.EXCEL):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only CSV and Excel sources have a working upload path in this build.")

    # Phase 16: this is the one upload endpoint in the app that actually
    # relays real file bytes (every other upload flow is a presigned-URL
    # request with no body - see app/core/upload_validation.py's docstring)
    # and it previously had zero extension or size validation before
    # writing an arbitrary-sized client file straight to disk. Enforce a
    # real per-file size cap and extension allow-list here.
    _MAX_MIGRATION_FILE_BYTES = 50 * 1024 * 1024  # 50 MB - bulk CSV/Excel imports are expected to be sizeable
    allowed_ext = {".xlsx"} if batch.source_type == MigrationSourceType.EXCEL else {".csv"}
    for upload in files:
        ext = Path(upload.filename or "").suffix.lower()
        if ext not in allowed_ext:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{upload.filename}' has an unsupported extension for this source type; expected {sorted(allowed_ext)}.",
            )

    batch_dir = UPLOAD_ROOT / str(batch.id)
    batch_dir.mkdir(parents=True, exist_ok=True)

    if batch.source_type == MigrationSourceType.EXCEL:
        upload = files[0]
        content = await upload.read()
        if len(content) > _MAX_MIGRATION_FILE_BYTES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File exceeds the 50 MB upload limit.")
        dest = batch_dir / "workbook.xlsx"
        dest.write_bytes(content)
        manifest = {"file": str(dest)}
    else:
        file_map: dict[str, str] = {}
        for upload in files:
            content = await upload.read()
            if len(content) > _MAX_MIGRATION_FILE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File '{upload.filename}' exceeds the 50 MB upload limit.",
                )
            entity = _entity_from_filename(upload.filename or "")
            key = entity.value if entity else Path(upload.filename or f"file{len(file_map)}").stem
            dest = batch_dir / (Path(upload.filename or f"{key}.csv").name)
            dest.write_bytes(content)
            file_map[key] = str(dest)
        manifest = {"files": file_map}

    batch.uploaded_file_path = json.dumps(manifest)
    await service.set_uploaded_path(batch, batch.uploaded_file_path)
    return batch


@router.post("/batches/{batch_id}/analyze")
async def analyze_batch(
    batch_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    current_user: User = Depends(require_migration_role),
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[str]]:
    service = MigrationService(db)
    batch = await _get_batch_or_404(service, batch_id, clinic_id)
    config = _connection_config_for_batch(batch)
    if not config:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No source uploaded yet.")
    return await service.analyze(batch, config)


@router.get("/batches/{batch_id}/mappings/suggest")
async def suggest_mapping_for_entity(
    batch_id: UUID,
    entity_type: MigrationEntityType,
    clinic_id: UUID = Depends(require_clinic_context),
    current_user: User = Depends(require_migration_role),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    service = MigrationService(db)
    batch = await _get_batch_or_404(service, batch_id, clinic_id)
    config = _connection_config_for_batch(batch)
    adapter = get_adapter(batch.source_type, config)
    await adapter.connect()
    try:
        schema = await adapter.analyze_schema()
    finally:
        await adapter.close()
    source_fields = schema.get(entity_type.value, [])
    return suggest_mappings(entity_type, source_fields)


@router.get("/batches/{batch_id}/mappings", response_model=list[MigrationFieldMappingRead])
async def get_mappings(
    batch_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    current_user: User = Depends(require_migration_role),
    db: AsyncSession = Depends(get_db),
) -> list[MigrationFieldMapping]:
    mapping_service = MappingService(db)
    return await mapping_service.list_mappings(batch_id, clinic_id)


@router.put("/batches/{batch_id}/mappings", response_model=list[MigrationFieldMappingRead])
async def put_mappings(
    batch_id: UUID,
    payload: MigrationFieldMappingBulkUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    current_user: User = Depends(require_migration_role),
    db: AsyncSession = Depends(get_db),
) -> list[MigrationFieldMapping]:
    mapping_service = MappingService(db)
    rows = await mapping_service.replace_mappings(batch_id, clinic_id, [m.model_dump() for m in payload.mappings])
    await db.commit()
    return rows


async def _load_rows_for_entity(batch: MigrationBatch, entity_type: MigrationEntityType) -> list[dict[str, Any]]:
    config = _connection_config_for_batch(batch)
    adapter = get_adapter(batch.source_type, config)
    await adapter.connect()
    try:
        rows: list[dict[str, Any]] = []
        async for chunk in adapter.read_table(entity_type.value, batch_size=1000):
            rows.extend(chunk)
        return rows
    finally:
        await adapter.close()


@router.post("/batches/{batch_id}/validate", response_model=list[MigrationValidationIssueRead])
async def validate_batch(
    batch_id: UUID,
    entity_type: MigrationEntityType,
    clinic_id: UUID = Depends(require_clinic_context),
    current_user: User = Depends(require_migration_role),
    db: AsyncSession = Depends(get_db),
) -> list[MigrationValidationIssue]:
    service = MigrationService(db)
    batch = await _get_batch_or_404(service, batch_id, clinic_id)
    rows = await _load_rows_for_entity(batch, entity_type)
    mappings = await MappingService(db).list_mappings(batch_id, clinic_id)
    await db.execute(
        MigrationValidationIssue.__table__.delete().where(
            MigrationValidationIssue.migration_batch_id == batch_id, MigrationValidationIssue.entity_type == entity_type
        )
    )
    issues = await service.validate_entity(batch, entity_type, rows, mappings)
    batch.status = MigrationBatchStatus.VALIDATED
    batch.total_warnings = sum(1 for i in issues if i.severity.value == "Warning")
    batch.total_errors = sum(1 for i in issues if i.severity.value == "Error")
    await db.commit()
    return issues


@router.post("/batches/{batch_id}/preview", response_model=MigrationPreviewResponse)
async def preview_batch(
    batch_id: UUID,
    entity_type: MigrationEntityType,
    clinic_id: UUID = Depends(require_clinic_context),
    current_user: User = Depends(require_migration_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = MigrationService(db)
    batch = await _get_batch_or_404(service, batch_id, clinic_id)
    rows = await _load_rows_for_entity(batch, entity_type)
    mappings = await MappingService(db).list_mappings(batch_id, clinic_id)
    existing = (await db.execute(
        select(MigrationValidationIssue).where(
            MigrationValidationIssue.migration_batch_id == batch_id, MigrationValidationIssue.entity_type == entity_type
        )
    )).scalars().all()
    if not existing:
        await service.validate_entity(batch, entity_type, rows, mappings)
        await db.commit()
    counts = await service.preview_entity(batch, entity_type, len(rows))
    batch.status = MigrationBatchStatus.PREVIEWED
    await db.commit()
    return {"entity_type": entity_type, **counts}


@router.patch("/batches/{batch_id}/issues/{issue_id}/resolve", response_model=MigrationValidationIssueRead)
async def resolve_issue(
    batch_id: UUID,
    issue_id: UUID,
    payload: MigrationIssueResolveRequest,
    clinic_id: UUID = Depends(require_clinic_context),
    current_user: User = Depends(require_migration_role),
    db: AsyncSession = Depends(get_db),
) -> MigrationValidationIssue:
    issue = (await db.execute(
        select(MigrationValidationIssue).where(MigrationValidationIssue.id == issue_id, MigrationValidationIssue.clinic_id == clinic_id, MigrationValidationIssue.migration_batch_id == batch_id)
    )).scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Validation issue not found")
    issue.resolution = payload.resolution
    issue.resolved_by = current_user.id
    issue.resolved_at = datetime.now(UTC)
    await db.commit()
    return issue


async def _run_import(batch_id: uuid.UUID, clinic_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    """Background task: runs every implemented entity in the mandated
    17-step order, using a fresh session (the request's session is closed
    by the time this runs)."""
    async with AsyncSessionLocal() as session:
        service = MigrationService(session)
        batch = await service.get_batch(batch_id, clinic_id)
        if batch is None:
            return
        batch.status = MigrationBatchStatus.IMPORTING
        batch.started_at = batch.started_at or datetime.now(UTC)
        await session.commit()

        actor = await session.get(User, actor_id)
        mappings = await MappingService(session).list_mappings(batch_id, clinic_id)
        had_failure = False

        for entity_type in MIGRATION_ENTITY_ORDER:
            batch = await service.get_batch(batch_id, clinic_id)
            if batch.status == MigrationBatchStatus.CANCELLED:
                break
            entity_mappings = [m for m in mappings if m.entity_type == entity_type]
            if entity_type not in IMPLEMENTED_ENTITIES and not entity_mappings:
                # No mapping configured and not implemented - skip silently.
                progress = await service.get_or_create_progress(batch, entity_type)
                progress.status = MigrationEntityProgressStatus.SKIPPED
                await session.commit()
                continue
            rows = await _load_rows_for_entity(batch, entity_type)
            if not rows:
                continue
            issues = list((await session.execute(
                select(MigrationValidationIssue).where(
                    MigrationValidationIssue.migration_batch_id == batch_id, MigrationValidationIssue.entity_type == entity_type
                )
            )).scalars().all())
            try:
                await service.import_entity(
                    batch, entity_type, rows, mappings, issues, actor=actor,
                    migration_source_label=f"{batch.source_type.value}:{batch.source_description or ''}",
                )
            except Exception:  # noqa: BLE001
                had_failure = True
                continue

        batch = await service.get_batch(batch_id, clinic_id)
        entities = await service.entity_progress(batch_id, clinic_id)
        batch.total_records_imported = sum(e.records_imported for e in entities)
        batch.total_duplicates = sum(e.records_skipped for e in entities)
        batch.total_errors = sum(e.records_failed for e in entities)
        batch.completed_at = datetime.now(UTC)
        batch.status = (
            MigrationBatchStatus.PARTIALLY_COMPLETED if had_failure else MigrationBatchStatus.COMPLETED
        )
        await AuditService(session).log_event(
            clinic_id=clinic_id, user_id=actor_id, action="migration.batch_completed",
            entity_type="migration_batch", entity_id=str(batch_id),
            metadata={"status": batch.status.value, "total_imported": batch.total_records_imported},
        )
        await session.commit()


@router.post("/batches/{batch_id}/import", response_model=MigrationBatchRead)
async def start_import(
    batch_id: UUID,
    background_tasks: BackgroundTasks,
    clinic_id: UUID = Depends(require_clinic_context),
    current_user: User = Depends(require_migration_role),
    db: AsyncSession = Depends(get_db),
) -> MigrationBatch:
    service = MigrationService(db)
    batch = await _get_batch_or_404(service, batch_id, clinic_id)
    batch.status = MigrationBatchStatus.IMPORTING
    await db.commit()
    background_tasks.add_task(_run_import, batch_id, clinic_id, current_user.id)
    return batch


@router.post("/batches/{batch_id}/resume", response_model=MigrationBatchRead)
async def resume_import(
    batch_id: UUID,
    background_tasks: BackgroundTasks,
    clinic_id: UUID = Depends(require_clinic_context),
    current_user: User = Depends(require_migration_role),
    db: AsyncSession = Depends(get_db),
) -> MigrationBatch:
    """Import is idempotent per-batch (resumes from `last_processed_offset`
    automatically), so resume is the same operation as import."""
    return await start_import(batch_id, background_tasks, clinic_id, current_user, db)


@router.post("/batches/{batch_id}/retry-batch", response_model=MigrationEntityProgressRead)
async def retry_entity(
    batch_id: UUID,
    entity_type: MigrationEntityType,
    background_tasks: BackgroundTasks,
    clinic_id: UUID = Depends(require_clinic_context),
    current_user: User = Depends(require_migration_role),
    db: AsyncSession = Depends(get_db),
) -> MigrationEntityProgress:
    service = MigrationService(db)
    batch = await _get_batch_or_404(service, batch_id, clinic_id)
    progress = await service.get_or_create_progress(batch, entity_type)
    progress.status = MigrationEntityProgressStatus.PENDING
    progress.last_processed_offset = 0
    progress.records_failed = 0
    await db.commit()
    background_tasks.add_task(_run_import, batch_id, clinic_id, current_user.id)
    return progress


@router.post("/batches/{batch_id}/cancel", response_model=MigrationBatchRead)
async def cancel_batch(
    batch_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    current_user: User = Depends(require_migration_role),
    db: AsyncSession = Depends(get_db),
) -> MigrationBatch:
    service = MigrationService(db)
    batch = await _get_batch_or_404(service, batch_id, clinic_id)
    batch.status = MigrationBatchStatus.CANCELLED
    await db.commit()
    return batch


@router.get("/batches/{batch_id}/status", response_model=MigrationStatusResponse)
async def get_status(
    batch_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    current_user: User = Depends(require_migration_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = MigrationService(db)
    batch = await _get_batch_or_404(service, batch_id, clinic_id)
    entities = await service.entity_progress(batch_id, clinic_id)

    elapsed = None
    eta = None
    if batch.started_at:
        now = datetime.now(UTC)
        started = batch.started_at if batch.started_at.tzinfo else batch.started_at.replace(tzinfo=UTC)
        elapsed = (now - started).total_seconds()
        total_found = sum(e.records_found for e in entities) or batch.total_records_found or 0
        total_done = sum(e.records_imported + e.records_skipped + e.records_failed for e in entities)
        if total_done > 0 and elapsed > 0 and total_found > total_done:
            rate = total_done / elapsed
            eta = (total_found - total_done) / rate if rate > 0 else None

    return {
        "batch": batch,
        "entities": entities,
        "elapsed_seconds": elapsed,
        "estimated_seconds_remaining": eta,
    }


@router.get("/batches/{batch_id}/verify", response_model=MigrationVerificationReport)
async def verify_batch(
    batch_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    current_user: User = Depends(require_migration_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = MigrationService(db)
    batch = await _get_batch_or_404(service, batch_id, clinic_id)
    return await service.verify(batch)


@router.get("/batches/{batch_id}/logs", response_model=list[MigrationLogRead])
async def get_logs(
    batch_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    current_user: User = Depends(require_migration_role),
    db: AsyncSession = Depends(get_db),
) -> list:
    service = MigrationService(db)
    await _get_batch_or_404(service, batch_id, clinic_id)
    return await service.logs(batch_id, clinic_id)
