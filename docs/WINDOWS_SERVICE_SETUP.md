# Windows Service Setup (Post-RC1 Phase 2.6)

How the three components (PostgreSQL, Backend, Frontend) are registered as
real Windows Services so the clinic machine boots straight into a running
system with zero developer-tool interaction and no logged-in user required.
Companion to [`LOCAL_DEPLOYMENT.md`](LOCAL_DEPLOYMENT.md) (the wider
picture) and [`FIRST_CLINIC_INSTALLATION.md`](FIRST_CLINIC_INSTALLATION.md)
(the install-day checklist). Scripts live in
[`deploy/windows/`](../deploy/windows/README.md).

**None of the service-registration or firewall scripts described here were
executed on the shared dev machine this phase was built on** — they modify
real, persistent OS state (Windows Services, firewall rules) and are
explicitly reserved for the real clinic machine, run by a human with
Administrator rights. See the "What you need to run yourself" checklist at
the end of this document.

## Why NSSM

Windows has no first-class equivalent of systemd's simple `ExecStart=`
unit file for an arbitrary console app — the built-in `sc.exe create`
mechanism expects a real Windows Service binary (calls
`StartServiceCtrlDispatcher`), which neither `pg_ctl.exe`, `uvicorn`, nor
`npm` implement. [NSSM](https://nssm.cc/) ("the Non-Sucking Service
Manager") is the standard, widely-used, free tool that wraps an arbitrary
executable as a real Windows Service — auto-start, auto-restart on
failure/crash, stdout/stderr redirected to log files, all configurable via
`nssm set <service> <property> <value>`. This is the direct Windows
equivalent of Phase 2.5's Linux `systemd` unit
(`deploy/connectph-backend.service`).

## The three services

| Service name | Wraps | Depends on | Install script |
|---|---|---|---|
| `CONNECTPH-Postgres` | `pg_ctl.exe` against the existing portable `.devdb\pgsql` / `.devdb\data` (untouched — **not** a new PostgreSQL Server install) | — | `deploy/windows/install-postgres-service.bat` |
| `CONNECTPH-Backend` | `uvicorn app.main:app --host 0.0.0.0 --port 8000` | `CONNECTPH-Postgres` | `deploy/windows/install-backend-service.bat` |
| `CONNECTPH-Frontend` | `npm run start -- --port 3000` (i.e. `next start` against the pre-built `.next\`) | `CONNECTPH-Backend` | `deploy/windows/install-frontend-service.bat` |

Each install script sets, via `nssm set`:

- `Start SERVICE_AUTO_START` — starts at boot, before any user logs in.
- `ObjectName LocalSystem` — runs without a logged-in user (see below).
- `AppExit Default Restart` + `AppRestartDelay 5000` — auto-restarts 5s
  after any unexpected exit, matching the systemd unit's
  `Restart=on-failure` / `RestartSec=5`.
- `AppStdout` / `AppStderr` — real log files under `deploy/windows/logs/`,
  with `AppRotateFiles`/`AppRotateBytes` so they don't grow unbounded.
- `DependOnService` (Backend → Postgres, Frontend → Backend) — Windows
  Service Control Manager will not start a dependent service until its
  dependency reports "running".

## Why uvicorn alone, not Gunicorn+Uvicorn-workers

Phase 2.5's Linux systemd unit runs Gunicorn with
`uvicorn.workers.UvicornWorker` (4 workers) — Gunicorn's process-management
model depends on `fork()`, which does not exist on Windows. Plain `uvicorn`
is the correct Windows-native equivalent; it also supports `--workers N`
directly (no Gunicorn needed) if a single clinic-desktop install with a
handful of concurrent staff ever needs more concurrency — commented out,
ready to enable, in `install-backend-service.bat`.

## Service account choice: LocalSystem

Two realistic choices for `ObjectName` (the account each service runs as):

- **`LocalSystem`** (chosen here) — always available, no separate password
  to manage/rotate, runs without any user ever logging in, has full local
  filesystem access to the app's own directories. The standard, simplest
  choice for a single-machine, no-domain, no-multi-tenant clinic install
  like this one.
- **A dedicated service account** (e.g. `.\svc-connectph`) — more
  principle-of-least-privilege (scoped ACLs on just the app folders/ports),
  but adds real operational burden for a solo clinic-IT install: a
  password to create/store/rotate, `Log on as a service` rights to grant,
  and no meaningful security win here since this machine has no other
  services or tenants to isolate from. Documented as the alternative for a
  future multi-clinic or higher-security deployment, not used for this
  first install.

## Startup order / race-condition avoidance

Two layers, deliberately redundant:

1. **`DependOnService`** controls *start order* — Backend's service entry
   will not be told to start until Postgres's service is in the "running"
   state, and likewise Frontend after Backend.
2. **Readiness polling, not fixed sleeps** — "running" (a Windows Service
   Control Manager concept) is not the same as "actually accepting
   connections" (Postgres can report "running" moments before it's ready
   to accept TCP connections; uvicorn's own DB connection pool handles a
   late-arriving Postgres via retry-on-first-use, but the *clean, provable*
   way to confirm real readiness is polling the actual signal):
   - Postgres: TCP connect to `localhost:5433`.
   - Backend: `GET http://localhost:8000/api/v1/health == 200`.
   - Frontend: `GET http://localhost:3000/ == 200`.

   [`deploy/windows/_wait_for.bat`](../deploy/windows/_wait_for.bat)
   implements this poll-with-timeout pattern and is used by both
   `start_clinic.bat` (manual/testing path) and `install_local_clinic.bat`
   (the real service-registration path, to confirm the freshly-started
   services actually came up before declaring the install complete).
   `install-backend-service.bat` / `install-frontend-service.bat` also set
   NSSM's `AppThrottle` as a secondary, belt-and-suspenders guard against a
   dependency reporting "running" fractionally before it's truly ready.

## Uninstalling

```
nssm stop CONNECTPH-Frontend
nssm stop CONNECTPH-Backend
nssm stop CONNECTPH-Postgres
nssm remove CONNECTPH-Frontend confirm
nssm remove CONNECTPH-Backend confirm
nssm remove CONNECTPH-Postgres confirm
```

## What you need to run yourself (Administrator, on the real clinic machine)

None of the following were executed by this phase's work — they are
provided as tested, ready-to-run scripts. Exact order:

```
REM 1. One-time prerequisites (see install_local_clinic.bat's header for
REM    the full list): Python 3.11+, Node.js 20+, backend .venv provisioned,
REM    frontend npm ci && npm run build, both .env.production files filled
REM    in from the .env.local-production.example templates, NSSM on PATH.

REM 2. Open Command Prompt as Administrator, cd to the repo, then:
deploy\windows\install_local_clinic.bat

REM This single script calls, in order:
REM   install-postgres-service.bat
REM   install-backend-service.bat
REM   install-frontend-service.bat
REM   open-firewall-ports.bat
REM then starts all three services and polls each for real readiness.

REM 3. Verify:
deploy\windows\check_health.bat

REM 4. Reboot the clinic machine and confirm the stack comes up
REM    automatically with no one logged in — this is the one step that
REM    genuinely requires a real reboot of the real target machine and
REM    cannot be simulated from this dev environment.
```
