"""Cloud Backup API - Post-RC1 Phase 2 Milestone 2: Cloud Backup (One-Way Sync).

These routes are what a SEPARATE, cloud-hosted instance of this same
backend codebase (pointed at `CLOUD_DATABASE_URL` instead of a clinic's
local database) exposes for a clinic's LOCAL instance's background sync
worker (`app/services/sync_worker_service.py`) to call OUT to via
`CLOUD_API_URL`. There is no separately-deployed cloud instance in this dev
environment, so these routes live in the same codebase and are exercised
locally against a second throwaway database standing in for "the cloud"
(see docs/TESTING.md) - but they are genuinely deployable as-is to a real
cloud instance later; nothing here assumes it is running alongside a local
instance.

Auth: a distinct service-to-service shared secret (`X-Sync-Api-Key` header
checked against `settings.CLOUD_SYNC_API_KEY`), NOT any of this codebase's
three existing JWT principal types (clinic-staff/platform-admin/patient).
Any request without a valid key is rejected 401.

Only POST is exposed - deliberately no GET/PUT/PATCH/DELETE, so nothing can
ever ask this endpoint to read back, overwrite, or mutate on command: this
channel is local -> cloud upload only. Local's codebase has no code path
that reads FROM `CLOUD_API_URL` other than Milestone 1's connectivity
reachability ping (`app/services/connectivity_service.py::check_cloud`) -
nothing here adds one.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.synced_record import SyncedRecord
from app.schemas.backup import BackupUploadRequest, BackupUploadResponse

router = APIRouter(prefix="/backup", tags=["cloud-backup"])

# The 8 entity types this milestone's sync worker uploads, per the spec.
ALLOWED_ENTITY_TYPES = {
    "patient",
    "visit",
    "soap_note",
    "queue_ticket",
    "prescription",
    "laboratory_order",
    "laboratory_result",
    "payment",
    "shift",
}


def _require_sync_api_key(x_sync_api_key: str | None) -> None:
    if not settings.CLOUD_SYNC_API_KEY or x_sync_api_key != settings.CLOUD_SYNC_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing sync API key")


@router.post("/{entity_type}", response_model=BackupUploadResponse)
async def upload_backup_record(
    entity_type: str,
    payload: BackupUploadRequest,
    x_sync_api_key: str | None = Header(default=None, alias="X-Sync-Api-Key"),
) -> BackupUploadResponse:
    """Upsert one record snapshot into this (cloud) instance's database.

    Upsert key is `(clinic_id, entity_type, record_id)` - a later upload for
    the same record simply overwrites the stored snapshot (local always
    wins / is the sole source of truth; this cloud endpoint never merges,
    diffs, or rejects based on its own prior state).
    """
    _require_sync_api_key(x_sync_api_key)

    if entity_type not in ALLOWED_ENTITY_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown entity_type: {entity_type}")

    async with AsyncSessionLocal() as session:
        stmt = pg_insert(SyncedRecord).values(
            clinic_id=payload.clinic_id,
            entity_type=entity_type,
            record_id=payload.record_id,
            operation=payload.operation,
            payload=payload.payload,
            synced_at=datetime.now(UTC),
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_synced_records_clinic_entity_record",
            set_={
                "operation": stmt.excluded.operation,
                "payload": stmt.excluded.payload,
                "synced_at": stmt.excluded.synced_at,
            },
        )
        await session.execute(stmt)
        await session.commit()

        result = await session.execute(
            select(SyncedRecord).where(
                SyncedRecord.clinic_id == payload.clinic_id,
                SyncedRecord.entity_type == entity_type,
                SyncedRecord.record_id == payload.record_id,
            )
        )
        row = result.scalar_one()

    return BackupUploadResponse(id=row.id, entity_type=row.entity_type, record_id=row.record_id, synced_at=row.synced_at)
