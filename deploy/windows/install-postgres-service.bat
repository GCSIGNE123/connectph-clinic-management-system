@echo off
REM ---------------------------------------------------------------------------
REM install-postgres-service.bat  -  Phase 2.6 Local Production Deployment
REM
REM *** DOES NOT RUN AUTOMATICALLY. WRITTEN, NOT EXECUTED, BY DESIGN. ***
REM
REM Registers the existing portable PostgreSQL (.devdb\pgsql, .devdb\data -
REM UNTOUCHED, not a new install, not EnterpriseDB) as a Windows Service via
REM NSSM (https://nssm.cc/), so it auto-starts on boot before login and
REM auto-restarts if it ever crashes.
REM
REM PREREQUISITES (do this once, manually, as Administrator):
REM   1. Download NSSM (nssm.cc/download), extract nssm.exe (win64 build)
REM      somewhere on PATH, e.g. C:\Tools\nssm\nssm.exe.
REM   2. Open an elevated (Run as Administrator) Command Prompt.
REM   3. cd to this folder (deploy\windows) and run this script.
REM
REM Runs as LocalSystem (no logged-in user required - see
REM docs/WINDOWS_SERVICE_SETUP.md "Service account choice" for why
REM LocalSystem was chosen over a dedicated service account for this
REM single-machine, no-domain clinic install).
REM ---------------------------------------------------------------------------
setlocal
call "%~dp0_common.bat"

where nssm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] nssm.exe not found on PATH. Install NSSM first - see docs/WINDOWS_SERVICE_SETUP.md.
    exit /b 1
)

set "SERVICE_NAME=CONNECTPH-Postgres"

echo Installing Windows Service "%SERVICE_NAME%" ...
nssm install %SERVICE_NAME% "%PG_BIN%\pg_ctl.exe" "runservice -D \"%PG_DATA%\" -o \"-p %PG_PORT%\""
REM NOTE: pg_ctl's "runservice" mode requires the data directory to have been
REM initialized (it already has - .devdb\data is the existing dev data dir).
REM If "runservice" is unavailable in this Postgres build, use "start" mode
REM instead with NSSM's own restart-on-exit handling:
REM   nssm install %SERVICE_NAME% "%PG_BIN%\pg_ctl.exe" "start -D \"%PG_DATA%\" -l \"%PG_LOG%\" -o \"-p %PG_PORT%\" -w"
REM   nssm set %SERVICE_NAME% AppExit Default Exit

nssm set %SERVICE_NAME% DisplayName "CONNECT.PH Clinic Platform - PostgreSQL (portable)"
nssm set %SERVICE_NAME% Description "Portable PostgreSQL instance for the CONNECT.PH local clinic database. Data dir: %PG_DATA%. Do not point this at a different data directory."
nssm set %SERVICE_NAME% Start SERVICE_AUTO_START
nssm set %SERVICE_NAME% ObjectName LocalSystem
nssm set %SERVICE_NAME% AppStdout "%LOG_DIR%\postgres-service.log"
nssm set %SERVICE_NAME% AppStderr "%LOG_DIR%\postgres-service-error.log"
nssm set %SERVICE_NAME% AppRotateFiles 1
nssm set %SERVICE_NAME% AppRotateBytes 10485760
REM Auto-restart on unexpected exit, with a delay to avoid a crash-loop.
nssm set %SERVICE_NAME% AppExit Default Restart
nssm set %SERVICE_NAME% AppRestartDelay 5000

echo.
echo Done. Start it with:   nssm start %SERVICE_NAME%
echo Check status with:     nssm status %SERVICE_NAME%
echo Remove it with:        nssm remove %SERVICE_NAME% confirm
exit /b 0
