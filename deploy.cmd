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
REM        pg_dump ...`, verified), then runs
REM        `docker exec connectph-backend python -m alembic upgrade head`.
REM        A migration failure stops the script immediately - containers
REM        are NOT restarted against a half-migrated or unknown schema.
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
set ENV_FILE=--env-file .env

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
echo   Migration required:       !MIGRATION_REQUIRED!
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

REM --- [10/16] Migrations (mandatory Docker-native backup first) ----------------
echo [10/16] Database migrations...
if "!MIGRATION_REQUIRED!"=="1" (
    echo   [MIGRATION REQUIRED] New Alembic migration^(s^) detected under backend\alembic\versions.
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
    echo   Running: docker exec connectph-backend python -m alembic upgrade head ...
    call docker exec connectph-backend python -m alembic upgrade head >>"%DETAIL_LOG%" 2>&1
    if errorlevel 1 (
        echo   [FAIL] alembic upgrade head FAILED inside connectph-backend.
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
        set "FAIL_REASON=alembic upgrade head failed inside connectph-backend - see %DETAIL_LOG%."
        call :fail
        exit /b 1
    )
    echo   [ OK ] Migration applied successfully.
    set "MIGRATION_RESULT=applied successfully"
    set "BACKEND_CHANGED=1"
) else (
    echo   No new migrations - skipped.
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
REM      (`docker volume ls`). docker-compose.prod.yml's `external: true`
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
REM See docker/docker-compose.prod.yml's header comment and
REM docs/DOCKER_UPDATE_PROCEDURE.md's "Volume identity" section.
:check_volume_protection
setlocal DisableDelayedExpansion
set "VOL_LIST=%TEMP%\cms_docker_volumes_%RUN_TS%.txt"
call docker volume ls --format "{{.Name}}" > "%VOL_LIST%" 2>>"%DETAIL_LOG%"
if errorlevel 1 (
    echo   [FAIL] Could not list Docker volumes - is Docker Desktop running?
    del "%VOL_LIST%" >nul 2>&1
    endlocal
    exit /b 1
)
findstr /x /c:"%POSTGRES_VOLUME_NAME%" "%VOL_LIST%" >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [FAIL] Refusing to proceed.
    echo.
    echo   The configured production volume "%POSTGRES_VOLUME_NAME%"
    echo   ^(POSTGRES_VOLUME_NAME in .env^) does not exist on this machine.
    echo   Existing volumes are:
    echo.
    type "%VOL_LIST%"
    echo.
    echo   This is never auto-created - a fresh, empty volume under this name
    echo   would silently look like a working database while containing none
    echo   of the real clinic's data. Verify POSTGRES_VOLUME_NAME in .env
    echo   against `docker volume ls` and fix whichever one is wrong. See
    echo   docs\DOCKER_UPDATE_PROCEDURE.md's "Volume identity" section.
    echo   Nothing was built or restarted.
    del "%VOL_LIST%" >nul 2>&1
    endlocal
    exit /b 1
)
del "%VOL_LIST%" >nul 2>&1
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
