"""Connectivity Service - Post-RC1 Phase 2 Milestone 1: Cloud Readiness.

Groundwork/plumbing only: this service DETECTS and DISPLAYS connectivity
state for a future hybrid (local + cloud) deployment. It does not implement
any data synchronization, does not gate any business logic, and does not
actually use `CLOUD_DATABASE_URL` for anything - see `docs/FEATURES.md` for
the full milestone scope and `app/core/config.py` for the related settings.

State is tracked in-memory (module-level), following the "in-memory is fine
for Milestone 1" guidance in the milestone spec - there is exactly one
backend process per clinic install today (no multi-instance/HA setup this
needs to survive a restart for), so a simple in-process singleton is the
least machinery that satisfies the requirement. A background asyncio task
(started at app startup, see `app/main.py`) refreshes this state every
`CHECK_INTERVAL_SECONDS`; `GET /api/v1/system/status` (see
`app/api/v1/system_status.py`) also refreshes on-demand so a poll never
returns stale data older than one request-response cycle.
"""

import asyncio
import logging
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from sqlalchemy import text

from app.core.config import settings
from app.db.session import AsyncSessionLocal

logger = logging.getLogger("app.connectivity")

CHECK_INTERVAL_SECONDS = 45
HTTP_CHECK_TIMEOUT_SECONDS = 3.0
INTERNET_CHECK_HOST = "8.8.8.8"
INTERNET_CHECK_PORT = 53
INTERNET_CHECK_TIMEOUT_SECONDS = 2.0


@dataclass
class ConnectivityState:
    deployment_mode: str = settings.DEPLOYMENT_MODE
    local_status: str = "up"
    cloud_status: str = "not_configured"  # "up" | "down" | "not_configured"
    database_status: str = "unknown"  # "reachable" | "unreachable"
    internet_status: str = "unknown"  # "reachable" | "unreachable"
    last_successful_cloud_connection: datetime | None = None
    last_checked_at: datetime | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)


_state = ConnectivityState()


async def check_database() -> bool:
    """Reuses the exact same cheap `SELECT 1` reachability check that the
    existing `GET /ready` probe (`app/api/v1/health.py`) already performs -
    intentionally not duplicated/reimplemented, just called from here too."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:  # pragma: no cover - exercised via manual DB-down check
        return False


async def check_internet() -> bool:
    """Basic outbound connectivity check: a single lightweight TCP connect
    attempt to a well-known, highly-reliable external host/port (Google
    Public DNS, port 53). Deliberately not a full network-diagnostics
    system - one cheap check is enough for Milestone 1."""
    try:
        await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None, lambda: socket.create_connection((INTERNET_CHECK_HOST, INTERNET_CHECK_PORT), timeout=INTERNET_CHECK_TIMEOUT_SECONDS).close()
            ),
            timeout=INTERNET_CHECK_TIMEOUT_SECONDS + 1,
        )
        return True
    except Exception:
        return False


async def check_cloud() -> tuple[str, bool]:
    """Returns (status, reached) where status is one of "up"/"down"/"not_configured".

    If `CLOUD_API_URL` is not configured, this is a neutral/expected state
    for clinics running fully local today - NOT an error - so it is reported
    distinctly from "down" rather than lumped in with it.
    """
    if not settings.CLOUD_API_URL:
        return "not_configured", False
    try:
        async with httpx.AsyncClient(timeout=HTTP_CHECK_TIMEOUT_SECONDS) as client:
            response = await client.get(settings.CLOUD_API_URL.rstrip("/") + "/health")
        if response.status_code < 500:
            return "up", True
        return "down", False
    except Exception:
        return "down", False


async def refresh_state() -> ConnectivityState:
    """Runs all checks and updates the shared in-memory state. Safe to call
    both from the periodic background loop and on-demand from the status
    endpoint (guarded by a lock so concurrent callers don't race)."""
    async with _state._lock:
        previous_cloud_status = _state.cloud_status

        db_ok = await check_database()
        internet_ok = await check_internet()
        cloud_status, cloud_ok = await check_cloud()

        _state.database_status = "reachable" if db_ok else "unreachable"
        _state.internet_status = "reachable" if internet_ok else "unreachable"
        _state.cloud_status = cloud_status
        _state.local_status = "up"  # trivially true: this code is running
        _state.deployment_mode = settings.DEPLOYMENT_MODE
        _state.last_checked_at = datetime.now(timezone.utc)
        if cloud_ok:
            _state.last_successful_cloud_connection = datetime.now(timezone.utc)

        # Post-RC1 Phase 2 Milestone 2: Cloud Backup - "Internet Recovery"
        # hook. When cloud connectivity transitions from down/not_configured
        # -> up, immediately wake the sync worker rather than making a
        # queued backlog wait for its next periodic tick. Lazy import to
        # avoid a circular import (sync_worker_service reads this module's
        # state); best-effort - never lets a sync-worker issue break the
        # connectivity check itself.
        if previous_cloud_status != "up" and cloud_status == "up":
            try:
                from app.services import sync_worker_service

                sync_worker_service.trigger_sync_now()
            except Exception:
                logger.exception("Failed to trigger sync worker on cloud recovery")

        return _state


def get_state() -> ConnectivityState:
    return _state


async def _background_loop() -> None:  # pragma: no cover - exercised via manual/live verification
    while True:
        try:
            await refresh_state()
        except Exception:
            logger.exception("Connectivity background check failed")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


_background_task: asyncio.Task | None = None


def start_background_loop() -> None:
    """Starts the periodic polling loop. Idempotent - safe to call multiple
    times (e.g. across test app instantiations); only ever holds one task."""
    global _background_task
    if _background_task is None or _background_task.done():
        loop = asyncio.get_event_loop()
        _background_task = loop.create_task(_background_loop())


def stop_background_loop() -> None:
    global _background_task
    if _background_task is not None:
        _background_task.cancel()
        _background_task = None
