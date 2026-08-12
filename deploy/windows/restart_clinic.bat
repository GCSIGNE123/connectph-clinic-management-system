@echo off
REM ---------------------------------------------------------------------------
REM restart_clinic.bat  -  Phase 2.6 Local Production Deployment
REM Stop, then start, the full stack. See stop_clinic.bat / start_clinic.bat.
REM ---------------------------------------------------------------------------
setlocal
call "%~dp0stop_clinic.bat"
echo.
timeout /t 2 /nobreak >nul
call "%~dp0start_clinic.bat"
exit /b %errorlevel%
