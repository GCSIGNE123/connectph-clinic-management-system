"""Phase 11: standalone, Windows-Task-Scheduler-invokable database backup.

Deliberately independent of the running FastAPI app/uvicorn process - it
must keep working (and must be scheduled) even if the app itself is down,
and it must never depend on the app being healthy to produce a backup.
Uses the exact same dump format and verification rules as the in-app
"Trigger Backup" button (`BackupService`, via the shared
`app.services.backup_verification` module) - two divergent backup formats
in one codebase is exactly the kind of restore-procedure inconsistency
this phase's investigation found in the existing documentation (see
docs/BACKUP.md's Phase 11 section) and was written specifically to avoid
here, at the implementation level.

Usage (run from `backend/`, using the same venv the app runs in):

    python scripts/backup_and_prune.py
    python scripts/backup_and_prune.py --backup-dir "D:\\ClinicBackups"
    python scripts/backup_and_prune.py --keep-daily 7 --keep-weekly 4 --keep-monthly 6

Reads `DATABASE_URL` from the app's own `.env` (via `app.core.config.
settings` - the same config loader the running app uses), so credentials
are never hardcoded into this script or any Task Scheduler action that
invokes it.

Exit code 0 on a verified successful backup, 1 on any failure - the
contract Windows Task Scheduler (or any scheduler) needs to reliably
detect and alert on a failed run, not just log it silently.

Retention is applied ONLY after a successful backup+verify, and never
deletes the single most recent backup file even in a pathological case -
see `app.services.backup_retention.select_backups_to_delete`'s explicit
invariant. If today's backup fails, retention is skipped entirely for
this run - a failed backup attempt must never be the reason a
previously-good backup gets pruned away.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.services.backup_retention import BackupFileInfo, select_backups_to_delete  # noqa: E402
from app.services.backup_verification import find_pg_dump, parse_db_url_for_pg_tools, verify_dump_file  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_BACKUP_DIR = _REPO_ROOT / "backend" / "backups"
LOG_FILE_NAME = "backup_log.txt"
_BACKUP_FILENAME_PREFIX = "scheduled-backup-"

# Phase 11 finding: on a local clinic install with no Supabase project
# configured, uploaded laboratory/consultation attachment files live on
# local disk here - entirely OUTSIDE PostgreSQL, so `pg_dump` alone never
# backs them up. Neither existing backup document (docs/BACKUP.md,
# docs/FIRST_CLINIC_INSTALLATION.md) mentioned this before Phase 11 - see
# those docs' Phase 11 sections for the full explanation. `--include-
# attachments` (default on) copies these directories alongside the DB
# dump so a technician relying on this script's output actually gets a
# complete backup, not just the database half of it.
ATTACHMENT_DIRS = ["var/laboratory_attachments", "var/consultation_attachments"]


def _log(log_path: Path, message: str) -> None:
    line = f"{datetime.now(UTC).isoformat()} {message}"
    print(line)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _existing_backups(backup_dir: Path) -> list[BackupFileInfo]:
    infos = []
    for path in backup_dir.glob(f"{_BACKUP_FILENAME_PREFIX}*.sql"):
        # Filename shape: scheduled-backup-YYYYMMDDTHHMMSS.sql
        stem = path.stem[len(_BACKUP_FILENAME_PREFIX):]
        try:
            created_at = datetime.strptime(stem, "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
        except ValueError:
            continue  # not one of ours (e.g. a manual-trigger file) - leave it alone, never delete
        infos.append(BackupFileInfo(identifier=str(path), created_at=created_at))
    return infos


def _copy_attachment_dirs(backup_dir: Path, log_path: Path, started_at: datetime) -> None:
    """Best-effort: copies each existing attachment directory into a
    timestamped subfolder of the backup directory. Never fails the overall
    backup run - the database dump (already verified by this point) is
    the higher-priority artifact; a missing/unreadable attachments
    directory is logged as a warning, not treated as a backup failure,
    since plenty of installs may have zero attachments so far (nothing to
    copy is not an error)."""
    dest_root = backup_dir / f"attachments-{started_at.strftime('%Y%m%dT%H%M%S')}"
    any_copied = False
    for rel_dir in ATTACHMENT_DIRS:
        source = _REPO_ROOT / "backend" / rel_dir
        if not source.exists():
            continue
        try:
            shutil.copytree(source, dest_root / Path(rel_dir).name, dirs_exist_ok=True)
            any_copied = True
        except OSError as exc:
            _log(log_path, f"WARNING: could not copy attachment directory {source}: {exc}")
    if any_copied:
        _log(log_path, f"Attachments copied to {dest_root}")


def run(*, backup_dir: Path, keep_daily: int, keep_weekly: int, keep_monthly: int, include_attachments: bool = True) -> int:
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # Destination unreachable (drive not mounted, permission denied, a
        # regular file blocking the path, etc.) - there is no log file to
        # write to yet, so fail loudly to stderr instead of letting an
        # unhandled traceback stand in for a clean failure. Exit code 1 is
        # what actually matters for schtasks/alerting, but the caller
        # should never see a raw traceback for an expected failure mode.
        print(f"FAILED: could not create backup directory {backup_dir}: {exc}", file=sys.stderr)
        return 1
    log_path = backup_dir / LOG_FILE_NAME
    started_at = datetime.now(UTC)

    pg_dump_path = find_pg_dump(_REPO_ROOT)
    if pg_dump_path is None:
        _log(log_path, "FAILED: pg_dump not found on PATH and no portable .devdb copy present.")
        return 1

    dest = backup_dir / f"{_BACKUP_FILENAME_PREFIX}{started_at.strftime('%Y%m%dT%H%M%S')}.sql"
    args, env, dbname = parse_db_url_for_pg_tools(settings.DATABASE_URL)

    try:
        result = subprocess.run(
            [pg_dump_path, *args, "--dbname", dbname, "--format=plain", "--file", str(dest)],
            env=env, capture_output=True, text=True, timeout=300,
        )
    except Exception as exc:
        _log(log_path, f"FAILED: pg_dump invocation raised: {exc}")
        return 1

    if result.returncode != 0:
        _log(log_path, f"FAILED: pg_dump exited {result.returncode}: {(result.stderr or '').strip()[:500]}")
        return 1

    is_valid, error_message = verify_dump_file(dest)
    if not is_valid:
        _log(log_path, f"FAILED: verification failed: {error_message} (file: {dest})")
        # Do not delete the invalid file - leave it for inspection; do not
        # run retention either, since this run did not produce a good
        # backup to retain in the first place.
        return 1

    size = dest.stat().st_size
    _log(log_path, f"SUCCESS: backup verified ({size} bytes, database={dbname!r}) at {dest}")

    if include_attachments:
        _copy_attachment_dirs(backup_dir, log_path, started_at)

    # Retention only runs after a confirmed-successful backup.
    existing = _existing_backups(backup_dir)
    to_delete = select_backups_to_delete(
        existing, now=started_at, keep_daily=keep_daily, keep_weekly=keep_weekly, keep_monthly=keep_monthly
    )
    deleted, delete_errors = 0, 0
    for identifier in to_delete:
        try:
            Path(identifier).unlink()
            deleted += 1
        except OSError as exc:
            # Retention-cleanup failure must never fail the run - the new
            # backup already succeeded and is what matters most; a stale
            # old file left behind is a minor disk-space issue, not data
            # loss, and is safe to retry on the next scheduled run.
            delete_errors += 1
            _log(log_path, f"WARNING: could not delete old backup {identifier}: {exc}")
    _log(log_path, f"Retention: kept {len(existing) + 1 - deleted} backup(s), deleted {deleted}, {delete_errors} deletion error(s).")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a verified PostgreSQL backup and apply retention.")
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR, help="Destination directory for backup files.")
    parser.add_argument("--keep-daily", type=int, default=7)
    parser.add_argument("--keep-weekly", type=int, default=4)
    parser.add_argument("--keep-monthly", type=int, default=6)
    parser.add_argument(
        "--no-attachments", dest="include_attachments", action="store_false",
        help="Skip copying laboratory/consultation attachment directories (database-only backup).",
    )
    args = parser.parse_args()
    return run(
        backup_dir=args.backup_dir, keep_daily=args.keep_daily, keep_weekly=args.keep_weekly,
        keep_monthly=args.keep_monthly, include_attachments=args.include_attachments,
    )


if __name__ == "__main__":
    sys.exit(main())
