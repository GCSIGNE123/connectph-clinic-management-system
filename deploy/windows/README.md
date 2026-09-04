# `deploy/windows/` — Phase 2.6 Local Production Deployment scripts

Scripts for running the CONNECT.PH Clinic Platform as a real, auto-starting
Windows production install on a clinic's own machine (the "doctor-desktop"
target), using the **NSSM/manual-Windows-process architecture** (portable
Postgres, a `backend\.venv`, `next start`, NSSM Windows Services). See
`docs/LOCAL_DEPLOYMENT.md` for the full walkthrough,
`docs/WINDOWS_SERVICE_SETUP.md` for the Windows Service details, and
`docs/FIRST_CLINIC_INSTALLATION.md` for the install checklist.

**This is NOT the actual Canora Medical Clinic Server PC's architecture.**
That machine runs Docker Compose instead (`docker/docker-compose.prod.yml`,
containers, no `backend\.venv`) — its update tool is the repo-root
`deploy.cmd`, documented in
[`docs/DOCKER_UPDATE_PROCEDURE.md`](../../docs/DOCKER_UPDATE_PROCEDURE.md),
not anything in this folder. See that document's "Which updater do I
actually run?" table if unsure which architecture a given machine uses.

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
| `check_health.bat` | Read-only, **dual-mode** (auto-detects NSSM vs. Docker). Prints PASS/FAIL for Postgres/Backend/DB-readiness/Frontend, and deployment-mode/cloud-sync status if `BACKEND_HEALTH_TOKEN` is set. | Yes — read-only. |
| `launch_clinic_browser.bat` | Opens the default browser to the frontend once it's responding. | Yes to run directly; installing it into Startup/Task Scheduler is a separate manual step (see the script's own header). |
| `install-postgres-service.bat` | Registers the portable Postgres as an NSSM Windows Service (auto-start, auto-restart). | **No — Administrator-only, registers a real service.** |
| `install-backend-service.bat` | Registers the backend as an NSSM Windows Service, `DependOnService` Postgres. | **No — Administrator-only.** |
| `install-frontend-service.bat` | Registers the production frontend (`next start`) as an NSSM Windows Service, `DependOnService` Backend. | **No — Administrator-only.** |
| `open-firewall-ports.bat` | `netsh advfirewall` rule opening inbound TCP 3000/8000 on the Private network profile. | **No — Administrator-only, modifies real firewall rules.** |
| `install_local_clinic.bat` | Orchestrates all four `install-*`/`open-firewall-ports` scripts above, in order, then starts everything. The one script clinic IT runs top-to-bottom on install day. | **No — Administrator-only. This is the real install.** |
| `update_server.bat` | **NSSM architecture only** — the entry point for updating an **already-installed** NSSM-architecture Server PC to the latest approved `origin/main` commit — pulls (fast-forward only), reinstalls/rebuilds only what changed, backs up + migrates safely, restarts only the affected service(s), health-checks, and reports SUCCESS/FAILED. See `docs/UPDATE_PROCEDURE.md` for the full runbook. The actual Canora Server PC uses `deploy.cmd` (repo root) instead — see `docs/DOCKER_UPDATE_PROCEDURE.md`. | Yes on a real NSSM install — refuses to run over a dirty working tree or diverged history, never touches `.env` files, never force-resets/cleans. |
| `run_backup.bat` | Scheduled/manual database + attachment backup (see `docs/BACKUP.md`). Also invoked automatically by `update_server.bat` before any migration. | Yes. |
| `run_restore_drill.bat` | Non-destructive "is this backup actually restorable" check (see `docs/BACKUP.md`). | Yes. |

Every script is idempotent (safe to re-run) and uses **poll-with-timeout**
(`_wait_for.bat`) rather than fixed sleeps to avoid startup-order race
conditions — see `docs/WINDOWS_SERVICE_SETUP.md` §"Startup order /
race-condition avoidance".
