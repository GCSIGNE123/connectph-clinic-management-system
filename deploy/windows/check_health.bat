@echo off
REM ---------------------------------------------------------------------------
REM check_health.bat  -  Phase 2.6 Local Production Deployment
REM
REM Read-only health check. Prints a clear PASS/FAIL summary for:
REM   - PostgreSQL (tcp reachability)
REM   - Backend      (/api/v1/health  - process up, no auth; also reports the
REM                   deployed Git commit - see backend/app/core/deploy_info.py)
REM   - Backend+DB   (/api/v1/ready   - DB reachable via SELECT 1, no auth)
REM   - Frontend     (http 200 on /)
REM   - Deployment mode / cloud backup status (/api/v1/system/status - needs
REM     an Owner/Administrator bearer token; skipped with a clear note if
REM     BACKEND_HEALTH_TOKEN is not set in the environment, since that
REM     endpoint is intentionally auth-gated - see
REM     backend/app/api/v1/system_status.py)
REM
REM Usage:
REM   check_health.bat
REM   set BACKEND_HEALTH_TOKEN=<a real Owner/Admin access token> & check_health.bat
REM
REM Exit code: 0 if every reachable check passed, 1 if anything failed.
REM ---------------------------------------------------------------------------
setlocal EnableDelayedExpansion
call "%~dp0_common.bat"

set "OVERALL_OK=1"

echo ============================================================
echo  CONNECT.PH Clinic Platform - health check
echo  %date% %time%
echo ============================================================

REM --- PostgreSQL -----------------------------------------------------------
echo.
"%PG_BIN%\pg_isready.exe" -p %PG_PORT% >nul 2>&1
if errorlevel 1 (
    echo [FAIL] PostgreSQL       - not accepting connections on port %PG_PORT%
    set "OVERALL_OK=0"
) else (
    echo [ OK ] PostgreSQL       - accepting connections on port %PG_PORT%
)

REM --- Backend liveness -------------------------------------------------------
REM Also prints the deployed Git commit (see backend/app/core/deploy_info.py) -
REM /api/v1/health is unauthenticated, so this answers "what commit is
REM running" with zero setup, unlike the System Status check below (needs
REM BACKEND_HEALTH_TOKEN). Shows "not recorded" (never a fabricated value)
REM on a machine that has never run update_server.bat.
powershell -NoProfile -Command ^
    "try { $r = Invoke-WebRequest -Uri 'http://localhost:%BACKEND_PORT%/api/v1/health' -UseBasicParsing -TimeoutSec 5; if ($r.StatusCode -ne 200) { exit 1 }; $j = $r.Content | ConvertFrom-Json; $commit = if ($j.git_commit_short) { $j.git_commit_short } else { 'not recorded' }; Write-Host ('[ OK ] Backend          - /api/v1/health responding on port %BACKEND_PORT% (deployed commit: ' + $commit + ')'); exit 0 } catch { exit 1 }"
if errorlevel 1 (
    echo [FAIL] Backend          - /api/v1/health not responding on port %BACKEND_PORT%
    set "OVERALL_OK=0"
)

REM --- Backend + DB readiness --------------------------------------------------
powershell -NoProfile -Command ^
    "try { $r = Invoke-WebRequest -Uri 'http://localhost:%BACKEND_PORT%/api/v1/ready' -UseBasicParsing -TimeoutSec 5; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }"
if errorlevel 1 (
    echo [FAIL] Backend DB       - /api/v1/ready failed ^(backend cannot reach Postgres^)
    set "OVERALL_OK=0"
) else (
    echo [ OK ] Backend DB       - /api/v1/ready OK ^(SELECT 1 against Postgres succeeded^)
)

REM --- Frontend -----------------------------------------------------------------
powershell -NoProfile -Command ^
    "try { $r = Invoke-WebRequest -Uri 'http://localhost:%FRONTEND_PORT%/' -UseBasicParsing -TimeoutSec 5; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }"
if errorlevel 1 (
    echo [FAIL] Frontend         - "/" not responding on port %FRONTEND_PORT%
    set "OVERALL_OK=0"
) else (
    echo [ OK ] Frontend         - "/" responding on port %FRONTEND_PORT%
)

REM --- Deployment mode / cloud backup (needs auth) -------------------------------
if "%BACKEND_HEALTH_TOKEN%"=="" (
    echo [SKIP] Deployment mode / cloud backup status - set BACKEND_HEALTH_TOKEN to an Owner/Admin access token to include this check ^(GET /api/v1/system/status is auth-gated by design^).
) else (
    powershell -NoProfile -Command ^
        "try { $r = Invoke-WebRequest -Uri 'http://localhost:%BACKEND_PORT%/api/v1/system/status' -Headers @{Authorization='Bearer %BACKEND_HEALTH_TOKEN%'} -UseBasicParsing -TimeoutSec 5; $j = $r.Content | ConvertFrom-Json; Write-Host ('[ OK ] System status     - deployment_mode=' + $j.deployment_mode + ' database_status=' + $j.database_status + ' cloud_status=' + $j.cloud_status + ' pending_sync_jobs=' + $j.pending_sync_jobs); exit 0 } catch { Write-Host '[FAIL] System status     - request failed or token invalid/expired'; exit 1 }"
    if errorlevel 1 set "OVERALL_OK=0"
)

echo.
echo ============================================================
if "%OVERALL_OK%"=="1" (
    echo  RESULT: ALL CHECKS PASSED
    echo ============================================================
    exit /b 0
) else (
    echo  RESULT: ONE OR MORE CHECKS FAILED - see [FAIL] lines above
    echo ============================================================
    exit /b 1
)
