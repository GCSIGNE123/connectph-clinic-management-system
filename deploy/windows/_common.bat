@echo off
REM ---------------------------------------------------------------------------
REM CONNECT.PH Clinic Platform - Phase 2.6 Local Production Deployment
REM Shared paths/config, included by every script in this folder via CALL.
REM Edit these once if the clinic machine's install location differs from
REM the default D:\Projects\CMS layout.
REM ---------------------------------------------------------------------------

REM Repo root (this file lives in <root>\deploy\windows\_common.bat)
set "CMS_ROOT=%~dp0..\.."
for %%I in ("%CMS_ROOT%") do set "CMS_ROOT=%%~fI"

set "BACKEND_DIR=%CMS_ROOT%\backend"
set "FRONTEND_DIR=%CMS_ROOT%\frontend"
set "PG_BIN=%CMS_ROOT%\.devdb\pgsql\bin"
set "PG_DATA=%CMS_ROOT%\.devdb\data"
set "PG_LOG=%CMS_ROOT%\.devdb\logfile.txt"
set "PG_PORT=5433"

set "BACKEND_HOST=0.0.0.0"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=3000"

set "LOG_DIR=%CMS_ROOT%\deploy\windows\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

REM Python interpreter used to run the backend. On the real clinic machine
REM this should point at backend\.venv\Scripts\python.exe once a venv is
REM provisioned there (see docs/WINDOWS_SERVICE_SETUP.md); falls back to
REM whatever "python" resolves to on PATH.
if exist "%BACKEND_DIR%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%BACKEND_DIR%\.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)
