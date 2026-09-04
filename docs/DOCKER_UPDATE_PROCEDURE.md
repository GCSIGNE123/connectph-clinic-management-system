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

## Volume identity — REQUIRED one-time setup (do this before the first run)

**Live-verified read-only evidence from the actual Canora Server PC**
(confirmed via `docker volume ls`/`docker inspect`, no changes made) showed
its already-running stack was created under Compose project name `docker`
(i.e. `docker compose` was once run from inside the `docker/` directory
rather than the repo root), giving its real, already-populated volumes
these names:

```
docker_postgres_data
docker_redis_data
docker_backend_var_data
```

with `connectph-postgres` confirmed mounted from `docker_postgres_data` and
`connectph-backend` confirmed mounted from `docker_backend_var_data`.

**`docker/docker-compose.prod.yml` declares all three volumes
`external: true`** — Compose will never create, rename, or recreate them;
it only ever attaches to a volume that already exists under exactly the
name given, and refuses outright (an ordinary Compose error, no
destructive action) if that name doesn't exist. The actual name is never
hardcoded in the compose file itself (this repo may serve more than one
clinic) — it comes from three required variables in the repo-root `.env`
(never tracked — see `.env.example`):

```
POSTGRES_VOLUME_NAME=docker_postgres_data
REDIS_VOLUME_NAME=docker_redis_data
BACKEND_VAR_VOLUME_NAME=docker_backend_var_data
```

**For the Canora Server PC specifically, these are the exact, confirmed,
correct values** — set them in that machine's `.env` exactly as shown
above before ever running the corrected `deploy.cmd`. Do not guess these
for any *other* installation — run `docker volume ls` on that machine and
use whatever it actually shows.

An earlier version of this design pinned a brand-new literal volume name
(`canora_postgres_data` etc.) instead of reusing the real ones. **That was
wrong** — it would have made Compose create a fresh, empty volume under
the new name on the very first run rather than reusing the real database,
and never reached the Server PC. It is corrected here, before ever being
used, via the `external: true` + `.env`-variable design above.

**Defense in depth** — `deploy.cmd`'s own `:check_volume_protection`
preflight (step 8) adds a second, independent, read-only layer beyond
Compose's own `external: true` refusal:

1. Confirms each of `POSTGRES_VOLUME_NAME`/`REDIS_VOLUME_NAME`/
   `BACKEND_VAR_VOLUME_NAME` actually exists via `docker volume inspect
   <exact-name>` — a single exact lookup, not a list-then-search — fails
   with a clear message, before any build starts, if it doesn't. Never
   silently creates a replacement. (An earlier version of this check used
   `docker volume ls` + `findstr /X`; that combination has a real,
   confirmed bug — see "A real bug found on first deployment" below — and
   was replaced with `docker volume inspect` specifically to eliminate it.)
2. Cross-checks that the **currently running** `connectph-postgres`
   container is actually mounted from the configured Postgres volume
   (`docker inspect`) — existence alone isn't enough; a correctly-existing-
   but-wrong name (e.g. a stale volume from testing, or another clinic's
   leftover) would pass check 1 while still being catastrophically wrong. This is the
   check that actually answers "is this the real clinic database."

### A real bug found on first deployment

The very first real run of the corrected `deploy.cmd` on the physical
Canora Server PC failed at step 8 with a **false** "volume does not exist"
— for `docker_postgres_data`, which genuinely existed and was genuinely
the volume `connectph-postgres` was mounted from (independently confirmed
via `docker volume ls` and `docker inspect` before this was reported).

**Root cause, reproduced on the Dev PC**: the original check ran `docker
volume ls --format "{{.Name}}" > file`, then `findstr /X /C:"<name>"
file`. `docker volume ls` — like any Go/Linux-style CLI — writes LF-only
line endings; `>` redirection in `cmd.exe` captures that verbatim with no
LF→CRLF translation. `findstr /X` (exact whole-line match) silently fails
to match **any** line in an LF-only-terminated file — confirmed by writing
the identical content to two files, one CRLF- and one LF-terminated:
`findstr /X` matched the CRLF file and reported no match at all against
the LF file, while `findstr /C` (a substring match, no `/X`) matched both
correctly regardless of line ending. Nothing on the Dev PC could have
caught this via inline testing — there's no real Docker CLI there to
produce genuine LF-terminated output; the earlier round's Dev-PC tests
used a mocked `docker` command whose output happened not to expose this
exact interaction.

**Fix**: replaced the `volume ls` + `findstr /X` combination with `docker
volume inspect <exact-name>` — an exact, single-volume lookup with no list
to parse and no line-ending assumption at all; existence is simply
"exited 0 or not." Re-tested on the Dev PC (this time exercising
`:check_volume_protection` directly via a mocked `docker` CLI implementing
`volume inspect`) against the exact real-server scenario — all three
volumes present under their real names, `connectph-postgres` mounted from
`docker_postgres_data` — and step 8 now passes correctly. Existence checks
for `REDIS_VOLUME_NAME`/`BACKEND_VAR_VOLUME_NAME` were also added at the
same time, for parity (the original check only verified Postgres).

A second, related fix from the same investigation: every `docker ...`
invocation in `deploy.cmd` is now prefixed with `call` (matching this
file's pre-existing `call npm ci` convention) — defensively correct
whether `docker` resolves to a real `.exe` (the normal case, and free to
add `call` for) or ever a `.cmd`/`.bat` wrapper. And every `docker compose`
invocation now passes `--env-file` with an **absolute** path
(`%CMS_ROOT%\.env`) rather than a relative `.env` — never relying on
Compose's own automatic `.env` discovery, which depends on the current
working directory a given invocation happens to have.

Both checks print the expected volume name before making any changes, and
both refuse to proceed on any mismatch.

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
7. Validates the merged production Compose configuration (`docker compose
   --env-file <repo-root>\.env -f docker/docker-compose.yml -f
   docker/docker-compose.prod.yml config` — always the repo root's absolute
   path, never relying on Compose's own `.env` auto-discovery).
8. Runs the volume-identity preflight check: confirms all three configured
   volumes exist (`docker volume inspect <name>`, one exact lookup each),
   then cross-checks that the **running** `connectph-postgres` container is
   actually mounted from the configured Postgres volume (`docker inspect`)
   — refuses to
   proceed on either failure (see "Volume identity" above).
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
