"""Phase 11: shared, pure backup-dump verification logic.

Extracted out of `backup_service.py` so the API-triggered manual backup
(`BackupService.run_backup`, async, DB-aware) and the standalone scheduled
backup script (`scripts/backup_and_prune.py`, sync, no DB session) apply
the *exact same* verification rules - a dump file is never considered
successful just because a subprocess exited 0 and a file exists.

Pure functions only (no I/O beyond reading the file itself, no async, no
DB) - trivially unit-testable without a real Postgres instance.
"""

from pathlib import Path

DUMP_HEADER_MARKER = "PostgreSQL database dump"


def verify_dump_file(path: Path) -> tuple[bool, str | None]:
    """Returns (is_valid, error_message). `error_message` is None when
    `is_valid` is True. Checks, in order: the file exists, is non-empty,
    and starts with the real pg_dump preamble - the same three checks
    `BackupService.run_backup` already applied inline before this
    extraction, now shared with the standalone scheduled script."""
    if not path.exists():
        return False, "Dump file does not exist."
    size = path.stat().st_size
    if size == 0:
        return False, "pg_dump produced an empty file."
    header = path.read_text(encoding="utf-8", errors="ignore")[:200]
    if DUMP_HEADER_MARKER not in header:
        return False, "Dump file does not start with the expected PostgreSQL dump header."
    return True, None


def find_pg_dump(repo_root: Path) -> str | None:
    """Locates a usable `pg_dump` binary: PATH first, then this project's
    portable Postgres distribution (`.devdb/pgsql/bin/pg_dump.exe` from the
    repo root) as a fallback - the same two-step lookup `BackupService`
    already used, now shared so the standalone script doesn't duplicate
    (and risk drifting from) this logic."""
    import shutil

    on_path = shutil.which("pg_dump")
    if on_path:
        return on_path
    candidate = repo_root / ".devdb" / "pgsql" / "bin" / "pg_dump.exe"
    return str(candidate) if candidate.exists() else None


def parse_db_url_for_pg_tools(database_url: str) -> tuple[list[str], dict[str, str], str]:
    """Translates the app's `postgresql+asyncpg://user:pass@host:port/db`
    URL into CLI args + a `PGPASSWORD` env override, usable by any
    synchronous libpq CLI tool (`pg_dump`, `psql`, `createdb`, `dropdb`) -
    the password is passed via env, never as a CLI arg, so it never shows
    up in a process list or gets logged by anything that dumps argv."""
    import os
    from urllib.parse import urlparse

    parsed = urlparse(database_url.replace("postgresql+asyncpg://", "postgresql://"))
    args = [
        "--host", parsed.hostname or "localhost",
        "--port", str(parsed.port or 5432),
        "--username", parsed.username or "postgres",
        "--no-password",
    ]
    dbname = (parsed.path or "/").lstrip("/")
    env = dict(os.environ)
    if parsed.password:
        env["PGPASSWORD"] = parsed.password
    return args, env, dbname
