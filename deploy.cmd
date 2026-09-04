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
REM        refuses to proceed if the pinned volume names don't exist yet
REM        AND a differently-named data volume is already present (see
REM        docker/docker-compose.prod.yml's volume-pinning comment).
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
set "PROJECT_FLAG="

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
    echo This file is required - it supplies POSTGRES_PASSWORD and the
    echo optional CLINIC_API_BASE_URL / CLINIC_FRONTEND_ORIGIN /
    echo COMPOSE_PROJECT_NAME_OVERRIDE overrides. Copy .env.example to .env
    echo and fill in the real values for this clinic - see .env.example.
    echo Nothing was pulled, validated, built, or restarted.
    set "FAIL_REASON=Repo-root .env is missing."
    goto :fail
)
REM Optional escape hatch - see .env.example's COMPOSE_PROJECT_NAME_OVERRIDE
REM comment. Only needed if a one-time volume-identity check (docs/
REM DOCKER_UPDATE_PROCEDURE.md) found this machine's real volumes were
REM created under a different project name than the pinned "canora_clinic".
set "COMPOSE_PROJECT_NAME_OVERRIDE="
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    if /i "%%A"=="COMPOSE_PROJECT_NAME_OVERRIDE" set "COMPOSE_PROJECT_NAME_OVERRIDE=%%B"
)
if defined COMPOSE_PROJECT_NAME_OVERRIDE (
    set "PROJECT_FLAG=-p !COMPOSE_PROJECT_NAME_OVERRIDE!"
    echo   OK - .env found ^(COMPOSE_PROJECT_NAME_OVERRIDE=!COMPOSE_PROJECT_NAME_OVERRIDE! in effect^).
) else (
    echo   OK - .env found ^(using the pinned project name "canora_clinic" from
    echo   docker-compose.prod.yml - no override set^).
)
echo.

REM --- [2/16] Verify this is the CMS repository --------------------------------
echo [2/16] Checking repository...
if not exist "%CMS_ROOT%\.git" (
    set "FAIL_REASON=Not a git repository - %CMS_ROOT%\.git does not exist. Nothing was changed."
    goto :fail
)
git rev-parse --is-inside-work-tree >>"%DETAIL_LOG%" 2>&1
if errorlevel 1 (
    set "FAIL_REASON=git rev-parse failed - is git installed and on PATH? See %DETAIL_LOG%."
    goto :fail
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
    goto :fail
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
    goto :fail
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
    goto :fail
)
git merge --ff-only origin/main >>"%DETAIL_LOG%" 2>&1
if errorlevel 1 (
    echo.
    echo FAILED: `git merge --ff-only origin/main` did not succeed - local and
    echo origin/main have diverged, or the remote is unreachable. This script
    echo will never force this with a reset/checkout. Resolve manually.
    set "FAIL_REASON=git merge --ff-only failed (diverged history) - see %DETAIL_LOG%."
    goto :fail
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

for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:8000/api/v1/health' -UseBasicParsing -TimeoutSec 5; $j = $r.Content | ConvertFrom-Json; if ($j.git_commit) { $j.git_commit } else { 'none' } } catch { 'unreachable' }"`) do set "RUNNING_SHA_BEFORE=%%i"
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
docker compose %ENV_FILE% %PROJECT_FLAG% %COMPOSE_FILES% config >>"%DETAIL_LOG%" 2>&1
if errorlevel 1 (
    echo.
    echo FAILED: the production Compose configuration is invalid, or .env is
    echo missing a required value ^(e.g. POSTGRES_PASSWORD^). See %DETAIL_LOG%.
    set "FAIL_REASON=docker compose config validation failed - see %DETAIL_LOG%."
    goto :fail
)
echo   OK.
echo.

REM --- [8/16] Protect production volumes ----------------------------------------
echo [8/16] Verifying production volume identity...
call :check_volume_protection
if errorlevel 1 (
    set "FAIL_REASON=Production volume identity check failed - see console output above and %DETAIL_LOG%."
    goto :fail
)
echo.

REM --- [9/16] Build affected images only -----------------------------------------
echo [9/16] Building images for changed services...
set "GIT_COMMIT=%NEW_SHA%"
if "!BACKEND_CHANGED!"=="1" (
    echo   Building backend...
    docker compose %ENV_FILE% %PROJECT_FLAG% %COMPOSE_FILES% build backend >>"%DETAIL_LOG%" 2>&1
    if errorlevel 1 (
        set "FAIL_REASON=docker compose build backend failed - see %DETAIL_LOG%. Previous container is still running, untouched."
        goto :fail
    )
) else (
    echo   Backend image unchanged - skipped.
)
if "!FRONTEND_CHANGED!"=="1" (
    echo   Building frontend...
    docker compose %ENV_FILE% %PROJECT_FLAG% %COMPOSE_FILES% build frontend >>"%DETAIL_LOG%" 2>&1
    if errorlevel 1 (
        set "FAIL_REASON=docker compose build frontend failed - see %DETAIL_LOG%. Previous container is still running, untouched."
        goto :fail
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
        goto :fail
    )
    echo.
    echo   Running: docker exec connectph-backend python -m alembic upgrade head ...
    docker exec connectph-backend python -m alembic upgrade head >>"%DETAIL_LOG%" 2>&1
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
        goto :fail
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
    docker compose %ENV_FILE% %PROJECT_FLAG% %COMPOSE_FILES% up -d --no-deps backend >>"%DETAIL_LOG%" 2>&1
    if errorlevel 1 (
        set "FAIL_REASON=docker compose up -d --no-deps backend failed - see %DETAIL_LOG%."
        goto :fail
    )
    echo   [ OK ] backend restarted.
) else (
    echo   Backend restart not required - skipped.
)
if "!FRONTEND_CHANGED!"=="1" (
    docker compose %ENV_FILE% %PROJECT_FLAG% %COMPOSE_FILES% up -d --no-deps frontend >>"%DETAIL_LOG%" 2>&1
    if errorlevel 1 (
        set "FAIL_REASON=docker compose up -d --no-deps frontend failed - see %DETAIL_LOG%."
        goto :fail
    )
    echo   [ OK ] frontend restarted.
) else (
    echo   Frontend restart not required - skipped.
)
echo   postgres/redis were not touched - never recreated for an app update.
echo.

REM --- [12/16] Current status ------------------------------------------------------
echo [12/16] Current container status:
docker compose %ENV_FILE% %PROJECT_FLAG% %COMPOSE_FILES% ps
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

docker exec connectph-postgres pg_isready -U connectph >>"%DETAIL_LOG%" 2>&1
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
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:8000/api/v1/health' -UseBasicParsing -TimeoutSec 5; $j = $r.Content | ConvertFrom-Json; if ($j.git_commit) { $j.git_commit } else { 'none' } } catch { 'unreachable' }"`) do set "RUNNING_SHA_AFTER=%%i"
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
    goto :fail
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
REM Refuses to let Compose silently create a fresh, empty volume in place of
REM a real one that already exists under a different name - see
REM docker/docker-compose.prod.yml's volume-pinning comment and
REM docs/DOCKER_UPDATE_PROCEDURE.md's "Volume identity" section. Read-only
REM (`docker volume ls`) - never creates, renames, or deletes anything itself.
:check_volume_protection
setlocal DisableDelayedExpansion
set "VOL_LIST=%TEMP%\cms_docker_volumes_%RUN_TS%.txt"
docker volume ls --format "{{.Name}}" > "%VOL_LIST%" 2>>"%DETAIL_LOG%"
if errorlevel 1 (
    echo   [FAIL] Could not list Docker volumes - is Docker Desktop running?
    del "%VOL_LIST%" >nul 2>&1
    endlocal
    exit /b 1
)
findstr /x /c:"canora_postgres_data" "%VOL_LIST%" >nul 2>&1
if not errorlevel 1 (
    echo   OK - pinned production volume "canora_postgres_data" already exists.
    del "%VOL_LIST%" >nul 2>&1
    endlocal
    exit /b 0
)
findstr /e /c:"postgres_data" "%VOL_LIST%" >nul 2>&1
if not errorlevel 1 (
    echo.
    echo   [FAIL] Refusing to proceed.
    echo.
    echo   The pinned production volume "canora_postgres_data" does not exist
    echo   yet, but a DIFFERENTLY-NAMED Postgres data volume already exists on
    echo   this machine:
    echo.
    for /f "usebackq delims=" %%L in ("%VOL_LIST%") do (
        echo %%L | findstr /e /c:"postgres_data" >nul 2>&1
        if not errorlevel 1 echo     %%L
    )
    echo.
    echo   Proceeding would make Docker silently create a NEW, EMPTY volume
    echo   named "canora_postgres_data" and use that instead of the real
    echo   clinic database. See docs\DOCKER_UPDATE_PROCEDURE.md's "Volume
    echo   identity - one-time verification" section for exactly how to fix
    echo   this safely. Nothing was built or restarted.
    del "%VOL_LIST%" >nul 2>&1
    endlocal
    exit /b 1
)
echo   No existing Postgres volume found anywhere on this machine - treating
echo   this as a first-time bootstrap. Compose will create fresh, empty
echo   "canora_postgres_data"/"canora_redis_data"/"canora_backend_var_data"
echo   volumes.
del "%VOL_LIST%" >nul 2>&1
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
docker inspect -f "{{.State.Running}}" connectph-postgres > "%BK_RUNNING_FILE%" 2>>"%DETAIL_LOG%"
set "BK_PG_RUNNING="
set /p BK_PG_RUNNING=<"%BK_RUNNING_FILE%"
del "%BK_RUNNING_FILE%" >nul 2>&1
if not "%BK_PG_RUNNING%"=="true" (
    echo   [FAIL] connectph-postgres container is not running - cannot back up.
    endlocal
    exit /b 1
)

docker exec connectph-postgres pg_dump -U connectph --format=plain canora_clinic > "%BK_DEST%" 2>>"%DETAIL_LOG%"
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
