@echo off
REM ---------------------------------------------------------------------------
REM CONNECT.PH Clinic Platform - Phase 11 Scheduled Database Backup
REM
REM Intended to be run by Windows Task Scheduler once daily (see
REM docs/BACKUP.md for the exact schtasks setup command). Runs the
REM standalone backup+verify+retention script and exits non-zero on any
REM failure, so Task Scheduler's own "Last Run Result" reliably reflects
REM whether today's backup actually succeeded.
REM
REM Does NOT touch the running CMS (backend/frontend services are left
REM completely alone) - pg_dump reads the live database without locking
REM out application traffic.
REM ---------------------------------------------------------------------------

call "%~dp0_common.bat"

REM Destination directory: change this to a SECOND physical drive if one
REM is available on the clinic machine - a backup on the same disk as the
REM live Postgres data directory protects against nothing (disk failure
REM takes both down together). See docs/BACKUP.md for guidance; this
REM default only makes sense until a second drive/destination is chosen.
set "BACKUP_DEST=%CMS_ROOT%\backend\backups"

"%PYTHON_EXE%" "%BACKEND_DIR%\scripts\backup_and_prune.py" --backup-dir "%BACKUP_DEST%"
set "BACKUP_EXIT=%ERRORLEVEL%"

if not "%BACKUP_EXIT%"=="0" (
    echo [FAIL] Backup failed - exit code %BACKUP_EXIT%. See %BACKUP_DEST%\backup_log.txt for detail.
    exit /b %BACKUP_EXIT%
)

echo [OK] Backup completed and verified. See %BACKUP_DEST%\backup_log.txt for detail.
exit /b 0
