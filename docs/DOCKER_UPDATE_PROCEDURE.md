# Updating a Docker-Based Server PC (Canora Medical Clinic)

This document is the authoritative runbook for updating the **actual
Canora Medical Clinic Server PC** (`D:\ClinicCMS`, Docker Desktop) from one
approved GitHub commit to the next. It exists because that machine's real
architecture — Docker Compose (`docker/docker-compose.yml` +
`docker/docker-compose.prod.yml`), containers `connectph-postgres` /
`connectph-redis` / `connectph-backend` / `connectph-frontend` — was
discovered to be **completely different** from the NSSM/manual-
Windows-process architecture that [`UPDATE_PROCEDURE.md`](UPDATE_PROCEDURE.md)
and `deploy\windows\update_server.bat` were built for. **Do not use
`update_server.bat` on this machine** — see "Why two updaters exist" below.

## Which updater do I actually run?

| This Server PC has... | Use |
|---|---|
| Docker Desktop, containers named `connectph-postgres`/`connectph-backend`/`connectph-frontend`, no `backend\.venv` | **This document** — run `deploy.cmd` (repo root) |
| `backend\.venv`, NSSM services `CONNECTPH-Postgres`/`CONNECTPH-Backend`/`CONNECTPH-Frontend`, a portable Postgres under `.devdb\` | [`UPDATE_PROCEDURE.md`](UPDATE_PROCEDURE.md) — run `deploy\windows\update_server.bat` |

**Canora Medical Clinic is the first row.** If you are unsure which
architecture a given machine uses, check for Docker Desktop running and
`docker ps` showing the four containers above — do not guess, and do not
run both updaters against the same machine.

## Prerequisites (Server PC)

- Docker Desktop installed and running.
- The repository is a real `git clone` (not a ZIP copy) — `git branch
  --show-current` must print `main`.
- A repo-root `.env` exists (copied from `.env.example`, real
  `POSTGRES_PASSWORD` filled in) — `deploy.cmd` refuses to run without it.
- `backend\.env` exists on the host and is already correctly configured —
  it is mounted into the `connectph-backend` container via `env_file:`,
  never baked into the image, never touched by this updater.
- **One-time only, before the very first run of this updated `deploy.cmd`
  on this specific machine**: the volume-identity verification below.

## Volume identity — one-time verification (do this before the first run)

`docker/docker-compose.prod.yml` now pins the production Postgres/Redis/
attachment volumes to fixed names (`canora_postgres_data`,
`canora_redis_data`, `canora_backend_var_data`) and pins the Compose
project name itself (`name: canora_clinic`) — this closes a real gap found
during the Docker-architecture investigation: without an explicit name,
Docker prefixes every named volume with whatever the *Compose project
name* happens to resolve to, which by default is derived from the current
working directory a `docker compose` command happens to be run from. That
name has, until now, never been pinned anywhere — so this machine's
**real, already-running** database volume may exist under a different,
implicit name.

**Before running the new `deploy.cmd` on this machine for the first time**,
a human must run (read-only, changes nothing):

```
docker volume ls
```

- **If `canora_postgres_data` is already in the list** — nothing to do,
  proceed normally.
- **If it is NOT in the list, but some other `*_postgres_data` volume is**
  (e.g. `clinicms_postgres_data`, `docker_postgres_data`) — **stop**. This
  is very likely the real, existing clinic database under its old implicit
  name. `deploy.cmd`'s own preflight check (`:check_volume_protection`)
  will refuse to proceed automatically rather than risk creating a fresh
  empty volume in its place, but a human still needs to resolve it, by one
  of:
  1. **Rename the volume's contents** (Docker has no in-place volume
     rename): create the new named volume, then copy the old volume's data
     into it with a disposable container —
     ```
     docker volume create canora_postgres_data
     docker run --rm -v <old_name>:/from -v canora_postgres_data:/to alpine sh -c "cp -a /from/. /to/."
     ```
     Verify the copy (e.g. spin up a throwaway `postgres:16-alpine`
     container against `canora_postgres_data` and check `psql -l`) before
     ever pointing production at it. Repeat the same pattern for
     `redis_data`/`backend_var_data` if they're also under an old name.
  2. **Or**, set `COMPOSE_PROJECT_NAME_OVERRIDE=<old project name>` in the
     repo-root `.env` instead — this makes `deploy.cmd` pass `-p <old
     project name>` on every `docker compose` invocation, which resolves
     the OLD implicit volume names again (a CLI `-p` flag always wins over
     a compose file's own `name:`). Simpler, no data movement — but it
     means this machine never actually adopts the new pinned name, so
     document clearly which one it uses.
- **If no `*_postgres_data` volume exists at all** — this is a genuine
  first-time bootstrap; proceed, Compose will create the new pinned
  volumes fresh.

## Running an update

```
deploy.cmd
```

Run from the repo root, by a human, after the new code has already been
reviewed and pushed from the Dev PC.

### What it does, in order

1. Confirms the repo-root `.env` exists.
2. Confirms this really is the CMS git repository.
3. Confirms the repo is on branch `main` (refuses on any other branch or a
   detached HEAD).
4. Confirms the working tree is clean — refuses otherwise.
5. Fetches GitHub and fast-forwards (`git merge --ff-only` — never a hard
   reset, never a force-checkout, never `git clean`), recording old/new SHA.
6. Compares old vs. new commit to see what changed, **and separately asks
   the currently-running backend container what commit it's actually
   serving** (`GET /api/v1/health`'s `git_commit` field) — forces a
   rebuild+restart whenever these disagree, even when git alone reports
   "already up to date". See "Repository state vs. running deployment
   state" below.
7. Validates the merged production Compose configuration
   (`docker compose --env-file .env -f docker/docker-compose.yml -f
   docker/docker-compose.prod.yml config`).
8. Runs the volume-identity preflight check (read-only `docker volume ls`)
   — refuses to proceed if the pinned volume doesn't exist yet AND a
   differently-named one already does (see above).
9. Rebuilds **only** the backend and/or frontend image whose inputs
   actually changed (or that step 6 determined is already stale).
10. **If** any file under `backend\alembic\versions` changed: takes a
    Docker-native backup first (`docker exec connectph-postgres pg_dump
    ...`, verified — see "Backup" below), then runs `docker exec
    connectph-backend python -m alembic upgrade head`. A failure here stops
    the whole script immediately — see "Migration behavior" below.
11. Restarts/recreates **only** the containers whose image was actually
    rebuilt or that just received a migration — `docker compose ... up -d
    --no-deps <service>`, so **postgres and redis are never restarted** for
    an ordinary application update.
12. Shows `docker compose ps`.
13. Waits for `/api/v1/ready` to actually respond (polled, not a fixed sleep).
14. Runs health checks: the Postgres container's own `pg_isready`, backend
    `/health` + `/ready`, frontend `/`, the CORS login-preflight check
    (unchanged from the original `deploy.cmd`), and — critically — confirms
    the **running** backend now reports the **new** commit, not just that
    `git log` on disk changed.
15. Appends one line to `deploy\docker\logs\update-history.log`.
16. Prints a clear `DEPLOYMENT SUCCESS` / `DEPLOYMENT FAILED` result.

### What it refuses to do

- **Never** `git reset --hard`, `git checkout -f`, `git clean -fd`, or
  `git clean -fdx`.
- **Never** `docker compose down`, `down -v`, `docker volume rm`, or
  `docker system prune` (with or without `--volumes`) — nothing that can
  delete a named volume. Building/restarting `backend`/`frontend` with
  `--no-deps` cannot touch `postgres`/`redis` at all.
- **Never** touches `backend\.env`, the repo-root `.env`, or any frontend
  production env file — Compose `env_file:`/variable substitution only
  ever *reads* these, and this script never writes to them.
- **Never** proceeds over an uncommitted/dirty working tree, a repo not on
  `main`, or an unresolved production-volume-identity mismatch.
- **Never** restarts a container after a failed migration.
- **Never** attempts an automatic database downgrade/rollback.
- **Never** reports success merely because `git` fast-forwarded — the
  final health-check step re-verifies the *running* container's reported
  commit before declaring success.

## Repository state vs. running deployment state

This is the property that matters most about this updater, and the reason
it exists in this exact shape. `git merge --ff-only` succeeding only
proves the **files on disk** changed — it proves nothing about whether the
currently-running `connectph-backend`/`connectph-frontend` containers were
ever rebuilt from those files. They weren't, until step 9/11 actually run.

This was not a hypothetical concern: this Server PC's repository was
manually fast-forwarded from `41b854218e1c0fcf00321cb909beb600dcf949d2` to
`0cd8dc7c383d2c8a46d1552e1b14a997b01071ec` outside of any script, before
this updater existed. On the very next run, step 5 alone would have
reported "already up to date" — true of the repository, **wrong** about
the running application, since the containers were never rebuilt from that
commit. Step 6's cross-check exists specifically to catch this class of
drift: it never trusts "HEAD == origin/main" alone, it also asks the
container itself, via `/api/v1/health`'s `git_commit` field (baked into
the image at build time, see below), which can only change when the image
is actually rebuilt and the container actually recreated from it.

## Verifying the deployed commit (Docker-correct)

`docker/Dockerfile.backend` accepts a `GIT_COMMIT` build argument and bakes
it in as a real `ENV` — `docker-compose.prod.yml` passes it through from
`deploy.cmd`'s `set GIT_COMMIT=<new sha>` right before `docker compose
build backend`. `backend/app/core/deploy_info.py` checks this environment
variable **first**, before falling back to the `deploy_info.json` file
mechanism used by the NSSM architecture — see that module's own docstring.

This means the reported commit only ever changes when a **new image is
actually built and the container actually recreated from it** — exactly
the property needed to distinguish repository state from running state. A
plain `git pull` on the host, by itself, changes nothing `/api/v1/health`
or `/api/v1/system/status` report.

```
curl http://localhost:8000/api/v1/health
```

or the System Status page in the app (Owner/Administrator) — both read the
same `get_deploy_info()`.

## Migration behavior

- Detected the same way as the NSSM architecture: whether any file under
  `backend/alembic/versions` changed between the old and new commit.
- **A verified backup is always taken first**, via `docker exec
  connectph-postgres pg_dump` (see "Backup" below) — never skipped, never
  optional.
- If the backup fails, the migration is **not attempted at all**.
- `docker exec connectph-backend python -m alembic upgrade head` then runs
  **inside the backend container** (not host Python — this machine has no
  `backend\.venv` and the container already has the app's dependencies).
  Note `docker/Dockerfile.backend`'s own image `CMD` would normally run
  this same command automatically before `uvicorn` starts — the
  production compose override (`docker-compose.prod.yml`'s
  `backend.command:`) deliberately skips that so migrations stay a
  separate, deliberate, backed-up step, never an implicit side effect of a
  container restart.
- A migration failure stops the script immediately — containers are
  **not** restarted, so the previously-running image keeps serving traffic
  rather than running against an unknown/partially-migrated schema.
- No automatic downgrade is ever attempted.

## Backup (Docker-native)

**The original `deploy\windows\run_backup.bat` cannot reach this
database** — it shells out to a *host-installed* `pg_dump` against
`DATABASE_URL`'s host/port, but production Postgres publishes **no host
port** (`docker-compose.prod.yml`'s `postgres.ports: !reset []`) and this
machine has no host Python/venv to run it from anyway. `deploy.cmd`'s own
`:docker_backup` subroutine instead runs entirely via `docker exec
connectph-postgres pg_dump -U connectph --format=plain canora_clinic`,
redirected straight to a host file — no host `pg_dump` binary, no
host-reachable DB port, no Python required anywhere on the host.

- **Where it's stored**: `backend\backups\docker-backup-<timestamp>.sql`
  (same directory the NSSM architecture's backups use, distinguished by
  the `docker-backup-` filename prefix vs. `scheduled-backup-`), logged to
  the same `backend\backups\backup_log.txt`.
- **Verification**: non-empty file, and the real `pg_dump` header
  (`PostgreSQL database dump`) present — checked before the migration is
  ever allowed to run.
- **Retention**: this gating backup step does **not** apply retention
  (old `docker-backup-*.sql` files simply accumulate) — a known,
  deliberate simplification, since retention logic (in
  `app.services.backup_retention`) needs the app's Python dependencies,
  which this host does not have installed outside the containers. A fuller
  Python-based equivalent with the same retention/verification logic as
  the original script — `backend\scripts\backup_docker.py` — exists for
  any host that *does* have Python + the backend's dependencies installed
  (e.g. run from the Dev PC against a reachable clinic Docker host, or if
  Python is separately provisioned on the Server PC later for a scheduled
  Task Scheduler backup analogous to `run_backup.bat`'s daily schedule).
  Until then, an operator should periodically clear old
  `docker-backup-*.sql` files manually — they are never deleted
  automatically by `deploy.cmd`.
- **Restore**: same manual, human-executed procedure as
  `docs/BACKUP.md` §4, adapted for Docker — restore into a *new* database
  first and verify before pointing production at it:
  ```
  docker exec -i connectph-postgres psql -U connectph -d postgres -c "CREATE DATABASE canora_clinic_restore_check;"
  docker exec -i connectph-postgres psql -U connectph -d canora_clinic_restore_check < backend\backups\docker-backup-<timestamp>.sql
  ```
  Verify the restored data looks correct, then only proceed to restore
  into the real `canora_clinic` database (stop the backend container
  first, then `docker exec -i connectph-postgres psql -U connectph -d
  canora_clinic < <file>.sql`, then restart it) with a human directly
  watching — never automated, exactly the same philosophy as
  `docs/BACKUP.md`.

## Service/container restart logic

| Change detected | postgres | redis | backend | frontend |
|---|---|---|---|---|
| Backend code/deps changed | — | — | rebuild + restart | — |
| Frontend code/deps changed | — | — | — | rebuild + restart |
| Migration applied | — | — | restart (already rebuilt or not, either way) | — |
| Running container's SHA doesn't match repo HEAD (bootstrap/drift) | — | — | rebuild + restart | rebuild + restart |
| Nothing changed and running SHA already matches | — | — | — | — |

`--no-deps` on every `docker compose ... up -d` call means Postgres/Redis
are **structurally** never touched by an application update, regardless of
what changed.

## After a failed update

The console output and the `DEPLOYMENT FAILED` banner say exactly which
step failed and where the detailed log is
(`deploy\docker\logs\update-<timestamp>.log`).

- **Failed at step 1–8 (env/repo/branch/tree/fetch/merge/config/volume
  checks)**: nothing was built or restarted — the old containers are still
  running, untouched.
- **Failed at step 9 (image build)**: code was pulled via git, but no
  image was rebuilt from it — the previous image/container is still what's
  actually serving traffic.
- **Failed at step 10 (migration)**: the most serious case — see
  "Rollback" below. Do not restart containers manually. Do not attempt a
  manual `alembic downgrade` without understanding what actually failed.
- **Failed at step 11–14 (restart/health)**: the image may already be
  rebuilt, but a container isn't coming up cleanly or isn't serving the
  expected commit yet — check `docker compose ... logs backend`/`frontend`.

## Rollback (manual, practical, no automation)

Same philosophy as the NSSM architecture's `docs/UPDATE_PROCEDURE.md`
Rollback section — deliberately no automated reversal of code or a
database migration.

1. **Identify the previous known-good commit** — `OLD_SHA`/`NEW_SHA` are
   printed by the failed run and recorded in
   `deploy\docker\logs\update-history.log`.
2. **No migration involved** → `git checkout <OLD_SHA>` (a deliberate,
   human-run detached checkout), then `docker compose --env-file .env -f
   docker/docker-compose.yml -f docker/docker-compose.prod.yml build
   backend frontend && ... up -d --no-deps backend frontend` for that
   commit manually — or push a real revert commit and re-run `deploy.cmd`.
3. **Migration applied, something else broken** → prefer a
   forward-fixing migration over downgrading.
4. **Migration itself failed** → do not guess; `docker exec
   connectph-backend python -m alembic current` to see the schema's actual
   state, then decide between a targeted manual fix, a verified-safe
   `alembic downgrade`, or restoring the pre-migration backup step 10
   already took (see "Backup" above).
5. **When in doubt, restore from the pre-migration backup** — the backup
   taken immediately before the failed migration is the most precise
   recovery point.

## Logging and troubleshooting

| What you need | Where |
|---|---|
| "What happened on which date, success or failure" | `deploy\docker\logs\update-history.log` (one line per run) |
| "Why exactly did today's update fail" | `deploy\docker\logs\update-<timestamp>.log` (full step transcript) |
| Container logs | `docker compose --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.prod.yml logs backend` (or `frontend`/`postgres`) |
| Backup result | `backend\backups\backup_log.txt` |
| Current container status | `docker compose ... ps`, or `check_health.bat` (dual-mode, see below) |
| What commit is actually running | `GET /api/v1/health` |

`deploy\windows\check_health.bat` was made dual-mode aware — it detects
whether the machine is Docker or NSSM-based (by whether the portable
Postgres binary exists) and checks Postgres accordingly, while every other
check (`/health`, `/ready`, frontend `/`) is unchanged, since those are
plain HTTP checks that work identically on both architectures.

## Why two updaters exist

The NSSM/manual-Windows-process architecture (`update_server.bat`,
`docs/UPDATE_PROCEDURE.md`) was built first, based on the assumption that
every Server PC install would look like the local dev setup: a portable
Postgres, a backend venv, `next start`, and NSSM-registered Windows
Services. That architecture may still be real for some future install.
**It is not what Canora Medical Clinic actually runs.** Rather than force
one script to branch its entire behavior between two fundamentally
different deployment mechanisms (doubling the failure surface of every
single step), each architecture gets its own updater, sharing only what's
genuinely architecture-agnostic (health-check HTTP calls, the
verification/retention logic in `app.services.backup_*`, the general
numbered-step/SUCCESS-FAILED console convention). Neither script was
deleted — see `deploy\windows\update_server.bat`'s own header, which now
explicitly scopes it to the NSSM architecture only.
