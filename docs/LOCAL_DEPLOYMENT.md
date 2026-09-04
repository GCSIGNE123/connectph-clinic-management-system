# Local Deployment (Post-RC1 Phase 2.6)

This document covers running CONNECT.PH Clinic Platform as a real, always-on
**local production install** on a clinic's own Windows machine (the
"doctor-desktop" target) — the actual first live install at Canora Medical
Clinic.

This is a **different target** from the other two deployment docs:

- **[`DEPLOYMENT.md`](DEPLOYMENT.md)** — the future cloud/VPS deployment
  (Nginx + HTTPS + a public domain, Vercel frontend). Read that if you are
  standing up the *Cloud Server* backup target from Phase 2.5, not the
  clinic's own machine.
- **[`INSTALLATION_GUIDE.md`](INSTALLATION_GUIDE.md)** — the clinic-hardware
  companion (network cabling, which PC is "Doctor Desktop" vs "Reception"
  vs the TV display, printer setup). Read that first for the physical/network
  layout; this document assumes that layout already exists and covers what
  runs *on* the Doctor Desktop machine specifically.
- **[`INSTALL.md`](INSTALL.md)** — the developer workflow (`npm run dev`,
  manual `uvicorn`, Docker Compose). This document replaces that workflow
  with an auto-starting production install for the one machine that is the
  real clinic server; developers elsewhere keep using `INSTALL.md` unchanged.

See also **[`WINDOWS_SERVICE_SETUP.md`](WINDOWS_SERVICE_SETUP.md)** (the
NSSM Windows Service details) and
**[`FIRST_CLINIC_INSTALLATION.md`](FIRST_CLINIC_INSTALLATION.md)** (the
step-by-step Canora Medical Clinic install checklist). All scripts referenced
below live in [`deploy/windows/`](../deploy/windows/README.md).

---

## 1. Production startup architecture

Boot chain, strictly ordered, each stage waiting for the previous to be
**actually ready** (polled with a timeout, never a fixed sleep):

```
PostgreSQL (portable, .devdb\)
      │  poll: TCP connect to port 5433
      ▼
Backend (FastAPI / uvicorn, port 8000)
      │  poll: GET /api/v1/health == 200
      ▼
Frontend (Next.js production, port 3000)
      │  poll: GET / == 200
      ▼
(optional) browser auto-launch to http://localhost:3000
```

Two implementations of this exact chain exist and must be kept in sync if
ever changed:

- **Manual / testing**: [`deploy/windows/start_clinic.bat`](../deploy/windows/start_clinic.bat)
  — runs the three stages as ordinary processes, using
  [`deploy/windows/_wait_for.bat`](../deploy/windows/_wait_for.bat) to poll.
- **Real production (boot, no login required)**: three NSSM Windows
  Services with `DependOnService` chaining — see
  `WINDOWS_SERVICE_SETUP.md`.

## 2. Production frontend (`next build` + `next start`)

The clinic-runtime frontend runs the real Next.js production server, not
`next dev`:

```bash
cd frontend
npm ci
npm run build      # next build — must be re-run after any source or
                    # NEXT_PUBLIC_* env change (baked in at build time)
npm run start -- --port 3000   # next start — the production server
```

**Verified for this phase** (2026-08-06, against this repo's real code):
`npm run build` completed cleanly across every route with
`NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1`, and `npm run start --
--port 3000` served the built app correctly — `GET /` returned `307` to
`/login` (expected, unauthenticated) and `GET /login` returned `200`. No
frontend code changes were needed; Phase 2.5 already proved `next build`
succeeds project-wide (see its `RELEASE_NOTES.md` entry, BUG-031) and this
phase re-confirmed the built output actually *serves* correctly under
`next start`, which Phase 2.5 did not test (it only shipped to Vercel,
which runs its own equivalent of `next start` internally).

`next start` is what `install-frontend-service.bat` registers as a Windows
Service — see `WINDOWS_SERVICE_SETUP.md`.

## 3–5. Windows Services, PostgreSQL auto-start, startup ordering

See **[`WINDOWS_SERVICE_SETUP.md`](WINDOWS_SERVICE_SETUP.md)** for the full
detail on all three NSSM services (Postgres, Backend, Frontend), the
service-account choice, auto-restart configuration, and how
`DependOnService` plus each stage's own readiness poll together avoid
startup-order races.

## 6. Windows Firewall

Two options, both documented, neither executed by this phase (this
environment's safety constraints prohibit making real firewall changes to a
shared machine — the clinic machine is a different, dedicated machine the
user/clinic IT controls):

**Script** (run once as Administrator on the real clinic machine):

```
deploy\windows\open-firewall-ports.bat
```

Adds one inbound rule (`CONNECT.PH Clinic Platform`) allowing TCP 3000 and
8000 on the **Private** network profile only — never Public/Domain, since
this machine should never be reachable from outside the clinic's own LAN.

**Manual GUI alternative** (for staff not comfortable running scripts):

1. Control Panel → Windows Defender Firewall → Advanced Settings.
2. Inbound Rules → New Rule… → Port → TCP → Specific local ports: `3000,8000`.
3. Allow the connection.
4. Check **Private** only (uncheck Domain and Public).
5. Name it `CONNECT.PH Clinic Platform` → Finish.

Verify either way with:

```
netsh advfirewall firewall show rule name="CONNECT.PH Clinic Platform"
```

## 7. Network configuration — what URL staff actually use

Being honest about what's achievable without adding new infrastructure:

- **Bare `http://localhost` (port 80, no port suffix) requires a reverse
  proxy that does not exist for this local Windows install.** Adding one
  (e.g. Nginx-for-Windows, IIS ARR, Caddy) is real new infrastructure this
  phase deliberately does **not** force-install for the first clinic
  rollout — it adds a fourth moving part to troubleshoot on install day,
  for a purely cosmetic URL improvement (a clinic-desktop app hitting
  port numbers in its own LAN URL is a completely normal, low-risk pattern;
  every browser bookmark/shortcut this phase ships hides the port anyway).
- **What actually works today, and is what this phase ships and
  documents**: `http://<Doctor-PC-LAN-IP>:3000` for the frontend (staff
  workstations, the receptionist PC, the waiting-room TV's `/tv` page) and
  `http://<Doctor-PC-LAN-IP>:8000` for direct API access (rarely needed by
  staff directly). On the Doctor Desktop machine itself, `http://localhost:3000`
  works identically.
- `http://<Doctor-PC-IP>/tv` (bare, no port) is **not** achievable today for
  the same reason above — use `http://<Doctor-PC-IP>:3000/tv`.
- **Making the Doctor-PC's LAN IP static** (so bookmarks/shortcuts survive a
  router reboot) is a one-time router-side or Windows-side step — see
  `FIRST_CLINIC_INSTALLATION.md`'s post-install checklist. Once static, the
  `:3000`/`:8000` URLs above never change.
- If a bare-`:80` URL becomes a real client requirement later, the correct
  fix is a minimal reverse proxy (e.g. Caddy's single-binary, single-file
  `Caddyfile` — no IIS/ARR complexity) added as its own explicitly-scoped
  follow-up phase, not bundled into this one.

## 8. Production environment files

Same tracked-`.example` / gitignored-real-file convention already
established by Phase 2.5, extended with one more profile:

| Profile | Backend example (tracked) | Frontend example (tracked) | Real file (gitignored) |
|---|---|---|---|
| Dev | `.env.development.example` | (uses `.env.local`, no separate example) | `backend/.env`, `frontend/.env.local` |
| Cloud/VPS production (Phase 2.5) | `.env.production.example` | `.env.production.example` | `backend/.env.production` (Vercel: Project env vars, not a file) |
| **Local clinic production (Phase 2.6, new)** | **`.env.local-production.example`** | **`.env.local-production.example`** | `backend/.env.production` (copied to `.env`), `frontend/.env.production` |

Key differences the local-clinic template deliberately makes vs. the
cloud/VPS one — see the files themselves for full inline comments:

- `DEBUG=false`, `DEPLOYMENT_MODE=local` by default (this **is** the local
  clinic instance, not the cloud backup target — only flip to `hybrid` once
  a real Cloud Server from Phase 2.5 exists and this clinic opts in).
- `DATABASE_URL` points at the existing portable `.devdb\` Postgres on port
  `5433` — unchanged from dev, not a new database.
- `COOKIE_SECURE=false` — this install serves plain `http://<LAN-IP>` (see
  §7 above), so `COOKIE_SECURE=true` would make the browser silently drop
  the refresh-token cookie and break login. This is the one deliberate,
  documented deviation from the cloud template.
- `CORS_ORIGINS` must list every hostname/IP staff actually type (not just
  `localhost`), since the frontend and backend are reached over LAN from
  other workstations.

The backend always loads a file literally named `.env`
(`backend/app/core/config.py`, `env_file=".env"`) — on the clinic machine,
copy `.env.local-production.example` → `.env.production` (for the record)
and then to `.env` (what actually loads). Next.js loads `.env.production`
automatically when `NODE_ENV=production` (which `next build`/`next start`
set implicitly) — no copy-to-`.env` step needed on the frontend side.

## 9. Automatic browser launch

[`deploy/windows/launch_clinic_browser.bat`](../deploy/windows/launch_clinic_browser.bat)
polls the frontend until it responds (never a fixed sleep) then opens the
default browser to it. Not installed into this machine's real Startup
folder by this phase — see the script's own header comment for the two
install options (Startup-folder shortcut, or a `schtasks /sc onlogon`
scheduled task), both doable without Administrator rights, both meant to be
run by clinic IT on the real machine.

## 10–11. Installation scripts & health check

See [`deploy/windows/README.md`](../deploy/windows/README.md) for the full
script inventory and which ones were safely executed and verified during
this phase vs. which are Administrator-only and were deliberately not run.
`check_health.bat` reuses the existing `GET /api/v1/system/status` endpoint
(built in Phase 2 Milestone 1/2, extended in Phase 2.5) — no backend changes
were needed for this phase.

## 12. Backup / restore

Unchanged from the existing dev workflow — the portable Postgres in
`.devdb\` (or its equivalent path on the clinic machine) is backed up with
the same `pg_dump`/`pg_basebackup` approach as any Postgres instance. See
`FIRST_CLINIC_INSTALLATION.md` §Backup & Restore for the clinic-specific
step-by-step (paths, a scheduled daily `pg_dump`, and the restore drill).
Cloud backup (uploading to a Phase 2.5 Cloud Server) is a separate,
optional, opt-in mechanism — see Phase 2/2.5 docs — not required for this
local install to be considered "backed up".

## 13. Updating an already-installed Server PC

Separate from everything above (which is the one-time initial install).
**This whole document (§1–12) describes the NSSM/manual-Windows-process
architecture** — a portable Postgres, a `backend\.venv`, `next start`,
three NSSM Windows Services. **A second, Docker-based architecture also
exists in this repo** (`docker/docker-compose.prod.yml` + the repo-root
`deploy.cmd`) and is what the actual **Canora Medical Clinic Server PC**
runs — do not assume every Server PC uses the architecture described above.

| This Server PC uses... | Update runbook | Update command |
|---|---|---|
| NSSM Windows Services (this document's architecture) | [`docs/UPDATE_PROCEDURE.md`](UPDATE_PROCEDURE.md) | `deploy\windows\update_server.bat` |
| Docker Desktop / `docker-compose.prod.yml` (the actual Canora Server PC) | [`docs/DOCKER_UPDATE_PROCEDURE.md`](DOCKER_UPDATE_PROCEDURE.md) | `deploy.cmd` (repo root) |

Each runbook never force-resets or cleans the working tree, never touches
`backend\.env`/the repo-root `.env`/`frontend\.env*`, only
rebuilds/restarts what actually changed, always backs up before running a
migration, and never restarts a service/container after a failed
migration. Read the runbook matching this specific machine's actual
architecture before running anything on a real clinic machine for the
first time — see `DOCKER_UPDATE_PROCEDURE.md`'s "Which updater do I
actually run?" table if unsure.
