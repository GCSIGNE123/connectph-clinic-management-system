@echo off
REM ---------------------------------------------------------------------------
REM launch_clinic_browser.bat  -  Phase 2.6 Local Production Deployment
REM
REM Opens the clinic's default browser to the frontend URL, waiting briefly
REM for it to actually respond first (poll, not a fixed sleep) so staff
REM don't land on a "site can't be reached" page on a slow boot.
REM
REM NOT installed into this machine's real Startup folder or Task Scheduler
REM by this script - see the two installation options below, run manually
REM by clinic IT (neither requires Administrator).
REM
REM OPTION A - Startup folder shortcut (simplest):
REM   1. Press Win+R, type: shell:startup , Enter.
REM   2. Right-click this file -> "Create shortcut", drag the shortcut into
REM      the folder that opened.
REM   (Runs once per user, at that user's next login.)
REM
REM OPTION B - Scheduled Task "at log on" (more control, e.g. delay/retry):
REM   schtasks /create /tn "CONNECT.PH Clinic Browser" /tr "\"%~f0\"" ^
REM     /sc onlogon /rl limited
REM   Remove with:  schtasks /delete /tn "CONNECT.PH Clinic Browser" /f
REM ---------------------------------------------------------------------------
setlocal
call "%~dp0_common.bat"

set "CLINIC_URL=http://localhost:%FRONTEND_PORT%"

call "%~dp0_wait_for.bat" http "%CLINIC_URL%/" 60 "Frontend"
start "" "%CLINIC_URL%"
exit /b 0
