@echo off
REM ---------------------------------------------------------------------------
REM stop_clinic.bat  -  Phase 2.6 Local Production Deployment
REM
REM Stops frontend and backend (by the window titles start_clinic.bat gave
REM them) and PostgreSQL cleanly via pg_ctl. Reverse order of start_clinic.bat.
REM Safe to run even if some/all components are already stopped.
REM ---------------------------------------------------------------------------
setlocal
call "%~dp0_common.bat"

echo ============================================================
echo  CONNECT.PH Clinic Platform - stopping local production stack
echo ============================================================

echo.
echo [1/3] Stopping frontend...
taskkill /FI "WINDOWTITLE eq connectph-frontend*" /T /F >nul 2>&1
if errorlevel 1 (echo   (not running, or already stopped)) else (echo   Frontend stopped.)

echo.
echo [2/3] Stopping backend...
taskkill /FI "WINDOWTITLE eq connectph-backend*" /T /F >nul 2>&1
if errorlevel 1 (echo   (not running, or already stopped)) else (echo   Backend stopped.)

echo.
echo [3/3] Stopping PostgreSQL...
"%PG_BIN%\pg_ctl.exe" -D "%PG_DATA%" stop -m fast
if errorlevel 1 (echo   (not running, or already stopped)) else (echo   PostgreSQL stopped.)

echo.
echo Done.
exit /b 0
