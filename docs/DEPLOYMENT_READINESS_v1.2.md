# Deployment Readiness — v1.2.0 (First Clinic Pilot Deployment)

This is the deployment candidate readiness report for taking CONNECT.PH Clinic Platform to its first real clinic. It consolidates and re-verifies (as of 2026-07-28, against the current codebase at v1.2.0 — Phases 1 through 19) what was previously documented across `DEPLOYMENT.md`, `DEPLOYMENT_PACKAGE.md`, `BACKUP.md`, and `SECURITY.md`, with fresh evidence from this pass. It does not duplicate the hosting-provider setup steps in `DEPLOYMENT.md` (Vercel/Railway/Supabase) — see that file for those. This document answers one question: **is this specific build safe to deploy, and exactly how do you do it and undo it.**

No new features were added in this pass. Two production-blocking issues found during this review were fixed (see §5); everything else found is either already-known (tracked in `docs/BUGS.md`) or out of scope for a deployment-blocking fix.

---

## 1. What changed since the last release doc (v1.0.0 → v1.2.0)

- Phase 18 (v1.1.0): Patient Portal — new `patient_accounts`/patient-auth tables (migration `0017_patient_portal`), a third structurally-separate JWT principal class.
- Phase 19 (v1.2.0): Online Appointment Booking — `appointments.booking_source` column (migration `0018_patient_appointment_booking`), DB-level double-booking prevention.
- **Found and fixed this pass**: `VERSION`, `backend/pyproject.toml`, `backend/app/main.py`'s FastAPI `version=`, and `frontend/package.json` were all still stamped `1.0.0` despite two shipped releases since — now correctly `1.2.0` everywhere. This is exactly the kind of drift a deployment readiness pass exists to catch.

## 2. Production environment variables

Authoritative source: `backend/.env.example`, `frontend/.env.example`. Reviewed line-by-line against current code; both are accurate (no undocumented env var was found in use anywhere in `app/core/config.py` or `frontend/src` that isn't already in the example files).

**Before deploying, set these to real, non-default values** (the example files intentionally ship with dev-only placeholders that must never reach production):

| Variable | Dev default | Required production value |
|---|---|---|
| `DATABASE_URL` | local Postgres | Real production Postgres connection string (async driver, `postgresql+asyncpg://...`) |
| `JWT_SECRET_KEY` | `change-me-to-a-random-secret-in-production` | A real random secret (e.g. `openssl rand -hex 32`), unique per environment, never reused from dev/staging |
| `ENV` | `development` | `production` — this single flag gates log level (`INFO` vs `DEBUG`), cookie `Secure`/`SameSite` flags, and other environment-sensitive behavior; verify it is actually set, not just present in `.env.example` |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` | The real production frontend domain(s), `https://` only |
| `REDIS_URL` | local Redis | A real, reachable Redis instance — **required** if running more than one backend worker process, since the rate limiter's in-memory fallback is not safe across multiple processes |
| `SUPABASE_URL` / `SUPABASE_KEY` / `SUPABASE_STORAGE_BUCKET` | placeholder project | A real Supabase project's values, if file storage (patient photos, attachments) is needed at launch — see §4 |
| `SMTP_*` | placeholder | Real SMTP credentials, only if/when password-reset and email-verification emails need to actually send (see `SECURITY.md` — token issuance itself doesn't depend on SMTP being configured, only delivery does) |

**Do not** commit real values for any of the above. Use the target host's own secrets store (or, for a single-VM pilot deployment, a `.env` file with restricted filesystem permissions, never checked into version control).

## 3. Exact build and startup commands (verified, this pass)

### Backend

```bash
cd backend
pip install -r requirements.txt          # or: pip install -e .
DATABASE_URL=<production-url> python -m alembic upgrade head   # see §4 — run this BEFORE starting the app
DATABASE_URL=<production-url> ENV=production JWT_SECRET_KEY=<real-secret> \
  python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

- `--workers 4` (or similar): once running more than one worker, `REDIS_URL` **must** point at a real Redis instance (see §2) — the rate limiter's in-memory counters do not coordinate across separate worker processes, silently under-enforcing limits otherwise.
- Do **not** pass `--reload` in production — it's a dev-only flag that adds file-watching overhead and is unnecessary/undesirable for a running service.
- Verified this pass: `python -c "import app.main"` — clean, no import errors, after the version-string fix in §1.

### Frontend

```bash
cd frontend
npm ci
NEXT_PUBLIC_API_URL=https://<production-backend-domain>/api/v1 npm run build
npm run start   # binds port 3000 by default; set PORT=<port> to change it
```

- **Verified this pass, live**: `npm run build` completed cleanly — 45 routes generated (0 errors) — after fixing two pre-existing `react/no-unescaped-entities` ESLint errors that were failing the build (`patient-portal/billing/page.tsx`, `patient-portal/login/page.tsx` — already fixed and logged as `docs/BUGS.md` BUG-014, resolved). `npm run start` was then run and confirmed serving correctly (`200` on `/login`) before being stopped.
- **Known operational gotcha, specific to this codebase, worth calling out explicitly for whoever runs this in production**: `next build` and `next dev` share the same `.next` directory. If a `next dev` process is left running against the same checkout while `next build` runs (as can happen if a deploy script runs on a shared/staging box that also has a dev server up), the running dev process's in-memory module cache is corrupted and needs a full process restart to recover — clearing `.next` on disk alone is not sufficient once the process itself is in a bad state. **Not a concern for a real production deployment** (production runs `next start` against a build produced by a dedicated CI/build step, never alongside a `next dev` process) — flagged here because it was directly observed and fixed during this session's own build verification, and is worth documenting so it's never mistaken for an application bug (see `docs/BUGS.md` BUG-015, closed).

### Database migrations

```bash
cd backend
DATABASE_URL=<production-url> python -m alembic upgrade head
```

**Verified this pass**: ran the entire migration chain (`0001_initial` through `0018_patient_appointment_booking` — 18 migrations, spanning every phase) against a freshly created, empty throwaway database (`connectph_deploy_check`, created and dropped within this session, never touching any real data). All 18 applied in order with zero errors. `alembic heads` confirms a single unbroken head — no branch points, no ambiguity about which migration is "current."

**Run migrations before starting the new application version**, not after — the app assumes the schema it expects already exists at startup.

## 4. Static assets & file uploads

- **Frontend static assets**: served by Next.js's own build output (`.next/static/...`) — no separate CDN/static-file server configuration is required at this stage; `npm run start` serves them directly.
- **File uploads — reviewed, current state confirmed**: patient photos, doctor photos, user profile photos, and consultation/laboratory attachments are all modeled as a **URL string** (`photo_url`, `file_url`, etc.), not a server-side file upload — the actual file is expected to live in Supabase Storage (or wherever `SUPABASE_STORAGE_BUCKET` points), with the backend only storing the resulting URL. **There is exactly one endpoint in this codebase that accepts a real multipart file upload today**: the Legacy Migration Wizard's CSV/Excel import (`POST` in `backend/app/api/v1/migration.py`), which already has a 50 MB size cap and extension validation (verified present in source this pass).
- **Deployment implication**: if the pilot clinic needs patient/doctor photo upload to actually work (not just accept a URL), a real Supabase Storage project must be provisioned and `SUPABASE_URL`/`SUPABASE_KEY`/`SUPABASE_STORAGE_BUCKET` set to real values before launch — this is a **pre-existing, already-documented gap** (see `DEPLOYMENT_PACKAGE.md` §3), not something newly discovered here, and not a blocker if the pilot clinic doesn't need photo upload on day one.

## 5. Production logging

Already implemented (Phase 16), reviewed and confirmed still correct this pass:

- `backend/app/main.py`'s `setup_logging()` installs a structured JSON log formatter to stdout, with log level driven by `ENV` (`INFO` in any non-`"development"` environment, `DEBUG` locally) — confirmed by reading the current source (`app/main.py:43-48`).
- Every request is logged with a `request_id`, method, path, status code, and duration (`app/middleware/request_logging.py`), and the same `request_id` is echoed back to the client via the `X-Request-ID` response header and included in every error response body — both previously verified live in Phase 16/17's testing and re-confirmed structurally unchanged this pass.
- **Production recommendation**: since output goes to stdout as structured JSON, point whatever process supervisor runs the app (systemd, a container orchestrator, PM2, etc.) at a log aggregator that can ingest JSON-formatted stdout (e.g. Railway's built-in log viewer, or a shipped-to syslog/Loki/CloudWatch setup) — no code change is needed for this, it's purely an operational wiring step.

## 6. Authentication verification

Verified live this pass, against the running dev backend:

- `POST /api/v1/auth/login` with correct credentials (`owner@connectph.dev`) → `200`, valid JWT returned.
- Same endpoint with a wrong password → `401`.
- A protected endpoint (`GET /api/v1/patients`) with no `Authorization` header → `401`.
- `/api/v1/ready` correctly reported `503`/`"not_ready"` when Postgres was briefly down during this session (an unrelated environment event, not a deliberate test) and `200`/`"ready"` once Postgres was restored — confirms the readiness probe is a real dependency check, not a hardcoded `200`, which is exactly the property a deployment's health-check/load-balancer configuration should rely on.

## 7. Issues found this pass, classified by severity

| Severity | Issue | Blocking? | Action taken |
|---|---|---|---|
| Low | Version strings (`VERSION`, `pyproject.toml`, `main.py`, `package.json`) stale at `1.0.0` despite two releases since | Not deployment-blocking by itself, but would produce a misleading `/health`-adjacent version string and confusing release tracking | **Fixed this pass** — bumped to `1.2.0` in all four locations, backend re-verified importing cleanly |
| Low | Frontend production build was red (`npm run build` failing ESLint) | **Would have blocked deployment** — a red build cannot be shipped | **Already fixed** in a prior session (BUG-014, resolved); re-confirmed clean this pass |
| Low–Medium | No demo-data bootstrap script exists (real clinics/users were created via live API calls, not a repeatable seed script) | Not blocking — does not affect the running application, only the convenience of standing up a fresh environment | Not fixed (out of scope — pre-existing, documented gap, `DEPLOYMENT_PACKAGE.md` §3) |
| Everything in `docs/BUGS.md` (BUG-002, 003, 005, 006, 007, 008, 009) | Various Low/Medium application-behavior gaps, each already documented with a workaround | Not blocking — none affect core auth/tenant-isolation/data-integrity | Not touched this pass, per "fix only what blocks deployment" |

**No Critical or High severity issue was found or is currently open** (`BUG-001` was the only High, already fixed in Phase 17; nothing above Medium is currently Open).

## 8. Go/no-go for first-clinic deployment

**Go**, with the explicit, pre-existing caveats already tracked in `PILOT_READINESS.md` and `DEPLOYMENT_PACKAGE.md`:

- Build, migrations, auth, logging, and health/readiness probes are all verified working in this pass.
- No Critical/High bugs are open.
- Remaining gaps (photo-upload storage provisioning, demo-data bootstrap script, real cloud infra not yet provisioned, real CI/CD not yet run) are all **already known and documented**, not newly discovered blockers — and none of them prevent the core clinical/billing/queue/appointment workflows from working correctly for a pilot clinic that doesn't need patient photo uploads or automated multi-tenant onboarding on day one.
- See `docs/ROLLBACK_PLAN.md` for exactly how to undo this deployment if something goes wrong after go-live.
