@echo off
REM ---------------------------------------------------------------------------
REM start_clinic.bat  -  Phase 2.6 Local Production Deployment
REM
REM Manually starts the full stack in the correct order, each stage polling
REM for real readiness (no fixed sleeps): PostgreSQL -> Backend -> Frontend.
REM
REM This is the SAME boot chain the NSSM Windows Services use (see
REM install-backend-service.bat / install-postgres-service.bat /
REM install-frontend-service.bat) - useful for manual testing without
REM registering real services, and as the logic reference for
REM docs/WINDOWS_SERVICE_SETUP.md's DependOnService wiring.
REM
REM Safe to run repeatedly - already-running components are detected and
REM skipped.
REM ---------------------------------------------------------------------------
setlocal
call "%~dp0_common.bat"

echo ============================================================
echo  CONNECT.PH Clinic Platform - starting local production stack
echo ============================================================

REM --- Stage 1: PostgreSQL (portable, .devdb\) ---------------------------
echo.
echo [1/3] PostgreSQL
"%PG_BIN%\pg_ctl.exe" -D "%PG_DATA%" -l "%PG_LOG%" -o "-p %PG_PORT%" start
call "%~dp0_wait_for.bat" tcp localhost %PG_PORT% 30 "PostgreSQL (port %PG_PORT%)"
if errorlevel 1 (
    echo [FATAL] PostgreSQL did not come up. Check %PG_LOG%. Aborting.
    exit /b 1
)

REM --- Stage 2: Backend (FastAPI / uvicorn) -------------------------------
echo.
echo [2/3] Backend
start "connectph-backend" /D "%BACKEND_DIR%" /MIN cmd /c ^
    ""%PYTHON_EXE%" -m uvicorn app.main:app --host %BACKEND_HOST% --port %BACKEND_PORT% >> "%LOG_DIR%\backend.log" 2>&1"
call "%~dp0_wait_for.bat" http "http://localhost:%BACKEND_PORT%/api/v1/health" 45 "Backend (/api/v1/health)"
if errorlevel 1 (
    echo [FATAL] Backend did not become healthy. Check %LOG_DIR%\backend.log. Aborting.
    exit /b 1
)

REM --- Stage 3: Frontend (Next.js production server) ----------------------
echo.
echo [3/3] Frontend
start "connectph-frontend" /D "%FRONTEND_DIR%" /MIN cmd /c ^
    "npm run start -- --port %FRONTEND_PORT% >> "%LOG_DIR%\frontend.log" 2>&1"
call "%~dp0_wait_for.bat" http "http://localhost:%FRONTEND_PORT%/" 45 "Frontend (/)"
if errorlevel 1 (
    echo [FATAL] Frontend did not become healthy. Check %LOG_DIR%\frontend.log. Aborting.
    exit /b 1
)

echo.
echo ============================================================
echo  All components up. Backend: http://localhost:%BACKEND_PORT%
echo                     Frontend: http://localhost:%FRONTEND_PORT%
echo ============================================================
exit /b 0
