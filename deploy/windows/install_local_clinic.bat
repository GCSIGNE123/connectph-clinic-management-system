@echo off
REM ---------------------------------------------------------------------------
REM install_local_clinic.bat  -  Phase 2.6 Local Production Deployment
REM
REM *** DOES NOT RUN AUTOMATICALLY. WRITTEN, NOT EXECUTED, BY DESIGN. ***
REM
REM Orchestrates the full real install, in order, as Administrator. This is
REM the ONE script clinic IT should run top-to-bottom on install day, after
REM completing the manual prerequisites below. It calls the individual
REM install-*-service.bat scripts in this folder - see each of those for
REM what it does in detail, and see docs/FIRST_CLINIC_INSTALLATION.md for
REM the full narrative walkthrough with screenshots-equivalent detail.
REM
REM MANUAL PREREQUISITES (do these BEFORE running this script):
REM   1. Copy this whole repo to the clinic machine (e.g. D:\Projects\CMS),
REM      including the existing .devdb\ folder (portable Postgres binaries +
REM      data dir) untouched.
REM   2. Install Python 3.11+ and Node.js 20+ on the clinic machine.
REM   3. cd backend && python -m venv .venv && .venv\Scripts\pip install -e .
REM   4. cd frontend && npm ci && npm run build
REM   5. Copy backend\.env.local-production.example -> backend\.env.production,
REM      fill in real values, then copy it to backend\.env (Settings loads a
REM      file literally named .env - see backend/app/core/config.py).
REM   6. Copy frontend\.env.local-production.example -> frontend\.env.production,
REM      fill in real values. (next build must be re-run after editing this -
REM      NEXT_PUBLIC_* vars are baked in at build time.)
REM   7. Download NSSM (https://nssm.cc/download) and put nssm.exe on PATH.
REM   8. Open an ELEVATED (Run as Administrator) Command Prompt.
REM
REM Then run:  install_local_clinic.bat
REM ---------------------------------------------------------------------------
setlocal
call "%~dp0_common.bat"

echo ============================================================
echo  CONNECT.PH Clinic Platform - full local install
echo ============================================================

net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] This script must be run as Administrator ^(Windows Services and
    echo         firewall rules cannot be created otherwise^). Right-click this
    echo         file ^(or the Command Prompt shortcut^) and choose "Run as
    echo         administrator", then run it again.
    exit /b 1
)

where nssm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] nssm.exe not found on PATH. Download from https://nssm.cc/download
    echo         and add its folder to PATH first.
    exit /b 1
)

echo.
echo [1/5] Installing PostgreSQL service...
call "%~dp0install-postgres-service.bat"
if errorlevel 1 exit /b 1

echo.
echo [2/5] Installing Backend service...
call "%~dp0install-backend-service.bat"
if errorlevel 1 exit /b 1

echo.
echo [3/5] Installing Frontend service...
call "%~dp0install-frontend-service.bat"
if errorlevel 1 exit /b 1

echo.
echo [4/5] Opening firewall ports 3000/8000 for the LAN...
call "%~dp0open-firewall-ports.bat"
if errorlevel 1 exit /b 1

echo.
echo [5/5] Starting all three services in order...
nssm start CONNECTPH-Postgres
call "%~dp0_wait_for.bat" tcp localhost %PG_PORT% 30 "PostgreSQL"
nssm start CONNECTPH-Backend
call "%~dp0_wait_for.bat" http "http://localhost:%BACKEND_PORT%/api/v1/health" 45 "Backend"
nssm start CONNECTPH-Frontend
call "%~dp0_wait_for.bat" http "http://localhost:%FRONTEND_PORT%/" 45 "Frontend"

echo.
echo ============================================================
echo  Install complete. Verify with:  check_health.bat
echo  Staff access this machine at:   http://<this-PC's-LAN-IP>:3000
echo  See docs/FIRST_CLINIC_INSTALLATION.md for the post-install checklist
echo  (auto-launch-on-login shortcut, reboot test, staff URL handout).
echo ============================================================
exit /b 0
