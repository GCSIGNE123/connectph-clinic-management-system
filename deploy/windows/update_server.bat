@echo off
REM ---------------------------------------------------------------------------
REM update_server.bat  -  Phase 2.6+ Local Production Deployment: the ONE
REM entry point for updating an already-installed clinic Server PC from one
REM approved GitHub commit to the next.
REM
REM *** SCOPED TO THE NSSM/MANUAL-WINDOWS-PROCESS ARCHITECTURE ONLY ***
REM (portable Postgres under .devdb\, a backend\.venv, `next start`, three
REM NSSM-registered Windows Services). The actual Canora Medical Clinic
REM Server PC uses a DIFFERENT, Docker-based architecture instead
REM (docker\docker-compose.prod.yml, containers, no backend\.venv) - for
REM that machine, use docs\DOCKER_UPDATE_PROCEDURE.md and the repo-root
REM `deploy.cmd`, never this script. If you are not certain which
REM architecture a given Server PC actually runs, check for Docker Desktop
REM and `docker ps` showing connectph-postgres/-backend/-frontend before
REM assuming this script applies - see DOCKER_UPDATE_PROCEDURE.md's "Which
REM updater do I actually run?" table.
REM
REM *** Run this ONLY on a real NSSM-architecture clinic Server PC, by a
REM     human, after the new code has already been reviewed/approved on
REM     GitHub. Never on the Dev PC as a substitute for `git pull` during
REM     development. ***
REM
REM See docs\UPDATE_PROCEDURE.md for the full runbook (prerequisites, what
REM this script refuses to do, failure recovery, and how production .env
REM files are protected). This header is a summary, not the authoritative doc.
REM
REM WHAT THIS SCRIPT DOES, IN ORDER:
REM   1.  Verifies this really is the CMS git repository.
REM   2.  Verifies the working tree is clean (no local edits, nothing
REM       uncommitted) - refuses to run otherwise.
REM   3.  Fetches from GitHub (does not change any files yet).
REM   4.  Records the currently-deployed commit, confirms the repo is on
REM       branch `main` (refuses on any other branch or a detached HEAD -
REM       this script only ever knows how to update `main`), and warns
REM       (does not fail) if local commits exist that were never pushed.
REM   5.  Fast-forwards to origin/main (`git merge --ff-only` - NEVER a hard
REM       reset, NEVER a force-checkout, NEVER `git clean`).
REM   6.  Compares old vs. new commit to decide what actually changed.
REM   7.  Reinstalls backend dependencies ONLY if backend\pyproject.toml changed.
REM   8.  Reinstalls + rebuilds the frontend ONLY if frontend source/deps changed.
REM   9.  If any new Alembic migration is present: backs up the database
REM       FIRST (the existing, verified `run_backup.bat`), then runs
REM       `alembic upgrade head`. A migration failure stops the script
REM       immediately - services are NOT restarted against a half-migrated
REM       or unknown schema state.
REM  10.  Restarts ONLY the services whose inputs actually changed - Backend
REM       restarts on any backend/app code, dependency, or migration change;
REM       Frontend restarts (after a fresh build) on any frontend source or
REM       dependency change. Postgres is never restarted for an ordinary
REM       application update.
REM  11.  Writes deployment metadata (git commit + timestamp) to the
REM       gitignored `backend\deploy_info.json` - NEVER to backend\.env or
REM       any other human-managed config file - so `/health`/`/system/status`
REM       already reflect the new commit by the time the health check below runs.
REM  12.  Runs the existing `check_health.bat`.
REM  13.  Prints a clear DEPLOYMENT SUCCESS / DEPLOYMENT FAILED banner and
REM       appends one line to deploy\windows\logs\update-history.log.
REM
REM WHAT THIS SCRIPT WILL NEVER DO (see docs\UPDATE_PROCEDURE.md for why):
REM   - git reset --hard / git checkout -f / git clean -fd / git clean -fdx
REM   - overwrite backend\.env, backend\.env.production, frontend\.env*,
REM     or any other file already excluded from git via .gitignore
REM   - restart CONNECTPH-Postgres for an ordinary code update
REM   - restart backend/frontend services after a failed migration
REM   - attempt an automatic database downgrade/rollback
REM   - proceed over an uncommitted/dirty working tree
REM ---------------------------------------------------------------------------
setlocal EnableExtensions EnableDelayedExpansion
call "%~dp0_common.bat"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "RUN_TS=%%i"
set "DETAIL_LOG=%LOG_DIR%\update-%RUN_TS%.log"
set "HISTORY_LOG=%LOG_DIR%\update-history.log"
type nul > "%DETAIL_LOG%"

set "MIGRATION_REQUIRED=0"
set "MIGRATION_RESULT=not required"
set "RESTART_BACKEND=0"
set "RESTART_FRONTEND=0"
set "OLD_SHA=unknown"
set "NEW_SHA=unknown"
set "FAIL_REASON="

echo ============================================================
echo  CONNECT.PH Clinic Platform - Server update
echo  %RUN_TS%
echo ============================================================
echo.

REM --- [1/13] Verify this is the CMS repository -----------------------------
echo [1/13] Checking repository...
if not exist "%CMS_ROOT%\.git" (
    set "FAIL_REASON=Not a git repository - %CMS_ROOT%\.git does not exist. Nothing was changed."
    goto :fail
)
git -C "%CMS_ROOT%" rev-parse --is-inside-work-tree >>"%DETAIL_LOG%" 2>&1
if errorlevel 1 (
    set "FAIL_REASON=git rev-parse failed - is git installed and on PATH? See %DETAIL_LOG%."
    goto :fail
)
echo [ OK ]
echo.

REM --- [2/13] Verify a clean working tree ------------------------------------
echo [2/13] Checking working tree is clean...
set "DIRTY_CHECK=%TEMP%\cms_update_dirty_%RUN_TS%.txt"
git -C "%CMS_ROOT%" status --porcelain > "%DIRTY_CHECK%" 2>>"%DETAIL_LOG%"
for %%A in ("%DIRTY_CHECK%") do set "DIRTY_SIZE=%%~zA"
if not "%DIRTY_SIZE%"=="0" (
    echo [FAIL]
    echo.
    echo   The working tree on THIS machine has uncommitted or unknown
    echo   changes. Deploying over this would risk losing them and makes
    echo   it impossible to know exactly what is running. Resolve this
    echo   first - a Server PC should never have unreviewed local edits:
    echo.
    type "%DIRTY_CHECK%"
    echo.
    del "%DIRTY_CHECK%" >nul 2>&1
    set "FAIL_REASON=Working tree is not clean - see console output above / %DETAIL_LOG% for the exact files."
    goto :fail
)
del "%DIRTY_CHECK%" >nul 2>&1
echo [ OK ]
echo.

REM --- [3/13] Fetch from GitHub -----------------------------------------------
echo [3/13] Fetching GitHub...
git -C "%CMS_ROOT%" fetch origin >>"%DETAIL_LOG%" 2>&1
if errorlevel 1 (
    set "FAIL_REASON=git fetch origin failed - check network/GitHub connectivity. See %DETAIL_LOG%."
    goto :fail
)
echo [ OK ]
echo.

REM --- [4/13] Record current commit -------------------------------------------
echo [4/13] Recording current commit...
for /f %%i in ('git -C "%CMS_ROOT%" rev-parse HEAD') do set "OLD_SHA=%%i"
for /f %%i in ('git -C "%CMS_ROOT%" rev-parse --abbrev-ref HEAD') do set "CURRENT_BRANCH=%%i"
echo   Currently deployed: %OLD_SHA%
echo   Current branch:     %CURRENT_BRANCH%
if not "%CURRENT_BRANCH%"=="main" (
    echo [FAIL]
    echo.
    echo   This machine is on branch/state "%CURRENT_BRANCH%", not "main"
    echo   ^(a value of "HEAD" here means detached HEAD^). This script only
    echo   ever updates to origin/main - deploying from any other branch or
    echo   a detached checkout is not something it should guess about. A
    echo   human must check out "main" deliberately first ^(and confirm
    echo   that's actually correct for this Server PC^) before re-running.
    set "FAIL_REASON=Not on branch main (currently: %CURRENT_BRANCH%) - see console output above."
    goto :fail
)
set "UNPUSHED_CHECK=%TEMP%\cms_update_unpushed_%RUN_TS%.txt"
git -C "%CMS_ROOT%" log --oneline origin/main..HEAD > "%UNPUSHED_CHECK%" 2>>"%DETAIL_LOG%"
for %%A in ("%UNPUSHED_CHECK%") do set "UNPUSHED_SIZE=%%~zA"
if not "%UNPUSHED_SIZE%"=="0" (
    echo   [WARN] This machine has commits that are not on origin/main yet:
    type "%UNPUSHED_CHECK%"
    echo   These are NOT lost or discarded ^(a fast-forward merge never
    echo   removes commits^), but a Server PC should never carry commits
    echo   GitHub doesn't have - confirm this is expected.
)
del "%UNPUSHED_CHECK%" >nul 2>&1
echo [ OK ]
echo.

REM --- [5/13] Fast-forward to origin/main ---------------------------------------
echo [5/13] Updating to origin/main (fast-forward only)...
git -C "%CMS_ROOT%" merge --ff-only origin/main >>"%DETAIL_LOG%" 2>&1
if errorlevel 1 (
    echo [FAIL]
    echo.
    echo   `git merge --ff-only origin/main` failed. This means the local
    echo   branch has diverged from origin/main - most likely local commits
    echo   that were never pushed. This script will NEVER force this with a
    echo   reset/checkout, since that could silently discard real work.
    echo   A human must resolve this manually ^(e.g. `git log origin/main..HEAD`
    echo   to see what's local-only, then decide whether to push it, rebase,
    echo   or discard it deliberately^) before re-running this script.
    echo.
    set "FAIL_REASON=git merge --ff-only failed (diverged history) - see %DETAIL_LOG%."
    goto :fail
)
echo [ OK ]
echo.

REM --- [6/13] Determine what changed -------------------------------------------
echo [6/13] Comparing old and new commit...
for /f %%i in ('git -C "%CMS_ROOT%" rev-parse HEAD') do set "NEW_SHA=%%i"
echo   Old commit: %OLD_SHA%
echo   New commit: %NEW_SHA%

if "%OLD_SHA%"=="%NEW_SHA%" (
    echo   Already up to date - nothing to deploy.
    echo [ OK ]
    echo.
    REM Still record deploy_info.json (idempotent - it's just confirming
    REM the already-running commit) and still run the health check below;
    REM only the dependency/build/migration/restart steps are genuinely
    REM unnecessary when nothing changed.
    goto :record_deploy_info
)

set "BACKEND_DEPS_CHANGED=0"
set "BACKEND_APP_CHANGED=0"
set "FRONTEND_DEPS_CHANGED=0"
set "FRONTEND_SRC_CHANGED=0"

call :diff_nonempty "backend/pyproject.toml"
if not errorlevel 1 set "BACKEND_DEPS_CHANGED=1"
call :diff_nonempty "backend/app"
if not errorlevel 1 (
    set "BACKEND_APP_CHANGED=1"
    set "RESTART_BACKEND=1"
)
call :diff_nonempty "frontend/package.json" "frontend/package-lock.json"
if not errorlevel 1 set "FRONTEND_DEPS_CHANGED=1"
call :diff_nonempty "frontend/src" "frontend/public" "frontend/next.config.ts" "frontend/tailwind.config.ts" "frontend/postcss.config.js" "frontend/package.json" "frontend/package-lock.json"
if not errorlevel 1 set "FRONTEND_SRC_CHANGED=1"
call :diff_nonempty "backend/alembic/versions"
if not errorlevel 1 set "MIGRATION_REQUIRED=1"

echo   Backend dependency changes:   !BACKEND_DEPS_CHANGED!
echo   Backend app code changes:     !BACKEND_APP_CHANGED!
echo   Frontend dependency changes:  !FRONTEND_DEPS_CHANGED!
echo   Frontend build-input changes: !FRONTEND_SRC_CHANGED!
echo   New Alembic migrations:       !MIGRATION_REQUIRED!
echo [ OK ]
echo.

REM --- [7/13] Backend dependencies -----------------------------------------------
echo [7/13] Backend dependencies...
if "!BACKEND_DEPS_CHANGED!"=="1" (
    echo   backend\pyproject.toml changed - reinstalling...
    pushd "%BACKEND_DIR%"
    "%PYTHON_EXE%" -m pip install -e . >>"%DETAIL_LOG%" 2>&1
    set "PIP_RC=!ERRORLEVEL!"
    popd
    if not "!PIP_RC!"=="0" (
        set "FAIL_REASON=Backend dependency install failed (pip install -e . exit !PIP_RC!) - see %DETAIL_LOG%."
        goto :fail
    )
    set "RESTART_BACKEND=1"
    echo [ OK ]
) else (
    echo   No backend dependency changes - skipped.
    echo [ SKIPPED ]
)
echo.

REM --- [8/13] Frontend dependencies + build -----------------------------------
echo [8/13] Frontend dependencies and build...
if "!FRONTEND_DEPS_CHANGED!"=="1" (
    echo   frontend package.json/package-lock.json changed - running npm ci...
    pushd "%FRONTEND_DIR%"
    call npm ci >>"%DETAIL_LOG%" 2>&1
    set "NPM_CI_RC=!ERRORLEVEL!"
    popd
    if not "!NPM_CI_RC!"=="0" (
        set "FAIL_REASON=npm ci failed (exit !NPM_CI_RC!) - see %DETAIL_LOG%."
        goto :fail
    )
)
if "!FRONTEND_SRC_CHANGED!"=="1" (
    echo   Frontend source/build inputs changed - running npm run build...
    pushd "%FRONTEND_DIR%"
    call npm run build >>"%DETAIL_LOG%" 2>&1
    set "NPM_BUILD_RC=!ERRORLEVEL!"
    popd
    if not "!NPM_BUILD_RC!"=="0" (
        set "FAIL_REASON=npm run build failed (exit !NPM_BUILD_RC!) - see %DETAIL_LOG%. The previous .next\ build was NOT replaced by a failed build, but confirm before restarting the Frontend service manually."
        goto :fail
    )
    set "RESTART_FRONTEND=1"
    echo [ OK ]
) else (
    echo   No frontend build-relevant changes - skipped.
    echo [ SKIPPED ]
)
echo.

REM --- [9/13] Migrations (with mandatory pre-migration backup) ------------------
echo [9/13] Database migrations...
if "!MIGRATION_REQUIRED!"=="1" (
    echo   [MIGRATION REQUIRED] New Alembic migration^(s^) detected under backend\alembic\versions.
    echo.
    echo   [BACKUP REQUIRED] Creating pre-migration backup via the existing
    echo   verified backup procedure ^(deploy\windows\run_backup.bat^)...
    call "%~dp0run_backup.bat" >>"%DETAIL_LOG%" 2>&1
    set "BACKUP_RC=!ERRORLEVEL!"
    if not "!BACKUP_RC!"=="0" (
        echo   [FAIL] Pre-migration backup failed ^(exit !BACKUP_RC!^).
        echo   Migration was NOT attempted. Services were NOT restarted.
        echo   See backend\backups\backup_log.txt and %DETAIL_LOG% for detail.
        set "MIGRATION_RESULT=backup failed - migration not attempted"
        set "FAIL_REASON=Pre-migration backup failed - see backend\backups\backup_log.txt and %DETAIL_LOG%."
        goto :fail
    )
    echo   [ OK ] Backup created and verified.
    echo.
    echo   Running: alembic upgrade head ...
    pushd "%BACKEND_DIR%"
    "%PYTHON_EXE%" -m alembic upgrade head >>"%DETAIL_LOG%" 2>&1
    set "ALEMBIC_RC=!ERRORLEVEL!"
    popd
    if not "!ALEMBIC_RC!"=="0" (
        echo   [FAIL] alembic upgrade head FAILED ^(exit !ALEMBIC_RC!^).
        echo.
        echo   ================================================================
        echo   DATABASE MIGRATION FAILED - THIS REQUIRES HUMAN INTERVENTION.
        echo   Backend/Frontend services were NOT restarted, so the OLD code
        echo   is still running - it will keep working against whatever
        echo   schema state the database was in before this migration attempt,
        echo   which may now be PARTIALLY migrated. Do not restart services
        echo   manually until this is resolved. See %DETAIL_LOG% for the exact
        echo   Alembic error, and docs\UPDATE_PROCEDURE.md's "After a failed
        echo   update" section for the recovery steps ^(the backup just taken
        echo   above is the safety net - see docs\BACKUP.md for restore^).
        echo   ================================================================
        set "MIGRATION_RESULT=FAILED - see %DETAIL_LOG%"
        set "FAIL_REASON=alembic upgrade head failed - see %DETAIL_LOG% and docs\UPDATE_PROCEDURE.md."
        goto :fail
    )
    echo   [ OK ] Migration applied successfully.
    set "MIGRATION_RESULT=applied successfully"
    set "RESTART_BACKEND=1"
) else (
    echo   No new migrations - skipped.
)
echo.

REM --- [10/13] Restart only the services that need it ---------------------------
echo [10/13] Restarting services as needed...
if "!RESTART_BACKEND!"=="1" (
    call :restart_service "CONNECTPH-Backend"
    if errorlevel 1 (
        set "FAIL_REASON=CONNECTPH-Backend failed to restart cleanly - see %DETAIL_LOG% and deploy\windows\logs\backend-service-error.log."
        goto :fail
    )
) else (
    echo   Backend restart not required - skipped.
)
if "!RESTART_FRONTEND!"=="1" (
    call :restart_service "CONNECTPH-Frontend"
    if errorlevel 1 (
        set "FAIL_REASON=CONNECTPH-Frontend failed to restart cleanly - see %DETAIL_LOG% and deploy\windows\logs\frontend-service-error.log."
        goto :fail
    )
) else (
    echo   Frontend restart not required - skipped.
)
echo   PostgreSQL was not touched - never restarted for an application update.
echo [ OK ]
echo.

:record_deploy_info
REM --- [11/13] Write deployment metadata (never backend\.env) -------------------
echo [11/13] Recording deployed commit...
pushd "%BACKEND_DIR%"
"%PYTHON_EXE%" scripts\write_deploy_info.py --commit "%NEW_SHA%" >>"%DETAIL_LOG%" 2>&1
set "DEPLOY_INFO_RC=!ERRORLEVEL!"
popd
if not "!DEPLOY_INFO_RC!"=="0" (
    echo   [WARN] Could not write backend\deploy_info.json ^(exit !DEPLOY_INFO_RC!^) -
    echo   the deploy itself still succeeded; only /health and /system/status
    echo   won't show the new commit until this is fixed. See %DETAIL_LOG%.
) else (
    echo [ OK ]
)
echo.

:health_check
REM --- [12/13] Health check -----------------------------------------------------
echo [12/13] Running health checks...
call "%~dp0check_health.bat"
set "HEALTH_RC=%ERRORLEVEL%"
echo.
if not "%HEALTH_RC%"=="0" (
    set "FAIL_REASON=Post-update health check reported failures - see the [FAIL] lines above."
    goto :fail
)

REM --- [13/13] Success ------------------------------------------------------------
echo [13/13] Finalizing...
echo   Detailed log: %DETAIL_LOG%
call :record_history "SUCCESS" ""
echo.
echo ============================================================
echo  DEPLOYMENT SUCCESS
echo.
echo  Previous commit: %OLD_SHA%
echo  New commit:      %NEW_SHA%
echo  Migration:       %MIGRATION_RESULT%
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
echo  See docs\UPDATE_PROCEDURE.md - "After a failed update" for next steps.
echo ============================================================
exit /b 1

REM =============================================================================
REM Subroutines
REM =============================================================================

REM --- :diff_nonempty <pathspec> [<pathspec> ...] -----------------------------
REM Sets ERRORLEVEL 0 if any of the given paths changed between OLD_SHA and
REM NEW_SHA, 1 otherwise. Never uses git pathspec exclusions (`:!...`) - `!`
REM is a delayed-expansion metacharacter in this script, so exclusion
REM pathspecs would be unreliable here; the trade-off is a same-directory
REM change (e.g. a backend test file, not just app code) can trigger a
REM restart/rebuild slightly more often than strictly necessary, which is
REM safe, just not maximally minimal - see docs\UPDATE_PROCEDURE.md.
:diff_nonempty
setlocal DisableDelayedExpansion
set "DIFF_FILE=%TEMP%\cms_update_diff_%RANDOM%.txt"
git -C "%CMS_ROOT%" diff --name-only %OLD_SHA% %NEW_SHA% -- %* > "%DIFF_FILE%" 2>>"%DETAIL_LOG%"
for %%A in ("%DIFF_FILE%") do set "SIZE=%%~zA"
del "%DIFF_FILE%" >nul 2>&1
if "%SIZE%"=="0" (
    endlocal
    exit /b 1
)
endlocal
exit /b 0

REM --- :restart_service <ServiceName> -----------------------------------------
REM Restarts a registered NSSM/Windows Service via plain `net stop`/`net
REM start` (works with any Windows Service regardless of whether nssm.exe is
REM on PATH). If the named service isn't registered at all, this Server PC
REM is presumably still on the manual/non-service setup - warns and returns
REM failure rather than silently doing nothing, so the caller can decide
REM whether that's expected.
:restart_service
setlocal DisableDelayedExpansion
set "SVC=%~1"
echo   Restarting %SVC% ...
sc query "%SVC%" >nul 2>&1
if errorlevel 1 (
    echo   [WARN] Windows Service "%SVC%" is not registered on this machine.
    echo   If this Server PC uses the manual/non-service setup instead, restart
    echo   it yourself via deploy\windows\restart_clinic.bat after this script finishes.
    endlocal
    exit /b 1
)
REM `net stop` on an already-stopped service returns non-zero - that's not a
REM failure for our purposes, only a failed `net start` afterward is.
net stop "%SVC%" >>"%DETAIL_LOG%" 2>&1
net start "%SVC%" >>"%DETAIL_LOG%" 2>&1
if errorlevel 1 (
    echo   [FAIL] %SVC% did not start cleanly - see %DETAIL_LOG%.
    endlocal
    exit /b 1
)
echo   [ OK ] %SVC% restarted.
endlocal
exit /b 0

REM --- :record_history <RESULT> <REASON> --------------------------------------
REM Appends exactly one line to deploy\windows\logs\update-history.log per
REM run - the single authoritative "what happened, when" record (see
REM docs\UPDATE_PROCEDURE.md). Never a second, competing logging mechanism -
REM the full step-by-step transcript for a given run stays in that run's own
REM %DETAIL_LOG% instead.
:record_history
setlocal DisableDelayedExpansion
set "HIST_RESULT=%~1"
set "HIST_REASON=%~2"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format o"') do set "NOW_ISO=%%i"
>>"%HISTORY_LOG%" echo %NOW_ISO% ^| old=%OLD_SHA% ^| new=%NEW_SHA% ^| migration=%MIGRATION_RESULT% ^| result=%HIST_RESULT% ^| reason=%HIST_REASON% ^| log=%DETAIL_LOG%
endlocal
exit /b 0
