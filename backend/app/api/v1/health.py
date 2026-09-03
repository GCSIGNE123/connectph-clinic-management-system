"""Health / readiness / liveness probes.

Phase 16 (Production Hardening) adds `/ready` and `/live` alongside the
existing `/health` (kept for backward compatibility - existing tooling and
`docs/TESTING.md`'s manual-verification notes already reference it):

- `/health` - original combined check. Also reports the deployed Git
  commit (`git_commit`/`git_commit_short`/`deployed_at`, all `null` unless
  `deploy/windows/update_server.bat` has run - see `app/core/deploy_info.py`).
- `/live` - liveness probe: the process is up and able to answer HTTP at
  all. No dependencies (no DB call) - a container orchestrator uses this to
  decide whether to restart the process; it must never depend on anything
  that could be slow or transiently down, or a flaky dependency would cause
  unnecessary restarts of an otherwise-healthy process.
- `/ready` - readiness probe: the process is up AND its real dependency
  (Postgres) is reachable, via a cheap `SELECT 1`. Returns `503` (not `200`
  with an error body) when the DB is unreachable, so a load balancer/
  orchestrator correctly stops routing traffic to this instance without
  restarting it (that's `/live`'s job, not `/ready`'s).

Both are registered with no auth dependency - these are infra probes hit by
orchestrators/load balancers, never by an end user or clinic session.
"""

import time

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.deploy_info import get_deploy_info
from app.db.session import AsyncSessionLocal

router = APIRouter(tags=["health"])

_process_start = time.monotonic()


@router.get("/health")
async def health_check() -> dict[str, object]:
    # `git_commit`/`git_commit_short`/`deployed_at` answer "what's actually
    # running on this machine" - see `app/core/deploy_info.py`. Added here
    # (not just on the auth-gated `/system/status`) so `check_health.bat`
    # and `deploy/windows/update_server.bat` can read the deployed commit
    # with no token at all - this is deployment metadata, not sensitive
    # data. `None` for every deploy_info field on a machine that has never
    # run `update_server.bat` (e.g. a dev checkout) is expected, not a bug.
    return {"status": "ok", **get_deploy_info()}


@router.get("/live")
async def liveness() -> dict[str, object]:
    """Trivial process-alive check - no dependencies, always fast."""
    return {"status": "alive", "uptime_seconds": round(time.monotonic() - _process_start, 2)}


@router.get("/ready")
async def readiness(response: Response) -> dict[str, object]:
    """Readiness probe - verifies the database is actually reachable."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready", "database": "reachable"}
    except Exception as exc:  # pragma: no cover - exercised via manual DB-down check
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "database": "unreachable", "detail": str(exc)}
