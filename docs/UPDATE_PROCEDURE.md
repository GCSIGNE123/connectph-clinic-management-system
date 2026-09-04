# Updating an Installed Server PC — NSSM/Manual Architecture (Post-RC1 Phase 2.6+)

> **This document covers ONLY the NSSM/manual-Windows-process Server PC
> architecture** (portable Postgres under `.devdb\`, a `backend\.venv`,
> `next start`, three NSSM-registered Windows Services). **The actual
> Canora Medical Clinic Server PC uses a different, Docker-based
> architecture** (`docker/docker-compose.prod.yml`, containers, no
> `backend\.venv`) — for that machine, use
> [`DOCKER_UPDATE_PROCEDURE.md`](DOCKER_UPDATE_PROCEDURE.md) and
> `deploy.cmd` instead, never `update_server.bat`. See that document's
> "Which updater do I actually run?" table if you're unsure which
> architecture a given machine is.

This document is the single procedure for moving an **already-installed**
NSSM-architecture clinic Server PC from one approved GitHub commit to the
next. If you are doing the *first* install instead, see
[`FIRST_CLINIC_INSTALLATION.md`](FIRST_CLINIC_INSTALLATION.md) — this
document assumes `install_local_clinic.bat` has already been run once and
the three Windows Services already exist.

Two machines, two completely different jobs — never confuse them:

| | DEV PC | SERVER PC |
|---|---|---|
| **What happens here** | Develop, test, review, commit, push to GitHub | Pull the *approved* commit and run it in production |
| **You run** | `npm run dev` / `uvicorn --reload` / `pytest` / `vitest`, `git commit`, `git push` | `deploy\windows\update_server.bat` — nothing else |
| **Never do here** | Never run `update_server.bat` — it's a production tool, not a dev workflow shortcut | Never edit code directly, never `git commit`/`git push`, never run `npm run dev` |

**The rule of thumb: code changes happen only on the Dev PC and only reach
the Server PC by being reviewed, committed, and pushed to GitHub first. The
Server PC only ever consumes an already-approved commit — it never
originates one.**

---

## Prerequisites (Server PC)

- **The repo on this machine must be a real `git clone` of the GitHub
  repository, not a ZIP/file copy.** `update_server.bat` is a thin wrapper
  around real `git` commands (`fetch`, `merge --ff-only`, `rev-parse`,
  `diff`) — none of that works if `.git\` doesn't exist or doesn't have
  `origin` pointed at the real GitHub repository (`git remote -v` to check).
  If the Server PC was originally set up from a ZIP copy per an older
  install, re-clone it once (`git clone <repo-url>`, then copy the
  existing `.devdb\` and `.env*` files across) before using this procedure.
- The clinic install already exists per `FIRST_CLINIC_INSTALLATION.md` — the
  three Windows Services (`CONNECTPH-Postgres`, `CONNECTPH-Backend`,
  `CONNECTPH-Frontend`) are registered, `backend\.env`/`frontend\.env.production`
  are already filled in with real production values, `backend\.venv` exists.
- The repo is on branch `main` (not detached, not a different branch) —
  `git branch --show-current` on the Server PC should print `main`.
- The Server PC can reach GitHub (same network access it needed on install day).
- You are logged in as a user with permission to stop/start the three
  Windows Services (Administrator, or a user granted that specific right).
- No one is actively relying on the app for the next few minutes — an update
  briefly restarts the Backend and/or Frontend service.

## Running an update

```
cd <repo-path>
deploy\windows\update_server.bat
```

That's it — one script, no arguments needed for the normal case (it always
updates to `origin/main`'s current tip).

### What it does, in order

1. Confirms this is really the CMS git repository.
2. Confirms the working tree is clean — refuses to run otherwise (see below).
3. Fetches from GitHub.
4. Records the commit currently running (`OLD_SHA`), confirms the repo is
   on branch `main` (refuses on any other branch or a detached HEAD — this
   script only ever knows how to update `main`), and warns (does not fail)
   if this machine has local commits that were never pushed to GitHub.
5. Fast-forwards to `origin/main` (`git merge --ff-only` — see "Git safety" below).
6. Compares `OLD_SHA` → `NEW_SHA` to work out what actually changed.
7. Reinstalls backend Python dependencies **only if** `backend\pyproject.toml` changed.
8. Runs `npm ci` **only if** frontend `package.json`/`package-lock.json` changed, and
   `npm run build` **only if** any frontend source/build-input file changed.
9. **If** any file under `backend\alembic\versions` changed: takes a
   verified pre-migration backup, then runs `alembic upgrade head`. A
   failure here stops the whole script immediately — see "Migration
   behavior" below.
10. Restarts **only** the services whose inputs actually changed — Backend
    restarts on any backend `app\` code change, dependency change, or
    applied migration; Frontend rebuilds and restarts on any frontend
    source or dependency change. **PostgreSQL is never restarted** for an
    ordinary application update.
11. Writes `backend\deploy_info.json` (git commit + timestamp) — see
    "Verifying the deployed commit" below. Done *before* the health check
    so `/health`/`/system/status` already reflect the new commit by the
    time it runs.
12. Runs the existing `check_health.bat`.
13. Prints a clear `DEPLOYMENT SUCCESS` or `DEPLOYMENT FAILED` banner and
    appends one line to `deploy\windows\logs\update-history.log`.

### What it refuses to do

- **Never** `git reset --hard`, `git checkout -f`, `git clean -fd`, or
  `git clean -fdx` — nothing that could silently discard a file. Updating
  uses only `git fetch` + `git merge --ff-only`.
- **Never** proceeds over an uncommitted/dirty working tree, a repo that
  has diverged from `origin/main`, or a repo that isn't on branch `main` at
  all (a different branch, or a detached HEAD) — all three stop the script
  immediately with the exact files/commits/branch involved, so a human can
  decide what to do.
- **Never** touches `backend\.env`, `backend\.env.production`,
  `frontend\.env*`, or any other file already excluded from Git via
  `.gitignore` — Git itself only ever updates *tracked* files, so a
  fast-forward merge is structurally incapable of changing them.
- **Never** restarts Backend/Frontend after a failed migration.
- **Never** attempts an automatic database downgrade/rollback.

## Production `.env` protection — why it's actually safe

`backend/.env`, `backend/.env.production`, and `frontend/.env*` are all
listed in the repo's `.gitignore` (only the `*.example` templates are
tracked). Because `git merge --ff-only` — like any Git operation — only
ever touches files Git is tracking, these files are **structurally
unreachable** by the update process, not just "avoided by convention." The
one thing that *would* break this guarantee is running `git clean` or
`git reset --hard` (both of which *do* touch untracked files) — which is
exactly why `update_server.bat` never runs either, ever.

## Dependency-change detection

- **Backend**: `git diff --name-only <old> <new> -- backend/pyproject.toml`.
  Non-empty → `pip install -e .` re-run inside `backend\.venv`. Empty → skipped.
- **Frontend**: `git diff --name-only <old> <new> -- frontend/package.json frontend/package-lock.json`
  for `npm ci`, and a broader check including `frontend/src`, `frontend/public`,
  and the build config files (`next.config.ts`, `tailwind.config.ts`,
  `postcss.config.js`) for whether `npm run build` needs to run at all.
- These checks are deliberately **path-based, not exclusion-based** — a
  same-directory change that doesn't strictly need a reinstall/rebuild
  (e.g. a backend test file, or a frontend `.test.tsx` file) can still
  trigger one. This trades a slightly slower update for simpler, more
  reliable detection logic — see the script's own `:diff_nonempty` comment.

## Migration behavior

- Detected purely by whether any file under `backend/alembic/versions`
  changed between the old and new commit — not by inspecting `alembic
  current` at runtime.
- **A verified backup is always taken first**, via the exact same
  `deploy\windows\run_backup.bat` used for the daily scheduled backup (see
  `docs/BACKUP.md`) — no separate backup mechanism.
- If the backup itself fails, the migration is **not attempted at all**,
  and the script stops.
- `alembic upgrade head` then runs. If it fails, the script stops
  **immediately** — Backend/Frontend are **not restarted**, so the
  previously-running code keeps serving traffic rather than running against
  an unknown/partially-migrated schema. See "After a failed update" below.
- No automatic downgrade is ever attempted, by design — see "Rollback" below.

## Service restart logic

| Change detected | Postgres | Backend | Frontend |
|---|---|---|---|
| Backend code only | — | restart | — |
| Backend dependencies | — | reinstall + restart | — |
| Frontend code/deps | — | — | `npm ci`/`build` + restart |
| Migration applied | — | restart | — |
| Nothing changed | — | — | — |

Restarts use plain `net stop`/`net start <ServiceName>` — this works
against any registered Windows Service regardless of whether `nssm.exe` is
on `PATH` at update time. If a named service isn't registered at all (the
Server PC is still on the older manual/non-service setup), the script warns
and tells you to use `deploy\windows\restart_clinic.bat` yourself instead
of silently doing nothing.

## Verifying the deployed commit

`backend/deploy_info.json` (generated, gitignored — never a config file, no
secrets) is written by `scripts/write_deploy_info.py` at step 11 — i.e.
only once the code is updated, dependencies/build are done, and (if
required) the migration has already succeeded. This is read by:

- `GET /api/v1/health` — unauthenticated, includes `git_commit`,
  `git_commit_short`, `deployed_at` (all `null` on a machine that has never
  run `update_server.bat` successfully).
- `GET /api/v1/system/status` — same fields, Owner/Administrator only, plus
  `app_version` and everything else that endpoint already reported.

To answer "what commit is actually running on this Server PC" at any time:
```
curl http://localhost:8000/api/v1/health
```
or open the System Status page in the app (Owner/Administrator). Cross-check
against `git -C <repo> log -1 --oneline` on the Server PC itself if you want
to confirm the repo and the running process agree.

**Important nuance**: `deploy_info.json` reflects the last commit that was
*actually restarted into*, not necessarily what `git log` shows checked out
on disk. If a run fails at dependency install, the frontend build, or the
migration step (§"Migration behavior" above), `git merge --ff-only` has
already advanced the files on disk to `NEW_SHA`, but the running
Backend/Frontend processes were deliberately **not** restarted — so
`/health` correctly keeps reporting the *previous* `OLD_SHA`, matching what
is actually executing in memory, not what the working tree contains. This
is intentional, not a bug: it means a mismatch between `git log -1` and
`/health`'s `git_commit` on the Server PC is itself a reliable signal that
the last update attempt didn't complete successfully.

## After a failed update

The console output and the `DEPLOYMENT FAILED` banner tell you exactly
which step failed and where the detailed log is
(`deploy\windows\logs\update-<timestamp>.log`). What to do depends on which
step failed:

- **Failed at step 1–5 (repo/working-tree/fetch/merge checks)**: nothing
  was changed at all — the old code is still running, untouched. Resolve
  whatever the message describes (commit/discard local changes, check
  network, resolve diverged history) and re-run the script.
- **Failed at step 7–8 (dependency install / frontend build)**: code was
  updated via git, but the old `.venv`/`.next` build may now be inconsistent
  with the new source. Backend/Frontend were **not yet restarted** at this
  point, so the *previous build* is still what's actually serving traffic —
  fix the underlying error (see the detail log), then re-run the script
  (it will detect the same dependency/build changes again and retry).
- **Failed at step 9 (migration)**: the most serious case — see "Rollback"
  below. Do not restart services manually. Do not attempt a manual `alembic
  downgrade` without understanding what actually failed first.
- **Failed at step 10–11 (restart / health check)**: code and schema may
  already be updated, but a service isn't coming up cleanly. Check
  `deploy\windows\logs\{backend,frontend}-service-error.log` — this is the
  same troubleshooting table already in `FIRST_CLINIC_INSTALLATION.md`.

## Rollback (manual, practical, no automation)

**This project deliberately does not implement automatic rollback** — for
the same reason `docs/BACKUP.md` deliberately never automates restore: an
automated reversal of either code or (especially) a database migration is
exactly the kind of action that should have a human directly watching it on
a clinic's live system.

**Code and database rollback are separate concerns — handle them separately:**

1. **Identify the previous known-good commit.** `OLD_SHA`/`NEW_SHA` are
   printed by the failed run and recorded in
   `deploy\windows\logs\update-history.log` — that's your reference point.
2. **Determine whether a migration actually ran.** The same failed run's
   banner says `Migration: applied successfully` / `FAILED` / `not
   required`. This is the single most important fact for deciding what
   "rollback" even means here:
   - **No migration involved** → rolling back is just code: `git checkout
     <OLD_SHA>` (a deliberate, human-run detached checkout — the one
     legitimate place a "hard" git operation belongs, precisely because a
     person is choosing it on purpose), then re-run the dependency/build
     steps for that commit manually (or re-run `update_server.bat` after
     first pushing a real revert commit to `origin/main`, which is the
     cleaner long-term fix).
   - **Migration applied successfully, but something else in the same
     release is broken** → prefer a **forward-fixing migration** (a new
     migration that corrects the problem) over downgrading. Most schema
     changes are additive (new columns/tables) and don't strictly require
     reverting to keep the app working; check the specific migration file
     before assuming a downgrade is even necessary.
   - **Migration itself failed** → the database may be partially migrated.
     Do **not** guess. Use `alembic current` on the Server PC to see
     exactly what state the schema is actually in, compare it against the
     migration that failed, and only then decide between a targeted manual
     fix, a `alembic downgrade` (only if that specific migration's
     downgrade path is known-safe — not all migrations in this codebase
     have been individually audited for reversibility), or restoring the
     pre-migration backup that step 9 already took.
3. **When in doubt, restore from the pre-migration backup** — this is
   exactly why the backup is mandatory before any migration. Follow the
   existing, human-executed restore procedure in `docs/BACKUP.md` §4
   (never automated, on purpose). The backup taken immediately before the
   failed migration is your most precise recovery point.
4. **A deployment that fails partway through never leaves services
   restarted against a broken state** — by design, `update_server.bat`
   only restarts a service after every step that precedes it succeeded.
   The main risk of "half a deployment" is code and schema disagreeing
   with each other while the *old* process is still running — which is
   inconvenient, but not the corrupted/serving-garbage failure mode a
   naive "restart no matter what" script would risk.

## Logging and troubleshooting

| What you need | Where |
|---|---|
| "What happened on which date, success or failure" | `deploy\windows\logs\update-history.log` (one line per run) |
| "Why exactly did today's update fail" | `deploy\windows\logs\update-<timestamp>.log` (full step transcript for that one run) |
| Backend service errors | `deploy\windows\logs\backend-service-error.log` |
| Frontend service errors | `deploy\windows\logs\frontend-service-error.log` |
| Backup result | `backend\backups\backup_log.txt` (see `docs/BACKUP.md`) |
| Current service status | `check_health.bat`, or `nssm status <ServiceName>` |
| What commit is actually running | `GET /api/v1/health` (see above) |

No second/parallel logging system was introduced — this reuses exactly the
log locations already documented in `FIRST_CLINIC_INSTALLATION.md`'s
troubleshooting table, plus the two new files listed above.
