@echo off
REM ---------------------------------------------------------------------------
REM CONNECT.PH Clinic Platform - Phase 11 Safe Restore-Drill Verification
REM
REM Verifies a backup dump file is actually restorable WITHOUT touching the
REM real clinic database - restores into a throwaway temporary database,
REM checks it, then drops it. Safe to run any time, including while the
REM CMS is live and serving traffic.
REM
REM Usage:
REM   deploy\windows\run_restore_drill.bat "backend\backups\scheduled-backup-20260101T020000.sql"
REM ---------------------------------------------------------------------------

call "%~dp0_common.bat"

if "%~1"=="" (
    echo Usage: run_restore_drill.bat "path\to\backup-file.sql"
    exit /b 1
)

"%PYTHON_EXE%" "%BACKEND_DIR%\scripts\verify_restore.py" "%~1"
exit /b %ERRORLEVEL%
