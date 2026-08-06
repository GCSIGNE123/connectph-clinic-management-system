# Backup & Restore

This document covers how CONNECT.PH's database backups are triggered/verified today, and the human-executable restore procedure. Restore is deliberately **never automated** anywhere in this codebase — see the rationale below.

---

## 1. Backup: real, automated, verified

`app/services/backup_service.py` (Phase 16) extends Phase 15's `backups` table (which previously had no service behind it — a bare model with no code path that ever wrote a real row) with a genuine `pg_dump`-based implementation:

1. `POST /api/v1/platform-admin/backups` (PlatformAdministrator-only) triggers a real `pg_dump` against the live database, using the plain-SQL format (`--format=plain`) so the output is human-readable and independently verifiable.
2. The resulting file is checked for two things, not just a `0` exit code:
   - Non-empty (`file.stat().st_size > 0`).
   - Starts with the real PostgreSQL dump preamble (`-- PostgreSQL database dump`) — a truncated or corrupted file with a coincidentally-zero exit code would fail this check.
3. A `backups` row is written reflecting the real outcome: `Completed` with `file_size_bytes`/`storage_location` populated, or `Failed` with `error_message` set (e.g. `pg_dump not found on PATH in this environment`).
4. `GET /api/v1/platform-admin/backups` lists recent attempts (Owner/Administrator/Auditor view access).

**Verified live in this environment** (see `docs/TESTING.md`'s Phase 16 section for the full session log): `pg_dump (PostgreSQL) 16.4` is available via this environment's portable Postgres distribution (`.devdb/pgsql/bin/pg_dump.exe`, the same binaries used to run the dev database itself). A real backup was triggered and completed successfully — `601,587` bytes, header-verified, real file on disk at `backend/backups/backup-<timestamp>-<id>.sql`.

**Where dumps are stored today**: `backend/backups/` on local disk, next to the running backend process. This is adequate for a dev/demo environment and is explicitly **not** where a production deployment should leave its backups — see the production checklist below.

## 2. Production backup requirements (not yet implemented, documented for the next phase)

This sandboxed dev environment proves the `pg_dump` mechanism works; it does not implement production-grade backup *operations*. Before relying on this for a real deployment:

- **Off-host storage**: dumps must be shipped to object storage (S3/GCS/Azure Blob) or a managed Postgres provider's own backup system immediately after creation — a backup that lives on the same disk as the database it backs up does not survive the failure modes backups exist for (disk failure, host loss, ransomware).
- **Scheduling**: `POST /platform-admin/backups` is a manual trigger today. A production deployment needs this on a schedule (e.g. a cron job / scheduled task calling the endpoint, or a managed Postgres provider's built-in automated backup feature, which is generally preferable to rolling your own).
- **Retention policy**: how many backups to keep and for how long (e.g. daily for 30 days, weekly for a year) is not yet implemented — every triggered backup call creates one `backups` row and one file with no automatic pruning.
- **Restore drills**: a backup that has never been test-restored is not a verified backup. Schedule periodic restore drills against a scratch database (see the procedure below) to confirm dumps are actually restorable, not just non-empty.
- **Point-in-time recovery (PITR)**: `pg_dump` snapshots are a single point in time. A production deployment handling real patient/billing data should also enable WAL archiving / continuous backup (most managed Postgres providers offer this out of the box) so a failure between two `pg_dump` runs doesn't lose data change history.

## 3. Restore procedure (human-executable, never automated)

**This procedure is intentionally NOT exposed via any API endpoint, script, or button in this codebase.** Restoring a dump overwrites live data. In a multi-tenant system where every clinic's data lives in the same database, an automated or accidental restore could silently roll back every tenant's data to the dump's point in time — that is exactly the kind of destructive, irreversible action this project's own operating rules (and this session's) require a human at the controls for, not an autonomous agent or a one-click UI action.

### Step-by-step (dev/staging environment, adapt paths/credentials for your environment)

1. **Stop application traffic** to the target database (stop the backend process(es), or put the app in maintenance mode) — restoring into a database that's still receiving writes will produce a corrupted, inconsistent result.
2. **Confirm you have the right dump file** — check its filename timestamp and, if in doubt, `head -c 500 <file>` to confirm it starts with `-- PostgreSQL database dump` and inspect the `-- Dumped from database version` / `-- Started on` lines for sanity.
3. **Create a fresh, empty target database** (never restore directly into a database with live data still in it unless you have independently confirmed you intend to overwrite it entirely and have a separate, verified backup of the pre-restore state first):
   ```bash
   createdb -h <host> -p <port> -U <user> connectph_clinic_restored
   ```
4. **Restore the dump**:
   ```bash
   psql -h <host> -p <port> -U <user> -d connectph_clinic_restored -f <path-to-dump>.sql
   ```
5. **Verify the restore before cutting over**:
   - Confirm `alembic_version` in the restored database matches the migration head you expect (`SELECT * FROM alembic_version;`).
   - Spot-check row counts on a few key tables (`SELECT count(*) FROM patients;`, `SELECT count(*) FROM clinics;`) against what you expect from the dump's known point in time.
   - If restoring into a database with a different name than production (`connectph_clinic_restored` above), do NOT point the running application at it until you've fully verified it — rename/swap only after verification passes.
6. **Cut over**: update `DATABASE_URL` to point at the verified restored database (or rename the databases so the restored one takes the production name), then restart the application.
7. **Resume traffic** and monitor closely (error rates, `/ready` probe, a manual smoke test of login + one core workflow) for the first several minutes after cutover.

### What NOT to do

- Do not run a restore against the database an application is actively writing to.
- Do not skip step 5 (verification) "to save time" — an unverified restore that turns out to be from the wrong point in time or a corrupted dump is worse than no restore, because it looks like a success until someone notices missing/wrong data later.
- Do not automate this procedure into a script that runs without a human explicitly invoking and watching each step, in this codebase or any fork of it, until a much more mature safety net (staging-environment restore drills, automated verification, a rollback path) exists around it.
