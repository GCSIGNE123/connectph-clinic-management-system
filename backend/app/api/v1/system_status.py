"""System Status endpoint - Post-RC1 Phase 2 Milestone 1: Cloud Readiness,
extended in Milestone 2: Cloud Backup (One-Way Sync).

Exposes the Connectivity Service's current state (`app/services/
connectivity_service.py`) plus the Sync Queue's live stats (`sync_jobs`
table + `app/services/sync_worker_service.py`'s in-memory counters) for the
Admin System Status panel to poll. Owner and Administrator only
(`require_system_status_role`), matching every other admin-only settings
page in this codebase.

`GET /system/status` refreshes the connectivity state on-demand (rather than
only returning whatever the last background-loop tick produced) so a poll
never returns data older than one request-response cycle, then returns it
alongside a fresh read of the sync queue.
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_db, require_system_status_role
from app.core.deploy_info import get_deploy_info
from app.models.sync_job import SyncJob, SyncJobStatus
from app.schemas.system_status import SystemStatusResponse
from app.services import connectivity_service, sync_worker_service

router = APIRouter(prefix="/system", tags=["system-status"])


@router.get("/status", response_model=SystemStatusResponse, dependencies=[Depends(require_system_status_role)])
async def get_system_status(db: AsyncSession = Depends(get_db)) -> SystemStatusResponse:
    state = await connectivity_service.refresh_state()

    pending_count = (
        await db.execute(
            select(func.count()).where(
                SyncJob.status.in_([SyncJobStatus.PENDING.value, SyncJobStatus.IN_PROGRESS.value])
            )
        )
    ).scalar_one()

    retry_queue_count = (
        await db.execute(select(func.count()).where(SyncJob.retry_count > 0))
    ).scalar_one()

    last_success: datetime | None = (
        await db.execute(
            select(func.max(SyncJob.completed_at)).where(SyncJob.status == SyncJobStatus.COMPLETED.value)
        )
    ).scalar_one()

    last_failed_job = (
        await db.execute(
            select(SyncJob)
            .where(SyncJob.status == SyncJobStatus.FAILED.value)
            .order_by(SyncJob.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    deploy_info = get_deploy_info()
    return SystemStatusResponse(
        deployment_mode=state.deployment_mode,
        app_version=settings.APP_VERSION,
        git_commit=deploy_info["git_commit"],
        git_commit_short=deploy_info["git_commit_short"],
        deployed_at=deploy_info["deployed_at"],
        local_status=state.local_status,
        cloud_status=state.cloud_status,
        database_status=state.database_status,
        internet_status=state.internet_status,
        last_successful_cloud_connection=state.last_successful_cloud_connection,
        last_checked_at=state.last_checked_at,
        pending_sync_jobs=pending_count,
        last_successful_sync_at=last_success,
        last_failed_sync_at=last_failed_job.updated_at if last_failed_job else None,
        last_failed_sync_reason=last_failed_job.last_error if last_failed_job else None,
        total_uploaded_today=sync_worker_service.get_uploaded_today_count(),
        retry_queue_count=retry_queue_count,
        average_sync_time_ms=sync_worker_service.get_average_sync_time_ms(),
    )
