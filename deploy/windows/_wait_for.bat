@echo off
REM ---------------------------------------------------------------------------
REM _wait_for.bat  -  poll-with-timeout helper (NOT a fixed sleep).
REM
REM Usage:
REM   call _wait_for.bat tcp <host> <port> <timeout_seconds> <label>
REM   call _wait_for.bat http <url> <timeout_seconds> <label>
REM
REM Polls every 1 second until the target responds or the timeout elapses.
REM Sets ERRORLEVEL 0 on success, 1 on timeout.
REM ---------------------------------------------------------------------------
setlocal EnableDelayedExpansion

set "MODE=%~1"

if /I "%MODE%"=="tcp" (
    set "HOST=%~2"
    set "PORT=%~3"
    set "TIMEOUT=%~4"
    set "LABEL=%~5"
    echo   Waiting for !LABEL! ^(tcp !HOST!:!PORT!, timeout !TIMEOUT!s^) ...
    powershell -NoProfile -Command ^
        "$deadline = (Get-Date).AddSeconds(%TIMEOUT%); " ^
        "while ((Get-Date) -lt $deadline) { " ^
        "  try { $c = New-Object System.Net.Sockets.TcpClient; $iar = $c.BeginConnect('%HOST%', %PORT%, $null, $null); " ^
        "        if ($iar.AsyncWaitHandle.WaitOne(1000) -and $c.Connected) { $c.Close(); exit 0 }; $c.Close() " ^
        "  } catch {} ; Start-Sleep -Milliseconds 500 " ^
        "}; exit 1"
    if errorlevel 1 (
        echo   [TIMEOUT] !LABEL! did not become reachable within !TIMEOUT!s.
        exit /b 1
    ) else (
        echo   [OK] !LABEL! is reachable.
        exit /b 0
    )
)

if /I "%MODE%"=="http" (
    set "URL=%~2"
    set "TIMEOUT=%~3"
    set "LABEL=%~4"
    echo   Waiting for !LABEL! ^(http !URL!, timeout !TIMEOUT!s^) ...
    powershell -NoProfile -Command ^
        "$deadline = (Get-Date).AddSeconds(%TIMEOUT%); " ^
        "while ((Get-Date) -lt $deadline) { " ^
        "  try { $r = Invoke-WebRequest -Uri '%URL%' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400) { exit 0 } } catch {} ; " ^
        "  Start-Sleep -Milliseconds 500 " ^
        "}; exit 1"
    if errorlevel 1 (
        echo   [TIMEOUT] !LABEL! did not return a healthy response within !TIMEOUT!s.
        exit /b 1
    ) else (
        echo   [OK] !LABEL! responded.
        exit /b 0
    )
)

echo   [ERROR] _wait_for.bat: unknown mode "%MODE%" ^(expected tcp or http^)
exit /b 1
