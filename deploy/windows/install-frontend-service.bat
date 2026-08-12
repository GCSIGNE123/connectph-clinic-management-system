@echo off
REM ---------------------------------------------------------------------------
REM install-frontend-service.bat  -  Phase 2.6 Local Production Deployment
REM
REM *** DOES NOT RUN AUTOMATICALLY. WRITTEN, NOT EXECUTED, BY DESIGN. ***
REM
REM Registers the Next.js PRODUCTION frontend (next start, built via next
REM build - see docs/LOCAL_DEPLOYMENT.md "Production frontend build") as a
REM Windows Service via NSSM. Depends on the backend service so it never
REM starts before the API it talks to.
REM
REM PREREQUISITES:
REM   1. NSSM installed and on PATH.
REM   2. cd frontend && npm ci && npm run build   (produces .next\ - must be
REM      rebuilt any time frontend source or frontend\.env.production
REM      changes; NEXT_PUBLIC_* vars are baked in at build time, not read at
REM      runtime).
REM   3. frontend\.env.production copied from
REM      frontend\.env.local-production.example and filled in.
REM   4. Backend service (install-backend-service.bat) already installed.
REM   5. Open an elevated Command Prompt, cd to deploy\windows, run this script.
REM ---------------------------------------------------------------------------
setlocal
call "%~dp0_common.bat"

where nssm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] nssm.exe not found on PATH. Install NSSM first - see docs/WINDOWS_SERVICE_SETUP.md.
    exit /b 1
)

set "SERVICE_NAME=CONNECTPH-Frontend"
set "BACKEND_SERVICE_NAME=CONNECTPH-Backend"

for /f "delims=" %%N in ('where npm') do set "NPM_CMD=%%N"
if "%NPM_CMD%"=="" (
    echo [ERROR] npm not found on PATH.
    exit /b 1
)

echo Installing Windows Service "%SERVICE_NAME%" ...
nssm install %SERVICE_NAME% "%NPM_CMD%" "run start -- --port %FRONTEND_PORT%"
nssm set %SERVICE_NAME% AppDirectory "%FRONTEND_DIR%"
nssm set %SERVICE_NAME% DisplayName "CONNECT.PH Clinic Platform - Frontend (Next.js production)"
nssm set %SERVICE_NAME% Description "Next.js production server (next start) for the CONNECT.PH local clinic install. Depends on %BACKEND_SERVICE_NAME%."
nssm set %SERVICE_NAME% Start SERVICE_AUTO_START
nssm set %SERVICE_NAME% ObjectName LocalSystem
nssm set %SERVICE_NAME% DependOnService %BACKEND_SERVICE_NAME%
nssm set %SERVICE_NAME% AppStdout "%LOG_DIR%\frontend-service.log"
nssm set %SERVICE_NAME% AppStderr "%LOG_DIR%\frontend-service-error.log"
nssm set %SERVICE_NAME% AppRotateFiles 1
nssm set %SERVICE_NAME% AppRotateBytes 10485760
nssm set %SERVICE_NAME% AppExit Default Restart
nssm set %SERVICE_NAME% AppRestartDelay 5000
REM Give the backend a moment to actually accept requests, same rationale
REM as install-backend-service.bat's AppThrottle comment.
nssm set %SERVICE_NAME% AppThrottle 5000

echo.
echo Done. Start it with:   nssm start %SERVICE_NAME%
echo Check status with:     nssm status %SERVICE_NAME%
echo Remove it with:        nssm remove %SERVICE_NAME% confirm
exit /b 0
