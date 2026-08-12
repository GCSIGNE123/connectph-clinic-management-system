"""Schemas for the System Status endpoint.

Post-RC1 Phase 2 Milestone 1 (Cloud Readiness) fields plus Milestone 2
(Cloud Backup, One-Way Sync) additions: Pending Sync Jobs, Last Successful/
Failed Sync, Total Uploaded Today, Retry Queue, Average Sync Time.
"""

from datetime import datetime

from pydantic import BaseModel


class SystemStatusResponse(BaseModel):
    deployment_mode: str
    # --- Post-RC1 Phase 2.5: Production Cloud Deployment ---
    app_version: str  # backend app version string (settings.APP_VERSION / FastAPI `version=`)
    local_status: str  # "up" (trivially true if this response was returned)
    cloud_status: str  # "up" | "down" | "not_configured"
    database_status: str  # "reachable" | "unreachable"
    internet_status: str  # "reachable" | "unreachable"
    last_successful_cloud_connection: datetime | None  # None => "Never" client-side
    last_checked_at: datetime | None

    # --- Post-RC1 Phase 2 Milestone 2: Cloud Backup (One-Way Sync) ---
    pending_sync_jobs: int
    last_successful_sync_at: datetime | None
    last_failed_sync_at: datetime | None
    last_failed_sync_reason: str | None
    total_uploaded_today: int
    retry_queue_count: int
    average_sync_time_ms: float | None
