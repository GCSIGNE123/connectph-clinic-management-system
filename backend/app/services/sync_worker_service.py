"""Sync Worker Service - Post-RC1 Phase 2 Milestone 2: Cloud Backup (One-Way Sync).

Background asyncio loop (started/stopped in `app/main.py`'s lifespan,
structured the same way as Milestone 1's `connectivity_service.py`) that
drains the `sync_jobs` queue against the cloud Backup API
(`CLOUD_API_URL` + `POST /api/v1/backup/{entity_type}`, authenticated with
`CLOUD_SYNC_API_KEY`).

Only ever processes jobs when the cloud is reachable - reuses
`connectivity_service`'s own reachability state (`get_state().cloud_status`)
rather than duplicating a reachability check, per the milestone spec.
Oldest-pending-first. On failure: exponential backoff (never discards a
job). On success: marks completed, records `completed_at`/`duration_ms` for
the dashboard's "Average Sync Time" stat.

`trigger_sync_now()` is the "Internet Recovery" hook: `connectivity_service`
calls this when cloud status transitions from down/not_configured -> up, so
a queued backlog doesn't sit waiting for up to `SYNC_WORKER_INTERVAL_SECONDS`
for the next tick.

Local-mode behavior: when `CLOUD_API_URL` is unset (the default, unchanged
"local" deployment mode), `_ready_to_sync()` always returns False - the
loop still runs (cheap: one `SELECT`-free early-return per tick) but never
does any network I/O and never mutates `sync_jobs`, so a local-only clinic
is byte-for-byte behaviorally identical to before this milestone.
"""

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, update

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.sync_job import SyncJob, SyncJobStatus
from app.services import connectivity_service

logger = logging.getLogger("app.sync_worker")

# entity_type -> cloud endpoint path segment (same value today, kept as an
# explicit map so the two are free to diverge later without a data migration).
ENTITY_TYPE_PATH = {
    "patient": "patient",
    "visit": "visit",
    "soap_note": "soap_note",
    "queue_ticket": "queue_ticket",
    "prescription": "prescription",
    "laboratory_order": "laboratory_order",
    "laboratory_result": "laboratory_result",
    "payment": "payment",
    "shift": "shift",
}

_worker_task: asyncio.Task | None = None
_wake_event: asyncio.Event = asyncio.Event()

# Dashboard-facing best-effort in-memory counters (reset on process restart -
# consistent with Milestone 1's "in-memory is fine, single process per
# clinic" precedent in connectivity_service.py). Persisted facts (pending
# count, last success/fail, retry queue) are always read live from
# `sync_jobs` instead - these are only for stats that are awkward to derive
# from the table alone (Average Sync Time, Total Uploaded Today).
_uploaded_today_count = 0
_uploaded_today_date = datetime.now(UTC).date()
_sync_durations_ms: list[int] = []
MAX_TRACKED_DURATIONS = 200


def _ready_to_sync() -> bool:
    if not settings.CLOUD_API_URL or not settings.CLOUD_SYNC_API_KEY:
        return False
    return connectivity_service.get_state().cloud_status == "up"


def _next_retry_delay_seconds(retry_count: int) -> int:
    delay = settings.SYNC_RETRY_BASE_SECONDS * (2**retry_count)
    return min(delay, settings.SYNC_RETRY_MAX_SECONDS)


def _record_upload_stat(duration_ms: int) -> None:
    global _uploaded_today_count, _uploaded_today_date
    today = datetime.now(UTC).date()
    if today != _uploaded_today_date:
        _uploaded_today_date = today
        _uploaded_today_count = 0
    _uploaded_today_count += 1
    _sync_durations_ms.append(duration_ms)
    if len(_sync_durations_ms) > MAX_TRACKED_DURATIONS:
        del _sync_durations_ms[: len(_sync_durations_ms) - MAX_TRACKED_DURATIONS]


def get_uploaded_today_count() -> int:
    today = datetime.now(UTC).date()
    if today != _uploaded_today_date:
        return 0
    return _uploaded_today_count


def get_average_sync_time_ms() -> float | None:
    if not _sync_durations_ms:
        return None
    return sum(_sync_durations_ms) / len(_sync_durations_ms)


async def _process_one(job: SyncJob) -> None:
    started = time.monotonic()
    url = settings.CLOUD_API_URL.rstrip("/") + f"/api/v1/backup/{ENTITY_TYPE_PATH.get(job.entity_type, job.entity_type)}"
    body = {
        "clinic_id": str(job.clinic_id),
        "record_id": str(job.record_id),
        "operation": job.operation if isinstance(job.operation, str) else job.operation.value,
        "payload": job.payload,
    }
    async with AsyncSessionLocal() as session:
        try:
            async with httpx.AsyncClient(timeout=settings.SYNC_HTTP_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    url, json=body, headers={"X-Sync-Api-Key": settings.CLOUD_SYNC_API_KEY}
                )
            if response.status_code >= 400:
                raise RuntimeError(f"Cloud backup API returned {response.status_code}: {response.text[:500]}")

            duration_ms = int((time.monotonic() - started) * 1000)
            await session.execute(
                update(SyncJob)
                .where(SyncJob.id == job.id)
                .values(
                    status=SyncJobStatus.COMPLETED.value,
                    completed_at=datetime.now(UTC),
                    duration_ms=duration_ms,
                    last_error=None,
                )
            )
            await session.commit()
            _record_upload_stat(duration_ms)
            logger.info(
                "Sync job completed",
                extra={
                    "entity_type": job.entity_type,
                    "record_id": str(job.record_id),
                    "duration_ms": duration_ms,
                    "retry_count": job.retry_count,
                },
            )
        except Exception as exc:
            new_retry_count = job.retry_count + 1
            delay = _next_retry_delay_seconds(new_retry_count)
            next_retry_at = datetime.now(UTC) + timedelta(seconds=delay)
            await session.execute(
                update(SyncJob)
                .where(SyncJob.id == job.id)
                .values(
                    status=SyncJobStatus.FAILED.value,
                    retry_count=new_retry_count,
                    next_retry_at=next_retry_at,
                    last_error=str(exc)[:2000],
                )
            )
            await session.commit()
            logger.warning(
                "Sync job failed, will retry",
                extra={
                    "entity_type": job.entity_type,
                    "record_id": str(job.record_id),
                    "retry_count": new_retry_count,
                    "next_retry_at": next_retry_at.isoformat(),
                    "error": str(exc)[:500],
                },
            )


async def process_queue_once() -> int:
    """Processes every currently-ready job (oldest-pending-first, plus any
    FAILED job whose backoff window has elapsed). Returns the number of jobs
    attempted. Safe/no-op if the cloud isn't reachable or not configured."""
    if not _ready_to_sync():
        return 0

    now = datetime.now(UTC)
    attempted = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SyncJob)
            .where(
                (SyncJob.status == SyncJobStatus.PENDING.value)
                | (
                    (SyncJob.status == SyncJobStatus.FAILED.value)
                    & ((SyncJob.next_retry_at.is_(None)) | (SyncJob.next_retry_at <= now))
                )
            )
            .order_by(SyncJob.created_at.asc())
            .limit(100)
        )
        jobs = list(result.scalars().all())
        # Mark in_progress up front so a slow/crashed worker tick doesn't
        # double-process the same job on the next tick.
        if jobs:
            await session.execute(
                update(SyncJob)
                .where(SyncJob.id.in_([j.id for j in jobs]))
                .values(status=SyncJobStatus.IN_PROGRESS.value)
            )
            await session.commit()

    for job in jobs:
        if not _ready_to_sync():
            break
        await _process_one(job)
        attempted += 1

    return attempted


def trigger_sync_now() -> None:
    """Internet Recovery hook: called by connectivity_service when cloud
    status transitions from down/not_configured -> up, so a queued backlog
    is drained immediately instead of waiting for the next periodic tick."""
    _wake_event.set()


async def _background_loop() -> None:  # pragma: no cover - exercised via manual/live verification
    while True:
        try:
            await process_queue_once()
        except Exception:
            logger.exception("Sync worker tick failed")
        try:
            await asyncio.wait_for(_wake_event.wait(), timeout=settings.SYNC_WORKER_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass
        finally:
            _wake_event.clear()


def start_background_loop() -> None:
    global _worker_task
    if _worker_task is None or _worker_task.done():
        loop = asyncio.get_event_loop()
        _worker_task = loop.create_task(_background_loop())


def stop_background_loop() -> None:
    global _worker_task
    if _worker_task is not None:
        _worker_task.cancel()
        _worker_task = None
