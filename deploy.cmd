@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM  CONNECT.PH Clinic Platform - Docker Server PC Update Workflow
REM  (Phase 3, extended - see docs/DOCKER_UPDATE_PROCEDURE.md for the full
REM  runbook: prerequisites, volume-identity verification, failure recovery,
REM  and how production `.env` files are protected. This header is a
REM  summary, not the authoritative doc.)
REM
REM  *** Run this ONLY on the real, Docker-based clinic Server PC, by a
REM      human, after the new code has already been reviewed/approved and
REM      pushed to GitHub. This is NOT for the Dev PC, and NOT for a
REM      Server PC that uses the NSSM/manual-Windows-process install
REM      instead of Docker (that architecture uses
REM      deploy\windows\update_server.bat - see that script's own header
REM      and docs\UPDATE_PROCEDURE.md; do not mix the two up). ***
REM
REM  WHAT THIS SCRIPT DOES, IN ORDER:
REM    1.  Verifies the repo-root `.env` exists (Compose variable
REM        substitution needs POSTGRES_PASSWORD / CLINIC_* to even parse).
REM    2.  Verifies this really is the CMS git repository.
REM    3.  Verifies the repo is on branch `main` (refuses on any other
REM        branch or a detached HEAD).
REM    4.  Verifies the working tree is clean - refuses otherwise.
REM    5.  Fetches from GitHub (does not change any files yet).
REM    6.  Fast-forwards to origin/main (`git merge --ff-only` - NEVER a
REM        hard reset, NEVER a force-checkout, NEVER `git clean`).
REM    7.  Compares old vs. new commit to decide what actually changed,
REM        AND separately asks the RUNNING backend container what commit
REM        it's actually serving (`GET /api/v1/health`) - a rebuild/restart
REM        is forced whenever these disagree, even if git itself reports
REM        "already up to date". See "Repository state vs. running
REM        deployment state" below - this is the point of this whole step.
REM    8.  Validates the merged production Compose configuration.
REM    9.  Protects the production Postgres/Redis/attachment volumes -
REM        reads the configured `POSTGRES_VOLUME_NAME`/`REDIS_VOLUME_NAME`/
REM        `BACKEND_VAR_VOLUME_NAME` from .env, refuses to proceed if the
REM        named volume doesn't exist, and cross-checks that the RUNNING
REM        connectph-postgres container is actually mounted from that exact
REM        volume (see docker/docker-compose.prod.yml's header comment).
REM   10.  Rebuilds ONLY the backend and/or frontend images whose inputs
REM        actually changed (or that step 7 determined are already stale).
REM   11.  If any file under `backend/alembic/versions` changed: takes a
REM        Docker-native backup FIRST (`docker exec connectph-postgres
REM        pg_dump ...`, verified), then runs the migration in a throwaway
REM        container started FROM THE IMAGE JUST BUILT in step 10
REM        (`docker compose run --rm ... backend python -m alembic upgrade
REM        head`) - NEVER via `docker exec` into the still-running old
REM        container, which would only ever see whatever migration files
REM        were baked into it before this deploy (see the "Production
REM        incident" note near the migration step below). The database's
REM        actual post-migration revision (`alembic current`, also run
REM        against the new image) is then independently compared against
REM        this deploy's real Alembic head (`alembic heads`) - the exit
REM        code of the upgrade command alone is never trusted. A migration
REM        failure, or a revision mismatch, stops the script immediately -
REM        containers are NOT restarted against a half-migrated,
REM        unmigrated, or unknown schema, and the database is never
REM        stamped or downgraded automatically.
REM   12.  Restarts/recreates ONLY backend/frontend, ONLY if their image
REM        was actually rebuilt or a migration just ran - `--no-deps` so
REM        Postgres/Redis are never touched for an ordinary app update.
REM   13.  Shows `docker compose ps`.
REM   14.  Runs Docker-aware health checks: Postgres container readiness,
REM        backend `/health`+`/ready`, frontend `/`, the CORS preflight
REM        check, and confirms the RUNNING backend now reports the NEW
REM        commit (not just that HEAD changed).
REM   15.  Records one line to deploy\docker\logs\update-history.log.
REM   16.  Prints a clear DEPLOYMENT SUCCESS / DEPLOYMENT FAILED result.
REM
REM  REPOSITORY STATE VS. RUNNING DEPLOYMENT STATE - the most important
REM  correctness property this script has: `git merge --ff-only` succeeding
REM  only proves the FILES on disk changed. It proves nothing about
REM  whether the currently-running `connectph-backend`/`connectph-frontend`
REM  containers were ever rebuilt from those files - they weren't, until
REM  step 10/12 actually runs. This matters concretely: if this machine's
REM  repo was ever manually fast-forwarded outside of this script (e.g. a
REM  bare `git merge --ff-only origin/main` run by hand, or a first-time
REM  bootstrap), step 6 would report "already up to date" on the very next
REM  run - which is TRUE of the repository and WRONG about the running
REM  application. Step 7's SHA cross-check exists specifically to catch
REM  this: it never trusts "HEAD == origin/main" alone, it also asks the
REM  container itself, via `/api/v1/health`'s `git_commit` field (baked
REM  into the image at build time - see docker/Dockerfile.backend and
REM  app/core/deploy_info.py), which can only change when the image is
REM  actually rebuilt and the container actually recreated from it.
REM
REM  WHAT THIS SCRIPT WILL NEVER DO:
REM    - git reset --hard / git checkout -f / git clean -fd / git clean -fdx
REM    - docker compose down / down -v / docker volume rm / docker system
REM      prune (with or without --volumes) - nothing that can delete a
REM      named volume
REM    - overwrite backend\.env, the repo-root .env, or frontend production
REM      env files
REM    - restart/recreate the postgres or redis containers for an ordinary
REM      application update
REM    - restart backend/frontend after a failed migration
REM    - attempt an automatic database downgrade/rollback
REM    - proceed over an uncommitted/dirty working tree, a repo not on
REM      branch main, or an unresolved production-volume-identity mismatch
REM ============================================================

cd /d "%~dp0"
set "CMS_ROOT=%CD%"
set "BACKEND_DIR=%CMS_ROOT%\backend"
set "LOG_DIR=%CMS_ROOT%\deploy\docker\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

set COMPOSE_FILES=-f docker\docker-compose.yml -f docker\docker-compose.prod.yml
REM Absolute path, not a relative "--env-file .env" - never rely on Compose's
REM own automatic .env discovery (which depends on the current working
REM directory a given `docker compose` invocation happens to have) or on
REM this script's own CWD staying put for its entire run. `cd /d` above
REM already guarantees CMS_ROOT is the repo root, so this is always correct
REM regardless of how/where this script is later refactored or invoked from.
set ENV_FILE=--env-file "%CMS_ROOT%\.env"

REM Every `docker ...` invocation below is prefixed with `call` (matching
REM this same file's pre-existing `call npm ci`/`call npm run build`
REM convention) - defensively correct regardless of whether `docker`
REM resolves to a real .exe (the normal case) or a .cmd/.bat wrapper (some
REM environments ship one) - invoking a batch file from inside another
REM batch script WITHOUT `call` transfers control permanently into it,
REM abandoning the rest of this script the moment the callee exits. `call`
REM costs nothing when the target is already a real .exe.

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "RUN_TS=%%i"
set "DETAIL_LOG=%LOG_DIR%\update-%RUN_TS%.log"
set "HISTORY_LOG=%LOG_DIR%\update-history.log"
type nul > "%DETAIL_LOG%"

set "OLD_SHA=unknown"
set "NEW_SHA=unknown"
set "RUNNING_SHA_BEFORE=unknown"
set "MIGRATION_REQUIRED=0"
set "MIGRATION_RESULT=not required"
set "BACKEND_CHANGED=0"
set "FRONTEND_CHANGED=0"
set "FAIL_REASON="

echo ============================================================
echo  CONNECT.PH Clinic Platform - Docker Production Deployment
echo  %RUN_TS%
echo ============================================================
echo.

REM --- [1/16] Refuse to deploy without the clinic .env ------------------------
echo [1/16] Checking for the clinic .env...
if not exist ".env" (
    echo.
    echo FAILED: no ".env" file found in the repo root.
    echo This file is required - it supplies POSTGRES_PASSWORD and this
    echo machine's real POSTGRES_VOLUME_NAME / REDIS_VOLUME_NAME /
    echo BACKEND_VAR_VOLUME_NAME. Copy .env.example to .env and fill in the
    echo real values for this clinic - see .env.example.
    echo Nothing was pulled, validated, built, or restarted.
    set "FAIL_REASON=Repo-root .env is missing."
    call :fail
    exit /b 1
)
REM Read the three required production volume names up front - printed now
REM (before anything else happens) so an operator sees exactly what this
REM run expects BEFORE any git/docker command runs. Never defaulted/guessed
REM here - an unset value is caught later by docker-compose.prod.yml's own
REM `${VAR:?message}` requirement, which fails the whole `docker compose`
REM invocation rather than silently omitting the volume.
set "POSTGRES_VOLUME_NAME="
set "REDIS_VOLUME_NAME="
set "BACKEND_VAR_VOLUME_NAME="
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    if /i "%%A"=="POSTGRES_VOLUME_NAME" set "POSTGRES_VOLUME_NAME=%%B"
    if /i "%%A"=="REDIS_VOLUME_NAME" set "REDIS_VOLUME_NAME=%%B"
    if /i "%%A"=="BACKEND_VAR_VOLUME_NAME" set "BACKEND_VAR_VOLUME_NAME=%%B"
)
echo   OK - .env found.
echo   Expected production volumes for this machine:
echo     Postgres:     !POSTGRES_VOLUME_NAME!
echo     Redis:        !REDIS_VOLUME_NAME!
echo     Backend var:  !BACKEND_VAR_VOLUME_NAME!
if not defined POSTGRES_VOLUME_NAME (
    echo.
    echo FAILED: POSTGRES_VOLUME_NAME is not set in .env - refusing to guess.
    echo Run `docker volume ls` on this machine and set it to the real,
    echo already-existing Postgres data volume name - see .env.example.
    set "FAIL_REASON=POSTGRES_VOLUME_NAME is not set in .env."
    call :fail
    exit /b 1
)
echo.

REM --- [2/16] Verify this is the CMS repository --------------------------------
echo [2/16] Checking repository...
if not exist "%CMS_ROOT%\.git" (
    set "FAIL_REASON=Not a git repository - %CMS_ROOT%\.git does not exist. Nothing was changed."
    call :fail
    exit /b 1
)
git rev-parse --is-inside-work-tree >>"%DETAIL_LOG%" 2>&1
if errorlevel 1 (
    set "FAIL_REASON=git rev-parse failed - is git installed and on PATH? See %DETAIL_LOG%."
    call :fail
    exit /b 1
)
echo   OK.
echo.

REM --- [3/16] Verify branch = main ----------------------------------------------
echo [3/16] Checking branch...
for /f %%i in ('git rev-parse --abbrev-ref HEAD') do set "CURRENT_BRANCH=%%i"
echo   Current branch: %CURRENT_BRANCH%
if not "%CURRENT_BRANCH%"=="main" (
    echo.
    echo FAILED: this machine is on branch/state "%CURRENT_BRANCH%", not "main"
    echo ^(a value of "HEAD" here means detached HEAD^). This script only ever
    echo updates to origin/main. A human must check out "main" deliberately
    echo first before re-running.
    set "FAIL_REASON=Not on branch main (currently: %CURRENT_BRANCH%)."
    call :fail
    exit /b 1
)
echo   OK.
echo.

REM --- [4/16] Refuse to deploy over uncommitted local changes ------------------
echo [4/16] Checking for uncommitted local changes...
set "DIRTY_CHECK=%TEMP%\cms_docker_dirty_%RUN_TS%.txt"
git status --porcelain > "%DIRTY_CHECK%" 2>>"%DETAIL_LOG%"
for %%A in ("%DIRTY_CHECK%") do set "DIRTY_SIZE=%%~zA"
if not "%DIRTY_SIZE%"=="0" (
    echo.
    echo FAILED: this checkout has uncommitted local changes. Resolve or
    echo discard them before deploying - showing status below:
    echo.
    type "%DIRTY_CHECK%"
    del "%DIRTY_CHECK%" >nul 2>&1
    set "FAIL_REASON=Working tree is not clean - see console output above."
    call :fail
    exit /b 1
)
del "%DIRTY_CHECK%" >nul 2>&1
echo   OK - working tree clean.
echo.

REM --- [5/16] Fetch + fast-forward, with old/new SHA tracking ------------------
echo [5/16] Fetching GitHub and fast-forwarding (fast-forward only)...
for /f %%i in ('git rev-parse HEAD') do set "OLD_SHA=%%i"
git fetch origin >>"%DETAIL_LOG%" 2>&1
if errorlevel 1 (
    set "FAIL_REASON=git fetch origin failed - check network/GitHub connectivity. See %DETAIL_LOG%."
    call :fail
    exit /b 1
)
git merge --ff-only origin/main >>"%DETAIL_LOG%" 2>&1
if errorlevel 1 (
    echo.
    echo FAILED: `git merge --ff-only origin/main` did not succeed - local and
    echo origin/main have diverged, or the remote is unreachable. This script
    echo will never force this with a reset/checkout. Resolve manually.
    set "FAIL_REASON=git merge --ff-only failed (diverged history) - see %DETAIL_LOG%."
    call :fail
    exit /b 1
)
for /f %%i in ('git rev-parse HEAD') do set "NEW_SHA=%%i"
echo   Old commit: %OLD_SHA%
echo   New commit: %NEW_SHA%
echo.

REM --- [6/16] Determine what actually needs rebuilding -------------------------
REM Repository-level diff (skipped entirely when OLD_SHA==NEW_SHA - there is
REM nothing to diff) PLUS an independent check of what the RUNNING backend
REM container reports, so "already up to date" never means "definitely
REM already deployed" - see the header comment's "Repository state vs.
REM running deployment state" section.
echo [6/16] Comparing old/new commit and the running container's reported commit...
if not "%OLD_SHA%"=="%NEW_SHA%" (
    call :diff_nonempty "backend"
    if not errorlevel 1 set "BACKEND_CHANGED=1"
    call :diff_nonempty "docker/Dockerfile.backend"
    if not errorlevel 1 set "BACKEND_CHANGED=1"
    call :diff_nonempty "frontend"
    if not errorlevel 1 set "FRONTEND_CHANGED=1"
    call :diff_nonempty "docker/Dockerfile.frontend"
    if not errorlevel 1 set "FRONTEND_CHANGED=1"
    call :diff_nonempty "backend/alembic/versions"
    if not errorlevel 1 set "MIGRATION_REQUIRED=1"
) else (
    echo   Repository already up to date - no file-level diff to inspect.
)

REM Written to a temp file and read back via `set /p` rather than a
REM backtick-command-substitution `for /f`, matching the pattern already
REM used safely elsewhere in this script (:docker_backup,
REM :check_volume_protection) - simpler and more consistent, though the
REM cmd.exe bug below turned out to be unrelated to this specific choice.
set "RUNNING_SHA_FILE=%TEMP%\cms_docker_running_sha_%RANDOM%.txt"
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:8000/api/v1/health' -UseBasicParsing -TimeoutSec 5; $j = $r.Content | ConvertFrom-Json; if ($j.git_commit) { $j.git_commit } else { 'none' } } catch { 'unreachable' }" > "%RUNNING_SHA_FILE%" 2>>"%DETAIL_LOG%"
set "RUNNING_SHA_BEFORE="
set /p RUNNING_SHA_BEFORE=<"%RUNNING_SHA_FILE%"
del "%RUNNING_SHA_FILE%" >nul 2>&1
if not defined RUNNING_SHA_BEFORE set "RUNNING_SHA_BEFORE=unreachable"
echo   Currently RUNNING backend reports commit: %RUNNING_SHA_BEFORE%
if /i not "%RUNNING_SHA_BEFORE%"=="%NEW_SHA%" (
    echo   [BOOTSTRAP/DRIFT] The running container does not report the new
    echo   commit yet ^(repository is at %NEW_SHA%^) - forcing a rebuild+restart
    echo   of backend and frontend even though git alone might say "already up
    echo   to date". This is expected on this machine's very first run of this
    echo   script after the earlier manual fast-forward.
    set "BACKEND_CHANGED=1"
    set "FRONTEND_CHANGED=1"
) else (
    echo   Running container already matches the repository - no drift.
)
echo   Backend rebuild needed:   !BACKEND_CHANGED!
echo   Frontend rebuild needed:  !FRONTEND_CHANGED!
REM PRODUCTION INCIDENT #2 - a deploy of commit 3a85cf9 had already
REM fast-forwarded the repository to its target commit on an earlier,
REM interrupted attempt. The NEXT run therefore found OLD_SHA==NEW_SHA, so
REM the git-diff check above never inspected backend/alembic/versions and
REM this flag stayed 0 - the script printed "No new migrations - skipped"
REM and finished successfully while the database was still 3 migrations
REM behind (0043, not 0046). Git commit drift is not the same thing as
REM database drift: the repository can already be exactly at the target
REM commit while the database is not. This flag is now ONLY an early,
REM informational hint from the git diff - it no longer gates anything.
REM The actual, authoritative decision is made in step [10/16] from the
REM database's own real Alembic revision (see the note there).
echo   Migration files changed in this update ^(git diff, informational^): !MIGRATION_REQUIRED!
echo.

REM --- [7/16] Validate the production Compose configuration --------------------
echo [7/16] Validating production Compose configuration...
call docker compose %ENV_FILE% %COMPOSE_FILES% config >>"%DETAIL_LOG%" 2>&1
if errorlevel 1 (
    echo.
    echo FAILED: the production Compose configuration is invalid, or .env is
    echo missing a required value ^(e.g. POSTGRES_PASSWORD^). See %DETAIL_LOG%.
    set "FAIL_REASON=docker compose config validation failed - see %DETAIL_LOG%."
    call :fail
    exit /b 1
)
echo   OK.
echo.

REM --- [8/16] Protect production volumes ----------------------------------------
echo [8/16] Verifying production volume identity...
call :check_volume_protection
if errorlevel 1 (
    set "FAIL_REASON=Production volume identity check failed - see console output above and %DETAIL_LOG%."
    call :fail
    exit /b 1
)
echo.

REM --- [9/16] Build affected images only -----------------------------------------
echo [9/16] Building images for changed services...
set "GIT_COMMIT=%NEW_SHA%"
if "!BACKEND_CHANGED!"=="1" (
    echo   Building backend...
    call docker compose %ENV_FILE% %COMPOSE_FILES% build backend >>"%DETAIL_LOG%" 2>&1
    if errorlevel 1 (
        set "FAIL_REASON=docker compose build backend failed - see %DETAIL_LOG%. Previous container is still running, untouched."
        call :fail
        exit /b 1
    )
) else (
    echo   Backend image unchanged - skipped.
)
if "!FRONTEND_CHANGED!"=="1" (
    echo   Building frontend...
    call docker compose %ENV_FILE% %COMPOSE_FILES% build frontend >>"%DETAIL_LOG%" 2>&1
    if errorlevel 1 (
        set "FAIL_REASON=docker compose build frontend failed - see %DETAIL_LOG%. Previous container is still running, untouched."
        call :fail
        exit /b 1
    )
) else (
    echo   Frontend image unchanged - skipped.
)
echo.

REM --- [10/16] Migrations (mandatory Docker-native backup first; runs against ---
REM     the NEWLY BUILT image, never the old running container) --------------
echo [10/16] Database migrations...
REM SECOND HOTFIX - the decision to migrate is made from the DATABASE, not
REM from git. A deploy whose checkout already contains new migration files
REM (OLD_SHA==NEW_SHA after a manual `git pull`, an earlier failed deploy, or
REM a fetch that ran ahead) makes the git diff empty, which used to skip this
REM step while the new image expected newer schema. Now: read the new image's
REM Alembic head AND the database's current revision, and migrate whenever
REM they differ. The git diff is informational only.
echo   Discovering this deploy's actual Alembic head from the newly built image...
set "HEAD_FILE=%TEMP%\cms_docker_alembic_head_%RANDOM%.txt"
call docker compose %ENV_FILE% %COMPOSE_FILES% run --rm --no-deps -T backend python -m alembic heads > "!HEAD_FILE!" 2>>"%DETAIL_LOG%"
if errorlevel 1 (
    echo   [FAIL] Could not determine the Alembic head from the new image ^(docker compose run failed^).
    echo   Containers were NOT restarted. See %DETAIL_LOG%.
    set "MIGRATION_RESULT=FAILED - could not read alembic heads, see %DETAIL_LOG%"
    set "FAIL_REASON=docker compose run ... alembic heads failed before any migration was attempted - see %DETAIL_LOG%."
    del "!HEAD_FILE!" >nul 2>&1
    call :fail
    exit /b 1
)
set "EXPECTED_HEAD="
for /f "usebackq tokens=1" %%H in ("!HEAD_FILE!") do if not defined EXPECTED_HEAD set "EXPECTED_HEAD=%%H"
del "!HEAD_FILE!" >nul 2>&1
if not defined EXPECTED_HEAD (
    echo   [FAIL] `alembic heads` produced no output - cannot verify the target revision.
    echo   Containers were NOT restarted. See %DETAIL_LOG%.
    set "MIGRATION_RESULT=FAILED - alembic heads produced no output, see %DETAIL_LOG%"
    set "FAIL_REASON=alembic heads produced no output from the new image - see %DETAIL_LOG%."
    call :fail
    exit /b 1
)
echo   This deploy's Alembic head: !EXPECTED_HEAD!
set "HEAD_COUNT=0"
call docker compose %ENV_FILE% %COMPOSE_FILES% run --rm --no-deps -T backend python -m alembic heads > "%TEMP%\cms_heads_count.txt" 2>>"%DETAIL_LOG%"
for /f "usebackq tokens=1" %%H in ("%TEMP%\cms_heads_count.txt") do set /a HEAD_COUNT+=1
del "%TEMP%\cms_heads_count.txt" >nul 2>&1
if !HEAD_COUNT! GTR 1 (
    echo   [FAIL] Multiple Alembic heads detected ^(!HEAD_COUNT!^) - refusing to migrate.
    set "MIGRATION_RESULT=FAILED - multiple alembic heads"
    set "FAIL_REASON=Multiple Alembic heads in the new image - resolve the branch before deploying."
    call :fail
    exit /b 1
)
echo   Reading the database current revision...
set "CURRENT_FILE=%TEMP%\cms_docker_alembic_pre_%RANDOM%.txt"
call docker compose %ENV_FILE% %COMPOSE_FILES% run --rm --no-deps -T backend python -m alembic current > "!CURRENT_FILE!" 2>>"%DETAIL_LOG%"
if errorlevel 1 (
    echo   [FAIL] Could not read the database revision ^(alembic current failed^). Nothing was migrated.
    set "MIGRATION_RESULT=FAILED - could not read current revision, see %DETAIL_LOG%"
    set "FAIL_REASON=alembic current failed before migration - see %DETAIL_LOG%."
    del "!CURRENT_FILE!" >nul 2>&1
    call :fail
    exit /b 1
)
set "PRE_REV="
for /f "usebackq tokens=1" %%C in ("!CURRENT_FILE!") do if not defined PRE_REV set "PRE_REV=%%C"
del "!CURRENT_FILE!" >nul 2>&1
echo   Database revision: !PRE_REV!   ^|   image head: !EXPECTED_HEAD!
set "MIGRATE_NEEDED=0"
if /i not "!PRE_REV!"=="!EXPECTED_HEAD!" set "MIGRATE_NEEDED=1"
if "!MIGRATE_NEEDED!"=="1" (
    echo   [MIGRATION REQUIRED] Database is not at this deploy's Alembic head.
    if "!MIGRATION_REQUIRED!"=="0" echo   ^(git diff showed no migration change - database was behind anyway.^)
    echo.
    echo   [BACKUP REQUIRED] Creating pre-migration Docker-native backup...
    call :docker_backup
    if errorlevel 1 (
        echo   [FAIL] Pre-migration backup failed. Migration was NOT attempted.
        echo   Containers were NOT restarted. See %DETAIL_LOG% and
        echo   backend\backups\backup_log.txt for detail.
        set "MIGRATION_RESULT=backup failed - migration not attempted"
        set "FAIL_REASON=Pre-migration Docker backup failed - see %DETAIL_LOG% and backend\backups\backup_log.txt."
        call :fail
        exit /b 1
    )
    echo.
    REM PRODUCTION INCIDENT, FIXED - a real deploy of commit b72ab58 built the
    REM new backend image (step 9 above already contains migrations
    REM 0044-0046), then ran `docker exec connectph-backend python -m
    REM alembic upgrade head`. `docker exec` attaches to the CURRENTLY
    REM RUNNING container by name - which, at this point in the script, is
    REM still the OLD image (nothing recreates it until step 11, AFTER this
    REM block). The old container was already at its own head (0043), so the
    REM command exited 0 and this script printed "Migration applied
    REM successfully" while the database was never touched; step 11 then
    REM swapped the live app onto the new image, which now expected schema
    REM objects (laboratory_orders.order_item_id, prescription_items.dosage_
    REM form, soap_phrase_favorites) that did not exist. Fix: migrations now
    REM run in a throwaway (`--rm`) one-off container started FROM THE IMAGE
    REM JUST BUILT via `docker compose run`, never via `docker exec` into the
    REM live container - and the exit code is no longer trusted by itself:
    REM the database's actual post-migration revision is independently
    REM re-read and compared against this deploy's real Alembic head.
    REM `--no-deps` stops Compose from also (re)starting postgres/redis,
    REM which are already running and untouched here; `-T` disables TTY
    REM allocation so captured output is deterministic in a non-interactive
    REM run.
    echo   Running: docker compose run --rm backend python -m alembic upgrade head ^(new image, not the live container^) ...
    call docker compose %ENV_FILE% %COMPOSE_FILES% run --rm --no-deps -T backend python -m alembic upgrade head >>"%DETAIL_LOG%" 2>&1
    if errorlevel 1 (
        echo   [FAIL] alembic upgrade head FAILED in the new-image migration container.
        echo.
        echo   ================================================================
        echo   DATABASE MIGRATION FAILED - THIS REQUIRES HUMAN INTERVENTION.
        echo   Containers were NOT restarted, so the OLD image is still
        echo   running - it will keep working against whatever schema state
        echo   the database was in before this attempt, which may now be
        echo   PARTIALLY migrated. Do not restart containers manually until
        echo   this is resolved. See %DETAIL_LOG% for the exact Alembic error,
        echo   and docs\DOCKER_UPDATE_PROCEDURE.md's "After a failed update"
        echo   section for recovery steps ^(the backup just taken above is the
        echo   safety net^).
        echo   ================================================================
        set "MIGRATION_RESULT=FAILED - see %DETAIL_LOG%"
        set "FAIL_REASON=alembic upgrade head failed in the new-image migration container - see %DETAIL_LOG%."
        call :fail
        exit /b 1
    )
    REM Do NOT trust the exit code alone - that is exactly how the original
    REM incident went unnoticed. Independently re-read the database's own
    REM alembic_version via `alembic current` in the same new image and
    REM require it to equal the expected head computed above.
    echo   Verifying the database actually reached that revision...
    set "CURRENT_FILE=%TEMP%\cms_docker_alembic_current_%RANDOM%.txt"
    call docker compose %ENV_FILE% %COMPOSE_FILES% run --rm --no-deps -T backend python -m alembic current > "!CURRENT_FILE!" 2>>"%DETAIL_LOG%"
    if errorlevel 1 (
        echo   [FAIL] Could not read the post-migration database revision ^(alembic current failed^).
        echo   Containers were NOT restarted. See %DETAIL_LOG%.
        set "MIGRATION_RESULT=FAILED - could not verify post-migration revision, see %DETAIL_LOG%"
        set "FAIL_REASON=docker compose run ... alembic current failed after upgrade - see %DETAIL_LOG%."
        del "!CURRENT_FILE!" >nul 2>&1
        call :fail
        exit /b 1
    )
    set "ACTUAL_HEAD="
    for /f "usebackq tokens=1" %%C in ("!CURRENT_FILE!") do if not defined ACTUAL_HEAD set "ACTUAL_HEAD=%%C"
    del "!CURRENT_FILE!" >nul 2>&1
    if /i not "!ACTUAL_HEAD!"=="!EXPECTED_HEAD!" (
        echo   [FAIL] Database revision after migration is "!ACTUAL_HEAD!",
        echo   expected "!EXPECTED_HEAD!". The migration command exited 0 but
        echo   the database did NOT actually reach this deploy's Alembic head -
        echo   do not trust exit-code-only success. Containers were NOT
        echo   restarted and the database was NOT stamped or downgraded.
        echo   ================================================================
        echo   DATABASE MIGRATION FAILED - THIS REQUIRES HUMAN INTERVENTION.
        echo   See %DETAIL_LOG% and docs\DOCKER_UPDATE_PROCEDURE.md's "After a
        echo   failed update" section ^(the backup taken above is the safety
        echo   net^).
        echo   ================================================================
        set "MIGRATION_RESULT=FAILED - DB at !ACTUAL_HEAD!, expected !EXPECTED_HEAD!, see %DETAIL_LOG%"
        set "FAIL_REASON=Post-migration revision check failed: DB at !ACTUAL_HEAD!, expected !EXPECTED_HEAD! - see %DETAIL_LOG%."
        call :fail
        exit /b 1
    )
    echo   [ OK ] Migration applied and verified - database is at !ACTUAL_HEAD!.
    set "MIGRATION_RESULT=applied and verified at !ACTUAL_HEAD!"
    set "BACKEND_CHANGED=1"
) else (
    echo   Database already at this deploy's Alembic head ^(!PRE_REV!^) - migration skipped.
)
echo.

REM --- [11/16] Restart/recreate only the containers that need it ----------------
echo [11/16] Restarting containers as needed (postgres/redis left untouched)...
if "!BACKEND_CHANGED!"=="1" (
    call docker compose %ENV_FILE% %COMPOSE_FILES% up -d --no-deps backend >>"%DETAIL_LOG%" 2>&1
    if errorlevel 1 (
        set "FAIL_REASON=docker compose up -d --no-deps backend failed - see %DETAIL_LOG%."
        call :fail
        exit /b 1
    )
    echo   [ OK ] backend restarted.
) else (
    echo   Backend restart not required - skipped.
)
if "!FRONTEND_CHANGED!"=="1" (
    call docker compose %ENV_FILE% %COMPOSE_FILES% up -d --no-deps frontend >>"%DETAIL_LOG%" 2>&1
    if errorlevel 1 (
        set "FAIL_REASON=docker compose up -d --no-deps frontend failed - see %DETAIL_LOG%."
        call :fail
        exit /b 1
    )
    echo   [ OK ] frontend restarted.
) else (
    echo   Frontend restart not required - skipped.
)
echo   postgres/redis were not touched - never recreated for an app update.
echo.

REM --- [12/16] Current status ------------------------------------------------------
echo [12/16] Current container status:
call docker compose %ENV_FILE% %COMPOSE_FILES% ps
echo.

REM --- [13/16] Wait for real readiness before checking health -------------------
echo [13/16] Waiting for backend readiness...
set "READY_OK=0"
for /l %%n in (1,1,20) do (
    if "!READY_OK!"=="0" (
        curl -f -s -o nul "http://localhost:8000/api/v1/ready"
        if not errorlevel 1 (
            set "READY_OK=1"
        ) else (
            timeout /t 3 /nobreak >nul
        )
    )
)
if "!READY_OK!"=="0" (
    echo   [WARN] Backend did not report ready within ~60s - proceeding to the
    echo   full health check anyway, which will report the exact failure.
) else (
    echo   OK - backend ready.
)
echo.

REM --- [14/16] Docker-aware health checks ----------------------------------------
echo [14/16] Running health checks...
set HEALTH_OK=1

call docker exec connectph-postgres pg_isready -U connectph >>"%DETAIL_LOG%" 2>&1
if errorlevel 1 (
    echo   FAILED: PostgreSQL ^(docker exec connectph-postgres pg_isready^)
    set HEALTH_OK=0
) else (
    echo   OK - PostgreSQL container ready.
)

curl -f -s -o nul http://localhost:8000/api/v1/health
if errorlevel 1 (
    echo   FAILED: backend health check ^(http://localhost:8000/api/v1/health^)
    set HEALTH_OK=0
) else (
    echo   OK - backend healthy.
)

curl -f -s -o nul http://localhost:8000/api/v1/ready
if errorlevel 1 (
    echo   FAILED: backend readiness ^(http://localhost:8000/api/v1/ready - DB unreachable from backend^)
    set HEALTH_OK=0
) else (
    echo   OK - backend reports the database reachable.
)

curl -f -s -o nul http://localhost:3000/
if errorlevel 1 (
    echo   FAILED: frontend health check ^(http://localhost:3000/^)
    set HEALTH_OK=0
) else (
    echo   OK - frontend responding.
)

REM --- Deployed-SHA verification - the actual point of this whole script -------
set "RUNNING_SHA_FILE=%TEMP%\cms_docker_running_sha_%RANDOM%.txt"
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:8000/api/v1/health' -UseBasicParsing -TimeoutSec 5; $j = $r.Content | ConvertFrom-Json; if ($j.git_commit) { $j.git_commit } else { 'none' } } catch { 'unreachable' }" > "%RUNNING_SHA_FILE%" 2>>"%DETAIL_LOG%"
set "RUNNING_SHA_AFTER="
set /p RUNNING_SHA_AFTER=<"%RUNNING_SHA_FILE%"
del "%RUNNING_SHA_FILE%" >nul 2>&1
if not defined RUNNING_SHA_AFTER set "RUNNING_SHA_AFTER=unreachable"
if /i "%RUNNING_SHA_AFTER%"=="%NEW_SHA%" (
    echo   OK - running backend now reports the new commit ^(%RUNNING_SHA_AFTER%^).
) else (
    echo   FAILED: running backend reports "%RUNNING_SHA_AFTER%", expected %NEW_SHA%.
    echo   Do NOT report success merely because git HEAD changed - the
    echo   container itself must confirm it.
    set HEALTH_OK=0
)

REM --- CORS preflight check (production login) ----------------------------------
set CORS_EXPECTED_ORIGIN=
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    if /i "%%A"=="CLINIC_FRONTEND_ORIGIN" set CORS_EXPECTED_ORIGIN=%%B
)
if not defined CORS_EXPECTED_ORIGIN set CORS_EXPECTED_ORIGIN=http://192.168.68.106:3000

set CORS_TMP_HEADERS=%TEMP%\connectph_deploy_cors_headers.tmp
set CORS_TMP_STATUS=%TEMP%\connectph_deploy_cors_status.tmp
del /q "%CORS_TMP_HEADERS%" >nul 2>&1
del /q "%CORS_TMP_STATUS%" >nul 2>&1

curl -s -o nul -D "%CORS_TMP_HEADERS%" -w "%%{http_code}" -X OPTIONS "http://127.0.0.1:8000/api/v1/auth/login" -H "Origin: %CORS_EXPECTED_ORIGIN%" -H "Access-Control-Request-Method: POST" > "%CORS_TMP_STATUS%"

set CORS_STATUS=
set /p CORS_STATUS=<"%CORS_TMP_STATUS%"

set CORS_ORIGIN_OK=
findstr /I /C:"access-control-allow-origin: %CORS_EXPECTED_ORIGIN%" "%CORS_TMP_HEADERS%" >nul 2>&1
if not errorlevel 1 set CORS_ORIGIN_OK=1

set CORS_OK=1
if not "%CORS_STATUS%"=="200" set CORS_OK=0
if not defined CORS_ORIGIN_OK set CORS_OK=0

if "%CORS_OK%"=="1" (
    echo   OK - CORS preflight for %CORS_EXPECTED_ORIGIN% allowed.
) else (
    echo   FAILED: CORS preflight for %CORS_EXPECTED_ORIGIN% was rejected
    echo   ^(OPTIONS /api/v1/auth/login returned HTTP %CORS_STATUS%, expected
    echo   200 with Access-Control-Allow-Origin: %CORS_EXPECTED_ORIGIN%^).
    set HEALTH_OK=0
)
del /q "%CORS_TMP_HEADERS%" >nul 2>&1
del /q "%CORS_TMP_STATUS%" >nul 2>&1
echo.

if "!HEALTH_OK!"=="0" (
    set "FAIL_REASON=Post-deploy health checks reported failures - see [FAILED] lines above."
    call :fail
    exit /b 1
)

REM --- [15/16] Record deployment history -----------------------------------------
echo [15/16] Recording deployment history...
call :record_history "SUCCESS" ""
echo   Detailed log: %DETAIL_LOG%
echo.

REM --- [16/16] Success --------------------------------------------------------------
echo ============================================================
echo  DEPLOYMENT SUCCESS
echo.
echo  Previous commit: %OLD_SHA%
echo  New commit:      %NEW_SHA%
echo  Migration:       %MIGRATION_RESULT%
echo  Verified running commit: %RUNNING_SHA_AFTER%
echo ============================================================
exit /b 0

REM Every failure path above does `call :fail` + `exit /b 1` (never a bare
REM `goto :fail`) - empirically found, via live testing against an isolated
REM scratch repo, that a `goto :fail` jumping past certain earlier blocks in
REM this file did NOT reliably stop execution (a known cmd.exe parser
REM quirk where `goto` can misbehave jumping over/into large parenthesized
REM blocks in a long script - it is not specific to any one block here,
REM adding unrelated lines elsewhere in the file was enough to make a given
REM failure "accidentally" work, which is exactly the kind of fragility
REM that must never ship). `call` does not have this problem - it always
REM properly saves/resumes execution context - so `:fail` is now invoked as
REM an ordinary subroutine; the caller's own `exit /b 1` immediately after
REM the `call` is what actually terminates the script, since a called
REM subroutine's own `exit /b` only returns from that one call.
:fail
call :record_history "FAILED" "%FAIL_REASON%"
echo.
echo ============================================================
echo  DEPLOYMENT FAILED
echo.
echo  Previous commit: %OLD_SHA%
echo  New commit:      %NEW_SHA%
echo  Migration:       %MIGRATION_RESULT%
echo  Reason:          %FAIL_REASON%
echo.
echo  Detailed log:    %DETAIL_LOG%
echo  See docs\DOCKER_UPDATE_PROCEDURE.md - "After a failed update" for next steps.
echo ============================================================
exit /b 1

REM =============================================================================
REM Subroutines
REM =============================================================================

REM --- :diff_nonempty <pathspec> [<pathspec> ...] -------------------------------
REM Sets ERRORLEVEL 0 if any of the given paths changed between OLD_SHA and
REM NEW_SHA, 1 otherwise. Same convention as deploy\windows\update_server.bat's
REM own :diff_nonempty (no `!`-based pathspec exclusions - `!` is a delayed-
REM expansion metacharacter in this script).
:diff_nonempty
setlocal DisableDelayedExpansion
set "DIFF_FILE=%TEMP%\cms_docker_diff_%RANDOM%.txt"
git diff --name-only %OLD_SHA% %NEW_SHA% -- %* > "%DIFF_FILE%" 2>>"%DETAIL_LOG%"
for %%A in ("%DIFF_FILE%") do set "SIZE=%%~zA"
del "%DIFF_FILE%" >nul 2>&1
if "%SIZE%"=="0" (
    endlocal
    exit /b 1
)
endlocal
exit /b 0

REM --- :check_volume_protection --------------------------------------------------
REM Two independent, read-only checks - never creates, renames, or deletes
REM anything itself:
REM   1. The volume named by POSTGRES_VOLUME_NAME/REDIS_VOLUME_NAME/
REM      BACKEND_VAR_VOLUME_NAME (from .env) must already exist
REM      (`docker volume inspect <name>` - an exact, single-volume lookup;
REM      see below for why this replaced an earlier `docker volume ls` +
REM      `findstr /x` approach). docker-compose.prod.yml's `external: true`
REM      would also refuse at build/up time if it didn't - this check exists
REM      to fail EARLIER, with a clearer message, before any build starts.
REM   2. The currently RUNNING connectph-postgres container must actually be
REM      mounted from that exact volume (`docker inspect`'s Mounts list,
REM      matched against the data directory) - existence alone isn't enough:
REM      a typo'd-but-real volume name (e.g. a leftover from another
REM      clinic's install, or a stale test volume) would pass check 1 while
REM      still being catastrophically wrong. This is what actually answers
REM      "is this the real clinic database", not just "does a volume with
REM      this name exist somewhere on this machine".
REM
REM CONFIRMED BUG, FIXED - a real first-deployment run on the actual Canora
REM Server PC failed here with a FALSE "volume does not exist", even though
REM the volume genuinely existed and was correctly mounted. Root cause,
REM reproduced on the Dev PC: `docker volume ls --format "{{.Name}}"` -
REM like any Go/Linux-style CLI - writes LF-only line endings; cmd.exe's
REM `>` redirection captures that verbatim (no LF->CRLF translation), and
REM `findstr /X` (exact whole-line match) silently fails to match ANY line
REM in an LF-only-terminated file - it matches fine with CRLF endings, and
REM `findstr /C` (no `/X`, a substring match) also matches fine regardless
REM of line endings, which is why this specific combination (`/X` + a
REM Go-CLI's LF output) went undetected until real Docker Desktop output
REM was involved - nothing on the Dev PC (no Docker CLI at all) could have
REM produced this LF-only file to catch it earlier. `docker volume inspect
REM <exact-name>` sidesteps the entire class of output-formatting fragility:
REM no line-ending assumption, no multi-line list to parse - just a single
REM exact lookup whose SUCCESS/FAILURE is the real answer, via errorlevel.
REM See docker/docker-compose.prod.yml's header comment and
REM docs/DOCKER_UPDATE_PROCEDURE.md's "Volume identity" section.
:check_volume_protection
setlocal DisableDelayedExpansion
call docker volume inspect "%POSTGRES_VOLUME_NAME%" >nul 2>>"%DETAIL_LOG%"
if errorlevel 1 (
    echo.
    echo   [FAIL] Refusing to proceed.
    echo.
    echo   The configured production volume "%POSTGRES_VOLUME_NAME%"
    echo   ^(POSTGRES_VOLUME_NAME in .env^) does not exist on this machine
    echo   ^(docker volume inspect could not find it - see %DETAIL_LOG%^).
    echo   For reference, volumes that DO exist on this machine:
    echo.
    call docker volume ls
    echo.
    echo   This is never auto-created - a fresh, empty volume under this name
    echo   would silently look like a working database while containing none
    echo   of the real clinic's data. Verify POSTGRES_VOLUME_NAME in .env
    echo   against the list above and fix whichever one is wrong. See
    echo   docs\DOCKER_UPDATE_PROCEDURE.md's "Volume identity" section.
    echo   Nothing was built or restarted.
    endlocal
    exit /b 1
)
echo   OK - configured volume "%POSTGRES_VOLUME_NAME%" exists.

REM Cross-check: is the RUNNING connectph-postgres container actually using
REM this exact volume for its data directory? (existence alone, above,
REM would not catch a correctly-existing-but-wrong volume name.)
set "MOUNT_FILE=%TEMP%\cms_docker_pg_mount_%RANDOM%.txt"
call docker inspect -f "{{range .Mounts}}{{if eq .Destination \"/var/lib/postgresql/data\"}}{{.Name}}{{end}}{{end}}" connectph-postgres > "%MOUNT_FILE%" 2>>"%DETAIL_LOG%"
if errorlevel 1 (
    echo   [WARN] connectph-postgres container not found/not running - cannot
    echo   cross-verify its actual mounted volume. Proceeding on the basis of
    echo   the volume-existence check above only ^(expected only on a genuine
    echo   first-time bootstrap - if this is an already-running clinic
    echo   install, this is unexpected and worth investigating before
    echo   continuing^).
    del "%MOUNT_FILE%" >nul 2>&1
    endlocal
    exit /b 0
)
set "ACTUAL_PG_MOUNT="
set /p ACTUAL_PG_MOUNT=<"%MOUNT_FILE%"
del "%MOUNT_FILE%" >nul 2>&1
if not "%ACTUAL_PG_MOUNT%"=="%POSTGRES_VOLUME_NAME%" (
    echo.
    echo   [FAIL] Refusing to proceed.
    echo.
    echo   connectph-postgres is currently running with its data directory
    echo   mounted from volume "%ACTUAL_PG_MOUNT%", but .env's
    echo   POSTGRES_VOLUME_NAME says "%POSTGRES_VOLUME_NAME%". These MUST
    echo   match - proceeding could build/restart against the wrong database
    echo   entirely. Fix POSTGRES_VOLUME_NAME in .env to
    echo   "%ACTUAL_PG_MOUNT%" ^(the value the container is actually,
    echo   currently using^) and re-run. Nothing was built or restarted.
    endlocal
    exit /b 1
)
echo   OK - connectph-postgres is confirmed running with volume "%POSTGRES_VOLUME_NAME%".

REM Same existence check for the other two production volumes - parity with
REM Postgres above. No running-container mount cross-check for these two
REM (Redis' cache volume and the backend's /app/var volume are lower-stakes
REM than the primary clinic database, and connectph-redis/connectph-backend
REM don't need the same "which exact clinic" scrutiny a Postgres data
REM volume does) - but a wrong or missing name must still fail closed here,
REM before any build, exactly like Postgres.
call docker volume inspect "%REDIS_VOLUME_NAME%" >nul 2>>"%DETAIL_LOG%"
if errorlevel 1 (
    echo.
    echo   [FAIL] Refusing to proceed.
    echo   The configured volume "%REDIS_VOLUME_NAME%" ^(REDIS_VOLUME_NAME in
    echo   .env^) does not exist on this machine. See %DETAIL_LOG% and
    echo   docs\DOCKER_UPDATE_PROCEDURE.md's "Volume identity" section.
    echo   Nothing was built or restarted.
    endlocal
    exit /b 1
)
echo   OK - configured volume "%REDIS_VOLUME_NAME%" exists.

call docker volume inspect "%BACKEND_VAR_VOLUME_NAME%" >nul 2>>"%DETAIL_LOG%"
if errorlevel 1 (
    echo.
    echo   [FAIL] Refusing to proceed.
    echo   The configured volume "%BACKEND_VAR_VOLUME_NAME%"
    echo   ^(BACKEND_VAR_VOLUME_NAME in .env^) does not exist on this machine.
    echo   See %DETAIL_LOG% and docs\DOCKER_UPDATE_PROCEDURE.md's "Volume
    echo   identity" section. Nothing was built or restarted.
    endlocal
    exit /b 1
)
echo   OK - configured volume "%BACKEND_VAR_VOLUME_NAME%" exists.
endlocal
exit /b 0

REM --- :docker_backup -------------------------------------------------------------
REM Mandatory pre-migration backup, run entirely via `docker exec` - no host
REM Python/pg_dump/DB-port dependency at all (the real Server PC has neither
REM a backend venv nor a host-reachable Postgres port - see
REM docs/DOCKER_UPDATE_PROCEDURE.md). A Python-based equivalent with fuller
REM retention (backend/scripts/backup_docker.py) exists for hosts that do
REM have Python provisioned, but this gating step never depends on it.
:docker_backup
setlocal DisableDelayedExpansion
set "BK_BACKUP_DIR=%BACKEND_DIR%\backups"
if not exist "%BK_BACKUP_DIR%" mkdir "%BK_BACKUP_DIR%" >nul 2>&1
set "BK_DEST=%BK_BACKUP_DIR%\docker-backup-%RUN_TS%.sql"

set "BK_RUNNING_FILE=%TEMP%\cms_docker_pg_running_%RANDOM%.txt"
call docker inspect -f "{{.State.Running}}" connectph-postgres > "%BK_RUNNING_FILE%" 2>>"%DETAIL_LOG%"
set "BK_PG_RUNNING="
set /p BK_PG_RUNNING=<"%BK_RUNNING_FILE%"
del "%BK_RUNNING_FILE%" >nul 2>&1
if not "%BK_PG_RUNNING%"=="true" (
    echo   [FAIL] connectph-postgres container is not running - cannot back up.
    endlocal
    exit /b 1
)

call docker exec connectph-postgres pg_dump -U connectph --format=plain canora_clinic > "%BK_DEST%" 2>>"%DETAIL_LOG%"
if errorlevel 1 (
    echo   [FAIL] docker exec pg_dump failed - see %DETAIL_LOG%.
    endlocal
    exit /b 1
)
for %%A in ("%BK_DEST%") do set "BK_SIZE=%%~zA"
if "%BK_SIZE%"=="0" (
    echo   [FAIL] Backup file is empty - %BK_DEST%.
    endlocal
    exit /b 1
)
findstr /c:"PostgreSQL database dump" "%BK_DEST%" >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] Backup file does not look like real pg_dump output - %BK_DEST%.
    endlocal
    exit /b 1
)
echo   [ OK ] Docker backup verified ^(%BK_SIZE% bytes^) at %BK_DEST%
>>"%BK_BACKUP_DIR%\backup_log.txt" echo %RUN_TS% SUCCESS: Docker backup verified (%BK_SIZE% bytes) at %BK_DEST%
endlocal
exit /b 0

REM --- :record_history <RESULT> <REASON> -------------------------------------
:record_history
setlocal DisableDelayedExpansion
set "HIST_RESULT=%~1"
set "HIST_REASON=%~2"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format o"') do set "NOW_ISO=%%i"
>>"%HISTORY_LOG%" echo %NOW_ISO% ^| old=%OLD_SHA% ^| new=%NEW_SHA% ^| migration=%MIGRATION_RESULT% ^| result=%HIST_RESULT% ^| reason=%HIST_REASON% ^| log=%DETAIL_LOG%
endlocal
exit /b 0
