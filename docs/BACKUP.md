# Backup & Restore

This document covers how CONNECT.PH's database backups are triggered/verified, how to schedule them on the real clinic Windows machine, retention, attachment-file coverage, and the human-executable restore procedure. Restore is deliberately **never automated** anywhere in this codebase — see the rationale below.

---

## Quick reference (read this first in an emergency)

| Question | Answer |
|---|---|
| **Where is today's backup?** | `backend\backups\scheduled-backup-<timestamp>.sql` (scheduled) or `backend\backups\backup-<timestamp>-<id>.sql` (manually triggered via Platform Admin). Change the destination folder in `deploy\windows\run_backup.bat` if backups are pointed at a second drive — check there first if unsure. |
| **How do I know the backup failed?** | Check `backend\backups\backup_log.txt` (every run appends a `SUCCESS`/`FAILED` line) and Windows Task Scheduler's "Last Run Result" for the backup task (non-zero = failed). A failed backup never silently looks like a success — see §1. |
| **The Server PC died. How do I restore the CMS?** | Reinstall on a new/repaired machine per `docs/LOCAL_DEPLOYMENT.md`, then follow §3's restore procedure using the most recent verified backup file, then §5's attachment-restore step. |
| **The database is corrupted. How do I restore it?** | Stop the CMS services, follow §3 below against the same machine. |
| **How do I move the clinic onto another Windows PC?** | Full install per `docs/LOCAL_DEPLOYMENT.md` on the new PC, then §3's restore procedure pointed at the new PC's Postgres instance, then copy the attachment directories (§5) across. |
| **How do I know a restored database is actually usable?** | Run `deploy\windows\run_restore_drill.bat "<dump-file>"` (§4) — restores into a disposable temporary database and checks it, without touching anything live. |

---

## 1. Backup: real, automated, verified

Two ways to trigger a backup exist, and **both produce the exact same dump format and pass through the exact same verification logic** (`app/services/backup_verification.py`, shared code, not duplicated) — this was a real inconsistency risk this document and the codebase had before Phase 11 (see the historical note at the end of this section) and is now closed:

1. **Manual, in-app**: `POST /api/v1/platform-admin/backups` (PlatformAdministrator-only) triggers a `pg_dump` against the live database via `app/services/backup_service.py`, records a `backups` table row (`Completed`/`Failed`), and is visible via `GET /api/v1/platform-admin/backups`. Good for an on-demand "back up right before I do something risky" backup.
2. **Scheduled, standalone**: `backend/scripts/backup_and_prune.py`, invoked by `deploy/windows/run_backup.bat` — see §2 for scheduling this via Windows Task Scheduler. Deliberately independent of the running FastAPI app (works even if the app is down/crashed), and additionally applies retention (§3 below) and copies attachment directories (§5).

Both use the plain-SQL format (`--format=plain`), restored via `psql -f <dump>.sql` (§4 below) — **not** `pg_restore` (that tool is for custom/directory/tar-format dumps, which this project does not produce; using it against this project's output fails outright).

**Verification** — a file existing is never treated as a successful backup. Every dump is checked for, in order:
1. `pg_dump`'s subprocess exit code is `0`.
2. The output file exists and is non-empty.
3. The output file starts with the real PostgreSQL dump preamble (`-- PostgreSQL database dump`) — a truncated/corrupted file with a coincidentally-zero exit code fails this check.

Any failure at any step is logged with a clear reason (`backups` table `error_message` for the manual path; `backend/backups/backup_log.txt` for the scheduled path) — never silently reported as success.

## 2. Scheduling (Windows Task Scheduler)

The real clinic deployment target is a local Windows machine (`docs/LOCAL_DEPLOYMENT.md`) — Windows Task Scheduler is the correct, native mechanism for a daily job, not a new always-running service/daemon.

**Setup** (run once on the clinic Server PC, as the user - not by Claude, per this project's standing rule that deployment commands on the physical Server PC are executed by a human, not an agent):

```
schtasks /create /tn "CONNECT.PH Daily Backup" /tr "\"<repo-path>\deploy\windows\run_backup.bat\"" /sc daily /st 02:00 /ru SYSTEM
```

- Runs daily at 2:00 AM (adjust `/st` for the clinic's actual quiet hours).
- `run_backup.bat` calls `scripts/backup_and_prune.py`, which: runs the backup, verifies it, copies attachment directories, and applies retention — all in one invocation, all logged to `backend\backups\backup_log.txt`.
- Exits non-zero on any failure, so Task Scheduler's own "Last Run Result" column reliably shows whether last night's backup actually worked — check it (or the log file) periodically, e.g. weekly.
- Never touches the running backend/frontend Windows Services — `pg_dump` reads the live database without requiring app downtime.

**Backup destination**: `deploy\windows\run_backup.bat`'s `BACKUP_DEST` variable defaults to `backend\backups\` (same disk as the live database) purely so this works out of the box with zero configuration. **If a second physical drive/destination is available on the clinic machine, point `BACKUP_DEST` at it** — a backup on the same disk as the live Postgres data directory protects against nothing (a disk failure takes both down together). This project does not assume or require any specific cloud provider, NAS, or sync tool for that second destination — whatever the clinic actually has available (a second internal drive, a USB drive left permanently attached, a mapped network share) works; just point the variable at it.

## 3. Retention policy

`scripts/backup_and_prune.py` applies a Grandfather-Father-Son (daily/weekly/monthly) policy by default, implemented in `app/services/backup_retention.py` (pure, unit-tested function — see `app/tests/test_backup_verification.py`):

- **Daily**: every backup from the last 7 days is kept.
- **Weekly**: for backups older than 7 days but within the last 4 weeks, only the oldest backup of each calendar week survives.
- **Monthly**: for backups older than that but within the last 6 months, only the oldest backup of each calendar month survives.
- Anything older than that is deleted.

**Why these numbers**: a single-clinic installation generates at most one backup a day, and the realistic recovery scenarios are (a) "restore from yesterday/last week" (covered by the 7-day daily window), (b) "something has been subtly wrong for a few weeks and we need an older-but-not-ancient snapshot" (the weekly buckets), and (c) "we need to go back months for an audit/legal reason" (the monthly buckets, capped at 6 months as a reasonable starting point — extend `--keep-monthly` if the clinic's own record-retention policy requires longer). These are a starting recommendation, not a hard requirement — override via `--keep-daily`/`--keep-weekly`/`--keep-monthly` CLI flags if the clinic's needs differ.

**Failure safety** (the most important property): retention only ever runs *after* a confirmed-successful, verified backup for that run — a failed backup attempt never triggers cleanup at all. Independently of that, `select_backups_to_delete` is structurally incapable of selecting the single most recent backup for deletion, even if called with a list where every other backup has already expired — see that function's docstring and its dedicated test coverage. A run of consecutive failed backup attempts (e.g. disk full, Postgres down) never results in the last known-good backup being pruned away.

## 4. Restore procedure (human-executable, never automated)

**This procedure is intentionally NOT exposed via any API endpoint, script, or button in this codebase.** Restoring a dump overwrites live data. In a multi-tenant system where every clinic's data lives in the same database, an automated or accidental restore could silently roll back every tenant's data to the dump's point in time — that is exactly the kind of destructive, irreversible action this project's own operating rules (and this session's) require a human at the controls for, not an autonomous agent or a one-click UI action.

### Step-by-step (adapt paths/credentials for your environment)

1. **Stop application traffic** to the target database (stop the backend/frontend Windows Services via `deploy\windows\stop_clinic.bat`, or put the app in maintenance mode) — restoring into a database that's still receiving writes will produce a corrupted, inconsistent result.
2. **Confirm you have the right dump file** — check its filename timestamp and, if in doubt, `head -c 500 <file>` to confirm it starts with `-- PostgreSQL database dump` and inspect the `-- Dumped from database version` / `-- Started on` lines for sanity.
3. **Create a fresh, empty target database** (never restore directly into a database with live data still in it unless you have independently confirmed you intend to overwrite it entirely and have a separate, verified backup of the pre-restore state first):
   ```bash
   createdb -h <host> -p <port> -U <user> connectph_clinic_restored
   ```
4. **Restore the dump** — `psql`, not `pg_restore` (this project's dumps are plain-SQL format):
   ```bash
   psql -h <host> -p <port> -U <user> -d connectph_clinic_restored -f <path-to-dump>.sql
   ```
5. **Verify the restore before cutting over** — either manually (below) or automated via the restore-drill script (§5):
   - Confirm `alembic_version` in the restored database matches the migration head you expect (`SELECT * FROM alembic_version;`).
   - Spot-check row counts on a few key tables (`SELECT count(*) FROM patients;`, `SELECT count(*) FROM clinics;`) against what you expect from the dump's known point in time.
   - If restoring into a database with a different name than production (`connectph_clinic_restored` above), do NOT point the running application at it until you've fully verified it — rename/swap only after verification passes.
6. **Cut over**: update `DATABASE_URL` to point at the verified restored database (or rename the databases so the restored one takes the production name), then restart the application.
7. **Restore attachment files** (§6) — the database restore alone does NOT bring back uploaded laboratory/consultation attachment files; copy them back from the same backup run's attachment directory.
8. **Resume traffic** and monitor closely (error rates, `/ready` probe, a manual smoke test of login + one core workflow) for the first several minutes after cutover.

### What NOT to do

- Do not run a restore against the database an application is actively writing to.
- Do not skip step 5 (verification) "to save time" — an unverified restore that turns out to be from the wrong point in time or a corrupted dump is worse than no restore, because it looks like a success until someone notices missing/wrong data later.
- Do not automate this procedure into a script that runs without a human explicitly invoking and watching each step.

## 5. Safe restore-drill verification (non-destructive)

`scripts/verify_restore.py` (wrapped by `deploy\windows\run_restore_drill.bat`) automates the "is this backup actually restorable" check — **without ever touching the real database**:

```
deploy\windows\run_restore_drill.bat "backend\backups\scheduled-backup-20260101T020000.sql"
```

What it does: creates a throwaway temporary database (`<real-db-name>_restore_verify_<timestamp>`), restores the dump into it via `psql`, checks `alembic_version` has exactly one row and prints row counts for `clinics`/`patients`/`visits`, then drops the temporary database — always, even on failure. It structurally refuses to run at all if the computed temporary name ever collided with the real configured database name.

Run this periodically (e.g. monthly, or after any real disaster-recovery drill) against the latest backup to confirm dumps are genuinely restorable, not just non-empty — a backup that has never been test-restored is not a verified backup.

**Point-in-time recovery (PITR)**: `pg_dump` snapshots are a single point in time. This project does not implement WAL archiving/continuous backup — a failure between two backup runs loses any changes made in between (up to 24 hours of data with the default daily schedule). If this gap is unacceptable for a specific clinic's risk tolerance, that requires a separate, larger infrastructure decision (e.g. a managed Postgres provider with built-in PITR) — not something this phase implements.

## 6. Attachment files (Phase 11 finding — not covered by `pg_dump` alone)

**Uploaded laboratory and consultation attachment files are stored on local disk, entirely outside PostgreSQL, on a local clinic install with no Supabase project configured** — `backend/var/laboratory_attachments/` and `backend/var/consultation_attachments/` (see `app/api/v1/laboratory.py`/`app/api/v1/consultations.py`). **`pg_dump` never backs these up.** This was not documented anywhere before Phase 11 — a technician following only the database backup procedure above would silently lose every uploaded lab result image/consultation attachment in a disk failure, with no warning.

- **Scheduled backups** (`scripts/backup_and_prune.py`, the default/recommended path): copies both attachment directories into `backend\backups\attachments-<timestamp>\` alongside every successful database dump, automatically — no separate step needed. Disable with `--no-attachments` if not wanted.
- **Manual in-app backups** (`POST /platform-admin/backups`): database-only, does **not** copy attachments — use the scheduled script (or a manual file copy of `backend/var/`) if an attachment backup is needed at that moment.
- **Restoring attachments**: after restoring the database (§4), copy the matching backup run's `attachments-<timestamp>\laboratory_attachments\` and `\consultation_attachments\` folders back to `backend/var/laboratory_attachments/` and `backend/var/consultation_attachments/` respectively.
- **Cloud/VPS deployment** (`docs/DEPLOYMENT.md`): if Supabase Storage is configured for file uploads instead of local disk, attachments are backed up by Supabase's own storage durability/backup mechanisms, not this procedure — confirm this explicitly for any deployment that isn't the default local-disk clinic install.

## 7. Backup security

- **Credentials are never hardcoded** into any backup script — both `scripts/backup_and_prune.py` and `scripts/verify_restore.py` read `DATABASE_URL` from the app's own `.env` via `app.core.config.settings`, the same config loader the running app uses. The database password is passed to `pg_dump`/`psql`/`createdb`/`dropdb` via the `PGPASSWORD` environment variable, never as a command-line argument (which would be visible in a process list).
- **Backup files contain real patient/billing data in plain text** (the dump format is human-readable SQL) — treat every `.sql` backup file with the same access-control sensitivity as the live database itself. Restrict filesystem permissions on the backup destination directory to the same principals who could otherwise access the live database (e.g. the clinic's designated IT administrator, not all logged-in Windows accounts on the machine).
- **Encryption at rest**: not implemented by this project's backup scripts. If the backup destination (a second drive, a network share) doesn't already provide disk-level encryption, consider enabling Windows BitLocker (or equivalent) on that destination — this is an operating-system-level control, not something this codebase should reimplement.
- **Logs never contain secrets or raw patient data** — `backup_log.txt` records only timestamps, file sizes, byte counts, and error messages (e.g. "pg_dump exited 1: <stderr excerpt>"), never database credentials or dump content.

---

## Historical note (pre-Phase 11 documentation inconsistency, now resolved)

Before Phase 11, this document's own restore procedure (`psql -f <dump>.sql`, correct for `BackupService`'s plain-format output) coexisted with a **separate, uncoordinated** recommendation in `docs/FIRST_CLINIC_INSTALLATION.md` to manually schedule `pg_dump -F c` (custom format) backups, restored via `pg_restore --clean` — a fundamentally different, incompatible dump format from what the app's own `BackupService` actually produces. Following the wrong restore tool against the wrong format's dump would fail outright, in the worst possible moment (an actual disaster). Phase 11 closed this by (a) building one authoritative, shared-verification-logic backup path (`scripts/backup_and_prune.py`, plain format, matching `BackupService`) intended for scheduled use, and (b) updating `docs/FIRST_CLINIC_INSTALLATION.md` to point at it instead of its own divergent recommendation — see that document's Backup & Restore section.
