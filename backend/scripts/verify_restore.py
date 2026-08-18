"""Phase 11: safe, non-destructive restore-drill verification.

Restores a given dump file into a FRESH TEMPORARY database (never the
configured production/dev database), runs a handful of integrity checks,
then drops the temporary database again. The real database this script's
own `DATABASE_URL` config points at is NEVER written to, restored into,
or dropped - see `_assert_not_production_db` below, which refuses to run
at all if the computed temporary database name were ever to collide with
the configured one.

Usage (run from `backend/`, using the same venv the app runs in):

    python scripts/verify_restore.py "backend/backups/scheduled-backup-20260101T020000.sql"

What it does, in order (matches docs/BACKUP.md's documented restore-drill
procedure exactly, so this script is that procedure automated for the
"is this backup actually restorable" check specifically - it does not
replace the human-executed real restore procedure for an actual disaster,
see docs/BACKUP.md):

  1. Creates `<original_db_name>_restore_verify_<timestamp>` via `createdb`.
  2. Restores the given dump into it via `psql -f <dump>`.
  3. Confirms `alembic_version` has exactly one row (schema is at a real
     migration head, not empty/partial).
  4. Row-counts a handful of key tables (`clinics`, `patients`, `visits`)
     and prints them - not asserted against a fixed expected count (this
     script doesn't know what the dump *should* contain), but a table that
     errors out (doesn't exist) or a clinics count of 0 on a dump that's
     supposed to contain real data is a clear, visible red flag either way.
  5. Drops the temporary database in a `finally` block - always attempted,
     even if an earlier step failed, so a failed drill doesn't leave litter
     behind for the next one to collide with.

Exit code 0 if every check passed, 1 otherwise.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.services.backup_verification import find_pg_dump, parse_db_url_for_pg_tools  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

CHECK_TABLES = ["clinics", "patients", "visits"]


def _find_bin(repo_root: Path, name: str) -> str | None:
    """Same PATH-then-portable-distribution lookup as `find_pg_dump`, for
    the other libpq CLI tools this script needs (`createdb`/`psql`/
    `dropdb`) - `pg_dump`'s own portable-fallback path is a sibling of
    these in the same `.devdb/pgsql/bin/` directory."""
    import shutil

    on_path = shutil.which(name)
    if on_path:
        return on_path
    candidate = repo_root / ".devdb" / "pgsql" / "bin" / f"{name}.exe"
    return str(candidate) if candidate.exists() else None


def _assert_not_production_db(temp_db_name: str, real_db_name: str) -> None:
    if temp_db_name == real_db_name:
        raise RuntimeError(
            f"Refusing to run: computed temp database name {temp_db_name!r} collides with the "
            f"configured production/dev database {real_db_name!r}. This should be structurally "
            "impossible (the temp name always has a '_restore_verify_<timestamp>' suffix) - "
            "aborting rather than risk touching the real database."
        )


def verify_restore(dump_path: Path) -> bool:
    if not dump_path.exists():
        print(f"FAIL: dump file does not exist: {dump_path}")
        return False

    createdb_bin = _find_bin(_REPO_ROOT, "createdb")
    psql_bin = _find_bin(_REPO_ROOT, "psql")
    dropdb_bin = _find_bin(_REPO_ROOT, "dropdb")
    if not all([createdb_bin, psql_bin, dropdb_bin]):
        print("FAIL: could not locate createdb/psql/dropdb (checked PATH and .devdb/pgsql/bin/).")
        return False

    args, env, real_db_name = parse_db_url_for_pg_tools(settings.DATABASE_URL)
    temp_db_name = f"{real_db_name}_restore_verify_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
    _assert_not_production_db(temp_db_name, real_db_name)

    created = False
    try:
        print(f"Creating temporary database {temp_db_name!r}...")
        create_result = subprocess.run(
            [createdb_bin, *args, temp_db_name], env=env, capture_output=True, text=True, timeout=60
        )
        if create_result.returncode != 0:
            print(f"FAIL: createdb failed: {create_result.stderr.strip()}")
            return False
        created = True

        print(f"Restoring {dump_path} into {temp_db_name!r}...")
        restore_result = subprocess.run(
            [psql_bin, *args, "--dbname", temp_db_name, "--file", str(dump_path), "--set", "ON_ERROR_STOP=1"],
            env=env, capture_output=True, text=True, timeout=600,
        )
        if restore_result.returncode != 0:
            print(f"FAIL: restore failed: {restore_result.stderr.strip()[:1000]}")
            return False

        ok = True

        alembic_check = subprocess.run(
            [psql_bin, *args, "--dbname", temp_db_name, "--tuples-only", "--command", "SELECT count(*) FROM alembic_version"],
            env=env, capture_output=True, text=True, timeout=30,
        )
        if alembic_check.returncode != 0 or alembic_check.stdout.strip() != "1":
            print(f"FAIL: alembic_version does not have exactly one row (got: {alembic_check.stdout.strip()!r}).")
            ok = False
        else:
            print("PASS: alembic_version has exactly one row (schema at a real migration head).")

        for table in CHECK_TABLES:
            count_result = subprocess.run(
                [psql_bin, *args, "--dbname", temp_db_name, "--tuples-only", "--command", f"SELECT count(*) FROM {table}"],
                env=env, capture_output=True, text=True, timeout=30,
            )
            if count_result.returncode != 0:
                print(f"FAIL: could not query table {table!r}: {count_result.stderr.strip()}")
                ok = False
            else:
                print(f"INFO: {table} row count = {count_result.stdout.strip()}")

        return ok
    finally:
        if created:
            print(f"Dropping temporary database {temp_db_name!r}...")
            drop_result = subprocess.run(
                [dropdb_bin, *args, temp_db_name], env=env, capture_output=True, text=True, timeout=60
            )
            if drop_result.returncode != 0:
                print(f"WARNING: could not drop temporary database {temp_db_name!r}: {drop_result.stderr.strip()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely verify a backup dump is restorable, without touching the real database.")
    parser.add_argument("dump_path", type=Path)
    args = parser.parse_args()
    ok = verify_restore(args.dump_path)
    print("RESULT: PASS" if ok else "RESULT: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
