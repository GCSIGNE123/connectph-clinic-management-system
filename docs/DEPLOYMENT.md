# Deployment

This document covers hosting setup for each part of the platform — **Vercel** (frontend), **Railway** (backend), **Supabase** (Postgres + Storage) — required environment variables, and the CI/CD deploy flow.

---

## 1. Frontend — Vercel

### Setup

1. Import the repository into Vercel, setting the **Root Directory** to `frontend/`.
2. Framework preset: **Next.js** (auto-detected for App Router).
3. Build command: `npm run build` (default). Output: `.next` (Vercel handles this natively — no need for `output: "standalone"` unless also building the Docker image for another environment).
4. Configure **three environments** in Vercel: Production (branch `main`), Preview (all PRs/branches), and optionally a persistent Staging environment/branch.

### Required environment variables (Vercel → Project → Settings → Environment Variables)

| Variable | Example | Notes |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `https://api-staging.connectph.example.com/api/v1` | Points at the Railway-hosted backend for that environment |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://xxxx.supabase.co` | If frontend talks to Supabase Storage directly |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `eyJ...` | Public/anon key only — never the service role key |
| `NEXTAUTH_URL` / session-related vars | `https://app.connectph.example.com` | If/when a Next.js auth session layer is added |

`NEXT_PUBLIC_*` variables are exposed to the browser bundle by Next.js convention — never put secrets behind that prefix.

### Preview deployments

Every PR gets an automatic Vercel Preview URL pointing at whatever `NEXT_PUBLIC_API_BASE_URL` is configured for the Preview environment (typically the staging backend). This lets reviewers click through a live build before merge.

---

## 2. Backend — Railway

### Setup

1. Create a Railway project; add a service pointing at the repository with **Root Directory** `backend/`.
2. Railway can build either via **Nixpacks** (auto-detected Python) or via the provided **`docker/Dockerfile.backend`** (recommended for parity with local Docker Compose — set the service's build to use that Dockerfile with build context at the repo root).
3. Expose the service on Railway's assigned `PORT` — the app must bind `0.0.0.0:$PORT` (the Dockerfile's `CMD`/entrypoint reads `$PORT`, defaulting to 8000 locally).
4. Add a **Postgres** reference: either use Railway's own Postgres plugin for early local/staging convenience, or (recommended, matching production) point `DATABASE_URL` at the **Supabase** Postgres connection string directly so staging mirrors production infrastructure.
5. Add a **Redis** plugin (Railway offers a one-click Redis addon) for rate limiting/caching.
6. Configure a **Release/Deploy command** to run `alembic upgrade head` before the app starts (Railway "Deploy" → "Release Command", or as a pre-start step in the container entrypoint), so migrations are never skipped on deploy.

### Required environment variables (Railway → Service → Variables)

| Variable | Example | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/postgres` | Supabase connection string, async driver |
| `REDIS_URL` | `redis://default:pass@host:6379` | |
| `JWT_SECRET_KEY` | `<generated, per-environment>` | Never reused across environments |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | |
| `SUPABASE_URL` | `https://xxxx.supabase.co` | |
| `SUPABASE_SERVICE_ROLE_KEY` | `eyJ...` | Server-side only, never exposed to frontend |
| `CORS_ALLOWED_ORIGINS` | `https://app.connectph.example.com,http://localhost:3000` | Comma-separated allow-list |
| `ENVIRONMENT` | `production` / `staging` / `development` | Drives config (e.g., docs enabled or not); also gates cookie `Secure`/`SameSite` flags (see [Production considerations](#6-production-considerations)) |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` | _(TODO — not yet integrated)_ | Needed once forgot-password/verify-email/resend-verification are wired to real email delivery — token issuance itself does not depend on these, see [`SECURITY.md`](SECURITY.md#1b-password-reset--email-verification-token-lifecycle) |
| `ACCOUNT_LOCKOUT_MAX_ATTEMPTS` | `5` | Failed logins before lockout (Phase 2) |
| `ACCOUNT_LOCKOUT_DURATION_MINUTES` | `15` | Lockout window (Phase 2) |
| `REFRESH_TOKEN_REMEMBER_ME_EXPIRE_DAYS` | `7` | Extended cookie/session lifetime when `remember_me` is set on login (Phase 2); the non-remember-me session lifetime is shorter and session-scoped |

See `backend/.env.example` for the authoritative, current list.

### Health checks

Railway should be configured to hit `GET /api/v1/health` as its health check endpoint so failed deploys/crashes are detected and rolled back automatically.

---

## 3. Database & Storage — Supabase

### Postgres setup

1. Create a Supabase project per environment (or at minimum, separate **staging** and **production** projects — do not share one Postgres instance across environments).
2. Copy the connection string from Supabase → Project Settings → Database → Connection string, using the **connection pooling** (pgbouncer, port `6543`) string for the application's runtime connections (better suited to serverless/high-connection-churn workloads) and the **direct connection** (port `5432`) string for running Alembic migrations (migrations, especially those using `CREATE INDEX CONCURRENTLY` or session-level settings, generally need a direct, non-pooled connection).
3. Enable the `pgcrypto` extension if `gen_random_uuid()` is not already available by default on the Supabase Postgres version in use.
4. (Planned, Phase 1+) Enable Row-Level Security (RLS) policies on tenant tables as a defense-in-depth layer alongside application-level `clinic_id` scoping — see [`ARCHITECTURE.md`](ARCHITECTURE.md#3-multi-tenancy-strategy).

### Storage setup

1. Create a Storage bucket (e.g., `clinic-files`) per environment.
2. Configure bucket policies so uploads/downloads are scoped by `clinic_id` path prefix (e.g., objects stored under `clinics/{clinic_id}/...`) and access is mediated by signed URLs issued by the backend, rather than public bucket access.
3. The frontend uses the Supabase **anon key** only for operations explicitly permitted by bucket policy (e.g., uploading to a pre-signed URL); the backend uses the **service role key** to generate signed URLs and perform privileged storage operations.

---

## 4. CI/CD Deploy Flow

```
push to main
    │
    ▼
.github/workflows/ci.yml     (lint, test, build — both apps)
    │  (must pass)
    ▼
.github/workflows/deploy.yml  (currently skeleton/placeholder)
    ├── frontend deploy → Vercel (via Vercel CLI/GitHub integration)
    └── backend deploy  → Railway (via Railway CLI/GitHub integration)
```

- **CI (`ci.yml`)** runs on every push and pull request: installs dependencies, lints, runs the test suite, and builds both apps. This is the merge gate.
- **Deploy (`deploy.yml`)** is currently a **skeleton** — it documents the intended flow and required secrets but does not perform a real deploy yet, since no deploy secrets/tokens have been provisioned. In practice today, Vercel's own GitHub integration auto-deploys the frontend on push (Preview for PRs, Production for `main`) independent of this workflow, and Railway can be configured similarly via its GitHub integration. The `deploy.yml` workflow exists so that, once the team wants deploy fully driven from GitHub Actions (e.g., to add pre-deploy migration steps, smoke tests, or Slack notifications), the scaffold is already in place — uncomment and fill in the steps, and add these repository secrets:

| Secret | Used for |
|---|---|
| `VERCEL_TOKEN` | Vercel CLI deploy auth |
| `VERCEL_ORG_ID` | Vercel project linking |
| `VERCEL_PROJECT_ID` | Vercel project linking |
| `RAILWAY_TOKEN` | Railway CLI deploy auth |

- **Rollback:** Vercel keeps every deployment addressable/instantly promotable, so rollback is "promote a previous deployment" in the dashboard or via CLI. Railway keeps deploy history per service with a similar redeploy-previous-build option. Database migrations are the part that needs care on rollback — prefer additive, backward-compatible migrations (add columns/tables rather than destructive renames/drops) so a code rollback doesn't require an immediate matching down-migration.

## 5. Environments Summary

| Environment | Frontend | Backend | Database |
|---|---|---|---|
| Local | `next dev` (localhost:3000) or Docker Compose | `uvicorn --reload` (localhost:8000) or Docker Compose | Local Postgres via Docker Compose, or a Supabase dev project |
| Staging | Vercel Preview / dedicated staging branch | Railway staging service | Supabase staging project |
| Production | Vercel Production (`main`) | Railway production service | Supabase production project |

## 6. CI/CD Workflows Reference

- [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) — runs on every push/PR to `main`/`develop`: frontend job (`npm ci`, `npm run lint`, `npm run test -- --coverage`, `npm run build`) and backend job (`ruff check .`, `black --check .`, `alembic upgrade head` against an ephemeral Postgres/Redis service, `pytest --cov=app`). Both jobs upload their coverage report as a build artifact. This is the merge gate — Phase 2's new auth/user-management tests run here automatically as part of the same `pytest`/`vitest` invocations, no workflow changes required per feature.
- [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) — skeleton, gated on push to `main` or manual dispatch; documents (commented-out) steps to deploy the frontend to Vercel and backend to Railway via their CLIs once `VERCEL_TOKEN`/`VERCEL_ORG_ID`/`VERCEL_PROJECT_ID`/`RAILWAY_TOKEN` secrets are provisioned. Until then, Vercel/Railway's own GitHub integrations handle deploys.

## 7. Production Considerations

- **Secrets management:** never commit real values for `JWT_SECRET_KEY`, `DATABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_KEY`, `SMTP_PASSWORD`, or Redis credentials; use Vercel/Railway's environment variable stores per environment (see [`SECURITY.md`](SECURITY.md#6-secrets-management--environment-variables)). Rotate `JWT_SECRET_KEY` independently per environment.
- **HTTPS termination:** Vercel and Railway both terminate TLS at their edge by default in every non-local environment; the application itself never needs to handle certificates. Ensure `CORS_ALLOWED_ORIGINS` only lists `https://` origins in staging/production (no `http://` except for local dev).
- **Cookie flags in production:** the Phase 2 refresh-token cookie must be issued with `Secure` (HTTPS-only), `HttpOnly`, and `SameSite=Strict` in staging/production — these are driven off `ENVIRONMENT != "development"` so local HTTP dev (`localhost`) still works without `Secure`. Double-check this before the first production deploy involving real user sessions, since a misconfigured `Secure` flag will silently fail to set the cookie over plain HTTP.
- **Database migrations:** always run `alembic upgrade head` as part of deploy (Railway release command, see [Backend — Railway](#2-backend-railway)) before the new app version starts serving traffic, so the Phase 2 columns/tables exist before the code that depends on them goes live.

## 8. Phase 16: Production Readiness Checklist

What was actually verified in this environment (not a generic checklist copy-pasted — each line reflects a real check performed this phase, see `docs/TESTING.md` for the full session log):

- [x] `alembic upgrade head` runs cleanly against the real dev database; `alembic current`/`alembic heads` both confirm a single linear head (`0016_hardening_indexes`).
- [x] `/health`, `/live`, `/ready` all verified live via curl against the running dev backend — `/ready` confirmed to return `503` when the DB is unreachable (via a monkeypatched test, since taking the real dev DB down would be unsafe to do casually — see `test_ready_endpoint_returns_503_when_db_unreachable`).
- [x] Request-ID header (`X-Request-ID`) confirmed present on every response, echoing a client-supplied id when one is sent.
- [x] Standardized error envelope (`{"detail", "request_id"}`) confirmed across `404`/`401`/`422`/`500` response shapes via live curl.
- [x] CORS reviewed — explicit origin allow-list, no wildcard + credentials combination. **Production TODO** (not yet done, since no production domain exists to configure): update `CORS_ORIGINS` to the real production frontend domain(s) before the first production deploy — the current value is dev-only (`localhost:3000`/`5173`).
- [x] Rate limiting reviewed and re-confirmed live (20 concurrent logins correctly triggered `429`s beyond the configured limit). **Production TODO**: point `REDIS_URL` at a real, reachable Redis instance before running more than one API worker process — the in-memory fallback is not safe across multiple processes.
- [x] File upload validation added for the two upload endpoints that previously had none (consultation/laboratory attachments) and the one endpoint that relays real file bytes (migration wizard CSV/Excel upload).
- [x] A real `pg_dump` backup was triggered and verified (non-empty, valid header) against the dev database. **Production TODO**: off-host storage, scheduling, retention policy — see `docs/BACKUP.md`.
- [x] A real load test (`backend/scripts/load_test.py`) was run against the live dev server with a dedicated, cleaned-up synthetic test tenant — see `docs/TESTING.md` for the actual p50/p95/max numbers and the (correct, expected) rate-limiter interaction observed.
- [x] Frontend `npx tsc --noEmit` confirmed clean; frontend dev server confirmed still serving the app correctly (login session persisted, Patients list rendered real data, console clean) after all Phase 16 changes.
- [ ] **Not done in this phase** (explicitly out of scope per the phase spec): CI-integrated dependency vulnerability scanning, a production Redis/CDN provisioning step, WAL-based point-in-time recovery, an automated backup-retention job. These remain real, tracked gaps — not silently omitted.
