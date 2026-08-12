@echo off
REM ---------------------------------------------------------------------------
REM open-firewall-ports.bat  -  Phase 2.6 Local Production Deployment
REM
REM *** DOES NOT RUN AUTOMATICALLY WHEN THIS FOLDER IS OPENED. WRITTEN, NOT
REM     EXECUTED, BY DESIGN - modifies real Windows Firewall rules. ***
REM
REM Opens inbound TCP 3000 (frontend) and 8000 (backend) so staff
REM workstations and the waiting-room TV on the clinic LAN can reach this
REM machine. Scoped to "private" network profiles only (the clinic's own
REM LAN, not any public/guest Wi-Fi this machine might ever join) - do not
REM widen to "any" unless you specifically intend that.
REM
REM Run as Administrator. Idempotent - safe to run more than once (removes
REM any pre-existing rule with the same name first).
REM
REM MANUAL GUI ALTERNATIVE for staff uncomfortable running scripts (see
REM docs/LOCAL_DEPLOYMENT.md "Windows Firewall" for the click-by-click
REM version):
REM   Control Panel -> Windows Defender Firewall -> Advanced Settings ->
REM   Inbound Rules -> New Rule... -> Port -> TCP -> Specific local ports:
REM   3000,8000 -> Allow the connection -> check "Private" only (uncheck
REM   Domain and Public) -> Name: "CONNECT.PH Clinic Platform".
REM ---------------------------------------------------------------------------
setlocal
call "%~dp0_common.bat"

net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Must be run as Administrator.
    exit /b 1
)

set "RULE_NAME=CONNECT.PH Clinic Platform"

echo Removing any pre-existing rule named "%RULE_NAME%" (idempotency)...
netsh advfirewall firewall delete rule name="%RULE_NAME%" >nul 2>&1

echo Adding inbound rule: TCP %BACKEND_PORT%,%FRONTEND_PORT%, Private profile only...
netsh advfirewall firewall add rule name="%RULE_NAME%" dir=in action=allow protocol=TCP localport=%BACKEND_PORT%,%FRONTEND_PORT% profile=private

if errorlevel 1 (
    echo [ERROR] netsh failed to add the rule. Are you running as Administrator?
    exit /b 1
)

echo.
echo Done. Verify with:  netsh advfirewall firewall show rule name="%RULE_NAME%"
echo Remove with:        netsh advfirewall firewall delete rule name="%RULE_NAME%"
exit /b 0
