"""Docker-native database backup for the Docker Server PC production
architecture (`docker/docker-compose.yml` + `docker/docker-compose.prod.yml`,
run via the repo-root `deploy.cmd`).

`scripts/backup_and_prune.py` (the original Phase 11 script) cannot reach
this database: it shells out to a *host-installed* `pg_dump` binary against
`DATABASE_URL`'s host/port, but `docker-compose.prod.yml` deliberately
removes Postgres' host port publishing (`postgres.ports: !reset []`) - only
the internal Docker network can reach it. This script instead runs
`pg_dump` INSIDE the Postgres container itself, via `docker exec` - no host
`pg_dump` binary, no host-reachable port, and no compose project-name
resolution needed, since `docker exec` addresses the container by its
fixed, explicit `container_name` (`connectph-postgres` by default),
regardless of which Compose project it belongs to.

Reuses the *exact same* dump-verification (`verify_dump_file`) and
retention (`select_backups_to_delete`) logic as the original script - see
that module's own docstring for why a single shared verification/retention
implementation matters. Deliberately does NOT reuse `find_pg_dump`/
`parse_db_url_for_pg_tools` (host-oriented, not applicable here).

Usage (run from `backend/`, using the same venv the app runs in):

    python scripts/backup_docker.py
    python scripts/backup_docker.py --backup-dir "D:\\ClinicBackups"
    python scripts/backup_docker.py --container connectph-postgres \\
        --db-user connectph --db-name canora_clinic

Writes to the SAME `backend/backups/backup_log.txt` the original script
uses (one shared, chronological backup history regardless of which
mechanism produced a given entry), but its own dump files are named with a
distinct `docker-backup-` prefix (vs. `scheduled-backup-`) so each script's
retention pass only ever considers - and only ever deletes - backups it
produced itself.

Exit code 0 on a verified successful backup, 1 on any failure - callers
(the Docker Server PC updater) must stop immediately, and must never
attempt a migration, on a non-zero exit here.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.backup_retention import BackupFileInfo, select_backups_to_delete  # noqa: E402
from app.services.backup_verification import verify_dump_file  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_BACKUP_DIR = _REPO_ROOT / "backend" / "backups"
LOG_FILE_NAME = "backup_log.txt"
_BACKUP_FILENAME_PREFIX = "docker-backup-"

DEFAULT_CONTAINER = "connectph-postgres"
DEFAULT_DB_USER = "connectph"
DEFAULT_DB_NAME = "canora_clinic"


def _log(log_path: Path, message: str) -> None:
    line = f"{datetime.now(UTC).isoformat()} {message}"
    print(line)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _existing_backups(backup_dir: Path) -> list[BackupFileInfo]:
    infos = []
    for path in backup_dir.glob(f"{_BACKUP_FILENAME_PREFIX}*.sql"):
        # Filename shape: docker-backup-YYYYMMDDTHHMMSS.sql
        stem = path.stem[len(_BACKUP_FILENAME_PREFIX) :]
        try:
            created_at = datetime.strptime(stem, "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
        except ValueError:
            continue  # not one of ours - leave it alone, never delete
        infos.append(BackupFileInfo(identifier=str(path), created_at=created_at))
    return infos


def _container_is_running(container: str) -> tuple[bool, str]:
    """Returns (is_running, detail). A clear "container isn't up" message
    beats a confusing `pg_dump: connection refused` one - this is checked
    first so the failure log line actually says what's wrong."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        return False, "the `docker` CLI is not on PATH"
    except Exception as exc:
        return False, f"docker inspect raised: {exc}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[:300]
        return False, f"container {container!r} not found ({detail})"
    if result.stdout.strip() != "true":
        return False, f"container {container!r} exists but is not running"
    return True, ""


def run(
    *,
    backup_dir: Path,
    container: str,
    db_user: str,
    db_name: str,
    keep_daily: int,
    keep_weekly: int,
    keep_monthly: int,
) -> int:
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"FAILED: could not create backup directory {backup_dir}: {exc}", file=sys.stderr)
        return 1
    log_path = backup_dir / LOG_FILE_NAME
    started_at = datetime.now(UTC)

    is_running, detail = _container_is_running(container)
    if not is_running:
        _log(log_path, f"FAILED: Docker backup aborted - {detail}. No dump was attempted.")
        return 1

    dest = backup_dir / f"{_BACKUP_FILENAME_PREFIX}{started_at.strftime('%Y%m%dT%H%M%S')}.sql"

    try:
        with open(dest, "wb") as f:
            result = subprocess.run(
                ["docker", "exec", container, "pg_dump", "-U", db_user, "--format=plain", db_name],
                stdout=f, stderr=subprocess.PIPE, timeout=300,
            )
    except Exception as exc:
        _log(log_path, f"FAILED: docker exec pg_dump invocation raised: {exc}")
        return 1

    if result.returncode != 0:
        stderr = (result.stderr or b"").decode(errors="ignore").strip()[:500]
        _log(log_path, f"FAILED: docker exec pg_dump exited {result.returncode}: {stderr}")
        # Leave the (bad/partial) file for inspection rather than deleting it silently.
        return 1

    is_valid, error_message = verify_dump_file(dest)
    if not is_valid:
        _log(log_path, f"FAILED: verification failed: {error_message} (file: {dest})")
        return 1

    size = dest.stat().st_size
    _log(
        log_path,
        f"SUCCESS: Docker backup verified ({size} bytes, container={container!r}, "
        f"database={db_name!r}) at {dest}",
    )

    # Retention only runs after a confirmed-successful backup, and only
    # ever considers this script's own docker-backup-* files.
    existing = _existing_backups(backup_dir)
    to_delete = select_backups_to_delete(
        existing, now=started_at, keep_daily=keep_daily,
        keep_weekly=keep_weekly, keep_monthly=keep_monthly,
    )
    deleted, delete_errors = 0, 0
    for identifier in to_delete:
        try:
            Path(identifier).unlink()
            deleted += 1
        except OSError as exc:
            delete_errors += 1
            _log(log_path, f"WARNING: could not delete old backup {identifier}: {exc}")
    _log(
        log_path,
        f"Retention: kept {len(existing) + 1 - deleted} docker backup(s), "
        f"deleted {deleted}, {delete_errors} deletion error(s).",
    )

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a verified Docker-native PostgreSQL backup (docker exec pg_dump) "
        "and apply retention."
    )
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument(
        "--container", default=DEFAULT_CONTAINER,
        help=f"Postgres container name (default: {DEFAULT_CONTAINER}, "
        "matching docker-compose.yml's container_name).",
    )
    parser.add_argument(
        "--db-user", default=DEFAULT_DB_USER,
        help=f"Database role to dump as (default: {DEFAULT_DB_USER}).",
    )
    parser.add_argument(
        "--db-name", default=DEFAULT_DB_NAME,
        help=f"Database to dump (default: {DEFAULT_DB_NAME}, matching docker-compose.prod.yml).",
    )
    parser.add_argument("--keep-daily", type=int, default=7)
    parser.add_argument("--keep-weekly", type=int, default=4)
    parser.add_argument("--keep-monthly", type=int, default=6)
    args = parser.parse_args()
    return run(
        backup_dir=args.backup_dir, container=args.container, db_user=args.db_user,
        db_name=args.db_name, keep_daily=args.keep_daily,
        keep_weekly=args.keep_weekly, keep_monthly=args.keep_monthly,
    )


if __name__ == "__main__":
    sys.exit(main())
