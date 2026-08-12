@echo off
REM ---------------------------------------------------------------------------
REM install-backend-service.bat  -  Phase 2.6 Local Production Deployment
REM
REM *** DOES NOT RUN AUTOMATICALLY. WRITTEN, NOT EXECUTED, BY DESIGN. ***
REM
REM Registers the FastAPI backend as a Windows Service via NSSM: auto-start
REM on boot, auto-restart on crash, stdout/stderr to log files, runs
REM without a logged-in user (LocalSystem - see "Service account choice"
REM below and in docs/WINDOWS_SERVICE_SETUP.md).
REM
REM Uses plain uvicorn (not Gunicorn+Uvicorn-workers, unlike the Linux
REM systemd unit at deploy/connectph-backend.service) because Gunicorn does
REM not run on Windows (it forks, which Windows doesn't support) - uvicorn
REM alone is the correct Windows-native equivalent. A single clinic-desktop
REM install serving a handful of concurrent staff does not need multiple
REM worker processes; if this ever becomes a bottleneck, uvicorn supports
REM `--workers N` on Windows too (added here as a commented-out option).
REM
REM PREREQUISITES:
REM   1. NSSM installed and on PATH (see install-postgres-service.bat).
REM   2. backend\.venv provisioned on the clinic machine:
REM        cd backend && python -m venv .venv && .venv\Scripts\pip install -e .
REM   3. backend\.env.production copied from backend\.env.local-production.example
REM      and filled in with real production values (JWT secret, etc.) - see
REM      docs/LOCAL_DEPLOYMENT.md. Then copy/rename it to backend\.env
REM      (Settings always loads a file literally named .env).
REM   4. PostgreSQL service (install-postgres-service.bat) already installed,
REM      since this service DependsOn it (won't start before it).
REM   5. Open an elevated Command Prompt, cd to deploy\windows, run this script.
REM ---------------------------------------------------------------------------
setlocal
call "%~dp0_common.bat"

where nssm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] nssm.exe not found on PATH. Install NSSM first - see docs/WINDOWS_SERVICE_SETUP.md.
    exit /b 1
)

set "SERVICE_NAME=CONNECTPH-Backend"
set "PG_SERVICE_NAME=CONNECTPH-Postgres"

echo Installing Windows Service "%SERVICE_NAME%" ...
nssm install %SERVICE_NAME% "%PYTHON_EXE%" "-m uvicorn app.main:app --host %BACKEND_HOST% --port %BACKEND_PORT%"
REM For higher concurrency later, uvicorn also supports multiple workers on
REM Windows (no Gunicorn required):
REM   nssm set %SERVICE_NAME% AppParameters "-m uvicorn app.main:app --host %BACKEND_HOST% --port %BACKEND_PORT% --workers 4"

nssm set %SERVICE_NAME% AppDirectory "%BACKEND_DIR%"
nssm set %SERVICE_NAME% DisplayName "CONNECT.PH Clinic Platform - Backend (FastAPI)"
nssm set %SERVICE_NAME% Description "FastAPI backend for the CONNECT.PH local clinic install. Depends on %PG_SERVICE_NAME%. Reads backend\.env."
nssm set %SERVICE_NAME% Start SERVICE_AUTO_START
nssm set %SERVICE_NAME% ObjectName LocalSystem
REM --- Startup ordering: do not start until Postgres service is running. ---
nssm set %SERVICE_NAME% DependOnService %PG_SERVICE_NAME%
nssm set %SERVICE_NAME% AppStdout "%LOG_DIR%\backend-service.log"
nssm set %SERVICE_NAME% AppStderr "%LOG_DIR%\backend-service-error.log"
nssm set %SERVICE_NAME% AppRotateFiles 1
nssm set %SERVICE_NAME% AppRotateBytes 10485760
REM Auto-restart on crash, with a delay to avoid a crash-loop pegging the CPU.
nssm set %SERVICE_NAME% AppExit Default Restart
nssm set %SERVICE_NAME% AppRestartDelay 5000
REM Give the DB a moment even though DependOnService already orders the
REM services - NSSM's DependOnService controls START ORDER, not READINESS
REM (Postgres' Windows service can report "running" slightly before it is
REM actually accepting connections). This throttle plus uvicorn's own DB
REM connection-pool retry-on-first-use covers the gap; see
REM docs/WINDOWS_SERVICE_SETUP.md "Startup order / race conditions" for the
REM full explanation and why check_health.bat's polling (not a fixed sleep)
REM is still the authoritative way to confirm real readiness after boot.
nssm set %SERVICE_NAME% AppThrottle 5000

echo.
echo Done. Start it with:   nssm start %SERVICE_NAME%
echo Check status with:     nssm status %SERVICE_NAME%
echo Remove it with:        nssm remove %SERVICE_NAME% confirm
exit /b 0
