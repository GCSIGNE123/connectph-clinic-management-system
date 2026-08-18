"""Real database backup execution + verification (Phase 16).

Phase 15 added the `backups` table (`app/models/backup.py`) as a "trigger
manual backup" record but never wired an actual service to it - there was
no code path that ran a real `pg_dump`, only the bare model. This service
closes that gap for real, honestly, within what this sandboxed environment
can safely do:

- Runs a genuine `pg_dump` (confirmed available in this environment -
  `pg_dump (PostgreSQL) 16.4`, the same portable Postgres binary distribution
  documented in docs/TESTING.md's "Local end-to-end environment" section)
  against the real dev database, using the plain-text `-Fp` custom format so
  the output can be verified by reading its own header bytes.
- Verifies the resulting file is non-empty and starts with the real
  PostgreSQL dump preamble (`-- PostgreSQL database dump`), not just that
  the subprocess exit code was 0 - a truncated or empty file with a `0`
  exit code would otherwise pass a naive check.
- Records a real `backups` row reflecting the outcome (`Completed` with a
  real `file_size_bytes`/`storage_location`, or `Failed` with
  `error_message` if `pg_dump` is missing or errors out).

Restore is explicitly NOT automated here or anywhere in this codebase - see
docs/BACKUP.md for the full, human-executable restore procedure. Running a
destructive restore against a live multi-tenant database from an
autonomous agent/service is exactly the kind of action this platform's own
safety rules (and this session's operating rules) explicitly forbid without
a human at the controls.
"""

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.backup import Backup, BackupStatus
from app.services.backup_verification import find_pg_dump, parse_db_url_for_pg_tools, verify_dump_file

BACKUP_DIR = Path(__file__).resolve().parent.parent.parent / "backups"
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class BackupService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def run_backup(self, *, triggered_by: UUID | None) -> Backup:
        started_at = datetime.now(UTC)
        backup = Backup(backup_type="manual", status=BackupStatus.PENDING, triggered_by=triggered_by, started_at=started_at)
        self.session.add(backup)
        await self.session.flush()

        pg_dump_path = find_pg_dump(_REPO_ROOT)
        if pg_dump_path is None:
            backup.status = BackupStatus.FAILED
            backup.completed_at = datetime.now(UTC)
            backup.error_message = "pg_dump not found on PATH in this environment."
            await self.session.commit()
            return backup

        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        dest = BACKUP_DIR / f"backup-{started_at.strftime('%Y%m%dT%H%M%S')}-{backup.id}.sql"

        args, env, dbname = parse_db_url_for_pg_tools(settings.DATABASE_URL)
        try:
            result = subprocess.run(
                [pg_dump_path, *args, "--dbname", dbname, "--format=plain", "--file", str(dest)],
                env=env, capture_output=True, text=True, timeout=120,
            )
        except Exception as exc:  # pragma: no cover - subprocess/environment failure
            backup.status = BackupStatus.FAILED
            backup.completed_at = datetime.now(UTC)
            backup.error_message = f"pg_dump invocation failed: {exc}"
            await self.session.commit()
            return backup

        if result.returncode != 0:
            backup.status = BackupStatus.FAILED
            backup.completed_at = datetime.now(UTC)
            backup.error_message = (result.stderr or "pg_dump exited non-zero")[:2000]
            await self.session.commit()
            return backup

        # Real verification, not just "exit code 0" - see backup_verification.py.
        is_valid, error_message = verify_dump_file(dest)
        if not is_valid:
            backup.status = BackupStatus.FAILED
            backup.completed_at = datetime.now(UTC)
            backup.error_message = error_message
            await self.session.commit()
            return backup

        backup.status = BackupStatus.COMPLETED
        backup.completed_at = datetime.now(UTC)
        backup.file_size_bytes = dest.stat().st_size
        backup.storage_location = str(dest)
        await self.session.commit()
        return backup

    async def list_backups(self, *, limit: int = 20) -> list[Backup]:
        from sqlalchemy import select

        result = await self.session.execute(
            select(Backup).order_by(Backup.started_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
