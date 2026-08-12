# `deploy/windows/` — Phase 2.6 Local Production Deployment scripts

Scripts for running the CONNECT.PH Clinic Platform as a real, auto-starting
Windows production install on a clinic's own machine (the "doctor-desktop"
target). See `docs/LOCAL_DEPLOYMENT.md` for the full walkthrough,
`docs/WINDOWS_SERVICE_SETUP.md` for the Windows Service details, and
`docs/FIRST_CLINIC_INSTALLATION.md` for the Canora Medical Clinic install
checklist.

This is a **different** target from `deploy/connectph-backend.service` /
`deploy/nginx-connectph.conf` (Phase 2.5's Linux/systemd VPS deployment for
a future cloud-hosted instance) — those are unrelated to this folder.

| Script | What it does | Safe to run now? |
|---|---|---|
| `_common.bat` | Shared paths/ports, included by every other script. Not run directly. | n/a |
| `_wait_for.bat` | Poll-with-timeout helper (tcp/http), used by every script below instead of a fixed sleep. Not run directly. | n/a |
| `start_clinic.bat` | Starts Postgres → Backend → Frontend in order, each stage polling for real readiness. | Yes — manual start/stop, no OS-level registration. |
| `stop_clinic.bat` | Stops all three, reverse order. | Yes. |
| `restart_clinic.bat` | `stop_clinic.bat` then `start_clinic.bat`. | Yes. |
| `check_health.bat` | Read-only. Prints PASS/FAIL for Postgres/Backend/DB-readiness/Frontend, and deployment-mode/cloud-sync status if `BACKEND_HEALTH_TOKEN` is set. | Yes — read-only. |
| `launch_clinic_browser.bat` | Opens the default browser to the frontend once it's responding. | Yes to run directly; installing it into Startup/Task Scheduler is a separate manual step (see the script's own header). |
| `install-postgres-service.bat` | Registers the portable Postgres as an NSSM Windows Service (auto-start, auto-restart). | **No — Administrator-only, registers a real service.** |
| `install-backend-service.bat` | Registers the backend as an NSSM Windows Service, `DependOnService` Postgres. | **No — Administrator-only.** |
| `install-frontend-service.bat` | Registers the production frontend (`next start`) as an NSSM Windows Service, `DependOnService` Backend. | **No — Administrator-only.** |
| `open-firewall-ports.bat` | `netsh advfirewall` rule opening inbound TCP 3000/8000 on the Private network profile. | **No — Administrator-only, modifies real firewall rules.** |
| `install_local_clinic.bat` | Orchestrates all four `install-*`/`open-firewall-ports` scripts above, in order, then starts everything. The one script clinic IT runs top-to-bottom on install day. | **No — Administrator-only. This is the real install.** |

Every script is idempotent (safe to re-run) and uses **poll-with-timeout**
(`_wait_for.bat`) rather than fixed sleeps to avoid startup-order race
conditions — see `docs/WINDOWS_SERVICE_SETUP.md` §"Startup order /
race-condition avoidance".
