# Deployment

> **Post-RC1 Phase 2.5 update (2026-08-06):** the actual first production deployment target for the **backend** is a **VPS behind Nginx/HTTPS** (systemd + Gunicorn/Uvicorn workers), not Railway — see the new §0 below, which is the authoritative, currently-in-use deployment path. The **frontend** stays on **Vercel** as originally planned (§1 below is still accurate for that half). Everything under "Legacy planning doc" further down describes an earlier Railway/Supabase-based plan that was superseded for the backend/database hosting decision before any real deployment happened; it's kept for historical context and because the Supabase Storage guidance may still apply if Supabase is used for file storage independent of where Postgres/the API run. Do not follow the Railway steps for a real deploy — follow §0.
>
> **Post-RC1 Phase 2.6 note:** this whole document covers the **cloud/VPS** target (a future, separately-hosted Cloud Server/backup instance). The clinic's own on-prem machine — the actual first live install at Canora Medical Clinic — is a different target with its own doc: see [`LOCAL_DEPLOYMENT.md`](LOCAL_DEPLOYMENT.md).

---

## 0. VPS backend deployment (Post-RC1 Phase 2.5 — authoritative)

This section covers **real production deployment**: frontend on Vercel (§1, unchanged), backend on a VPS behind Nginx/HTTPS, and a Cloud PostgreSQL backup target. For local development setup, see [`INSTALL.md`](INSTALL.md) — this section is production-only.

**Architecture reminder** (unchanged from Milestones 1-2): the **Local Clinic Server** (backend + Postgres, on-prem or its own VPS per clinic) is the sole primary/source-of-truth database. A **Cloud Server** (this same backend codebase, deployed separately, its own Postgres) exists only as a `POST /api/v1/backup/{entity_type}` upload target for one-way sync/monitoring — it never writes back to any Local Clinic Server. The frontend talks only to its own clinic's Local Clinic Server via `NEXT_PUBLIC_API_URL`, never to the Cloud Server directly.

### 0.1 Server requirements

| Component | Minimum | Notes |
|---|---|---|
| VPS (backend) | 2 vCPU / 4 GB RAM / 40 GB SSD | Ubuntu 22.04 LTS+ |
| PostgreSQL | 15+ | one instance per clinic (Local Clinic Server) + one for the Cloud Server, if deployed |
| Redis | 7+ | rate limiting/caching |
| Domain | e.g. `connectph-it.com` | see §0.6 DNS |

### 0.2 VPS setup

```bash
apt update && apt upgrade -y
apt install -y python3.12 python3.12-venv postgresql postgresql-contrib redis-server nginx certbot python3-certbot-nginx git
adduser --system --group connectph
mkdir -p /opt/connectph && chown connectph:connectph /opt/connectph
```

### 0.3 PostgreSQL installation & database setup

```bash
sudo -u postgres psql <<'SQL'
CREATE USER clinic_user WITH PASSWORD '<strong-password>';
CREATE DATABASE connectph_clinic OWNER clinic_user;
SQL
```

For a Cloud Server, repeat with a separate database (e.g. `connectph_cloud_backup`), on the same instance or (for real isolation) a separate managed Postgres. `CLOUD_DATABASE_URL` lives in the **Cloud Server's own** `.env`; the Local Clinic Server never connects to it directly — all communication is HTTP (`POST /api/v1/backup/*`), not a DB connection.

### 0.4 Backend deployment

```bash
su - connectph
git clone <repo-url> /opt/connectph
cd /opt/connectph/backend
python3.12 -m venv .venv
.venv/bin/pip install -e ".[prod]"

cp .env.production.example .env
# edit .env: DATABASE_URL, JWT_SECRET_KEY, REDIS_URL, CORS_ORIGINS,
# CLOUD_* (Local Clinic Server only), SMTP_*

.venv/bin/alembic upgrade head
```

Verify manually first:

```bash
.venv/bin/gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 127.0.0.1:8000
curl http://127.0.0.1:8000/api/v1/health   # {"status":"ok"}
```

Then install as a systemd service (template: [`../deploy/connectph-backend.service`](../deploy/connectph-backend.service)):

```bash
sudo cp deploy/connectph-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now connectph-backend
sudo systemctl status connectph-backend
```

A Cloud Server deployment is identical, just with `DEPLOYMENT_MODE=local` (it has no cloud above itself) and `CLOUD_SYNC_API_KEY` set to authenticate *incoming* backup requests — same codebase, different `.env`, separate VPS/subdomain.

### 0.5 Nginx reverse proxy + HTTPS (Let's Encrypt)

Template: [`../deploy/nginx-connectph.conf`](../deploy/nginx-connectph.conf).

```bash
sudo cp deploy/nginx-connectph.conf /etc/nginx/sites-available/connectph
sudo ln -s /etc/nginx/sites-available/connectph /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo certbot --nginx -d clinic-api.connectph-it.com

# Auto-renewal: certbot installs a systemd timer by default on modern
# Ubuntu — verify rather than adding a duplicate cron job:
systemctl list-timers | grep certbot
# fallback if absent: 0 3 * * * certbot renew --quiet && systemctl reload nginx
```

**Cookies:** this app is primarily JWT-bearer (`Authorization: Bearer <token>`); the one cookie it sets is the refresh-token cookie (`REFRESH_TOKEN_COOKIE_NAME`, see `backend/app/core/config.py`). `COOKIE_SECURE=true` / `COOKIE_SAMESITE=lax` (both already the `Settings` defaults) must stay true in production, which requires the HTTPS this section sets up — `Secure` cookies are simply not set by the browser over plain HTTP.

**`/api/v1/health`** (no auth, no DB call, `{"status":"ok"}`) is the right target for a load-balancer/uptime health check — cheap and fast. Use `/api/v1/ready` instead only if you specifically want DB-reachability verification (heavier, `503` on DB-down).

### 0.6 Required production environment variables

From `backend/app/core/config.py` (`Settings`); full annotated template in `backend/.env.production.example`.

| Variable | Required? | Notes |
|---|---|---|
| `DATABASE_URL` | Yes | production Postgres |
| `JWT_SECRET_KEY` | Yes | long random value, never the dev default |
| `COOKIE_SECURE` / `COOKIE_SAMESITE` / `COOKIE_DOMAIN` | Recommended | `true` / `lax` behind HTTPS |
| `REDIS_URL` | Yes | rate limiting |
| `CORS_ORIGINS` | Yes | real frontend origin(s) only, e.g. `https://clinic.connectph-it.com` — no wildcard, no localhost |
| `SMTP_*` | If email used | password reset, notifications |
| `DEPLOYMENT_MODE` | No (`local` default) | `hybrid` on the Local Clinic Server if a Cloud Server exists |
| `CLOUD_API_URL` | Only in `hybrid` mode | Cloud Server base URL |
| `CLOUD_DATABASE_URL` | Cloud Server only | its own Postgres |
| `CLOUD_SYNC_API_KEY` | Both sides in `hybrid` mode | shared secret, same value both sides |
| `SYNC_WORKER_INTERVAL_SECONDS` / `SYNC_RETRY_BASE_SECONDS` / `SYNC_RETRY_MAX_SECONDS` | No | tuning only |

### 0.7 Frontend deployment (Vercel) — env vars specific to this phase

Builds on §1 below (framework/preset/root-directory guidance there is unchanged). Set in **Project → Settings → Environment Variables** (Production scope):

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://clinic-api.connectph-it.com/api/v1` |
| `NEXT_PUBLIC_APP_NAME` | `CONNECT.PH Clinic Platform` |
| `NEXT_PUBLIC_APP_ENV` | `production` |
| `NEXT_PUBLIC_APP_VERSION` | matches `frontend/package.json`'s `version` |
| `NEXT_PUBLIC_AUTH_COOKIE_NAME` | `cph_session` |

Every `NEXT_PUBLIC_*` var is inlined into the client bundle at build time — no dev-only fallback ships in production as long as `NEXT_PUBLIC_API_URL` is actually set in Vercel (the `?? "http://localhost:4000/api/v1"` fallbacks in source, e.g. `frontend/src/lib/api-client.ts:3`, are dev conveniences only reached when the env var is genuinely absent). Custom domain: **Project → Settings → Domains**, add `clinic.connectph-it.com`, follow Vercel's shown CNAME instructions (independent of the backend's own DNS record, §0.8).

### 0.8 DNS requirements

Example domain: `connectph-it.com`.

| Record | Type | Points to | Purpose |
|---|---|---|---|
| `clinic-api.connectph-it.com` | A | VPS public IP | Backend API (Nginx/Gunicorn) |
| `clinic.connectph-it.com` | CNAME | Vercel's provided target | Frontend |
| `cloud.connectph-it.com` | A | Cloud Server VPS public IP | Cloud backup/monitoring, if deployed |

### 0.9 Cloud database (backup target)

No local schema changes in this phase. The Cloud Server's Postgres only ever receives data via `POST /api/v1/backup/{entity_type}` (Milestone 2, `backend/app/api/v1/backup.py`) — this phase adds no new write paths. Migration story: a **cloud-hosted instance of this exact same codebase**, pointed at `CLOUD_DATABASE_URL` via its own `.env` and run through `alembic upgrade head`, is how the `sync_jobs`/`synced_records` schema gets created on the cloud side — identical process to §0.4's migration step, just against the cloud database.

### 0.10 Restart / rollback / backup / restore

**Restart:**
```bash
sudo systemctl restart connectph-backend
sudo systemctl status connectph-backend
curl https://clinic-api.connectph-it.com/api/v1/health
```

**Rollback (backend):**
```bash
cd /opt/connectph
git log --oneline -5
git checkout <previous-good-commit-or-tag>
cd backend && .venv/bin/pip install -e ".[prod]"
.venv/bin/alembic upgrade head    # or: .venv/bin/alembic downgrade -1, if the bad deploy added a migration to revert
sudo systemctl restart connectph-backend
```
Frontend rollback: Vercel **Deployments → (previous) → Promote to Production** — no git action needed.

**Backup** (application-level, in addition to Milestone 2's automated per-record cloud sync):
```bash
pg_dump -U clinic_user -h localhost connectph_clinic | gzip > connectph_clinic_$(date +%F).sql.gz
```
Automate via cron/systemd-timer, store off-box.

**Restore:**
```bash
gunzip -c connectph_clinic_2026-08-01.sql.gz | psql -U clinic_user -h localhost connectph_clinic
```
Restore into a new, empty database first and verify before pointing `DATABASE_URL` at it — never restore directly over a live database without a fresh pre-restore dump of current state.

### 0.11 Modes recap (local vs. hybrid)

Per `backend/app/core/config.py`, `DEPLOYMENT_MODE: Literal["local", "hybrid"]` — there is no separate third "cloud mode". A clinic backend is either fully local (`local`, unchanged default) or hybrid (`hybrid` = "this Local Clinic Server also backs up to a configured Cloud Server"). What's informally called "cloud mode" for the standalone Cloud Server deployment is really the same app running with `DEPLOYMENT_MODE=local` from its own point of view (it has no cloud above itself) — it's distinguished only by `CLOUD_SYNC_API_KEY` being set so it accepts authenticated incoming backup uploads. See `docs/TESTING.md`'s Phase 2.5 section for live proof.

---

## Legacy planning doc (pre-Phase 2.5) — Vercel / Railway / Supabase

The sections below describe an earlier hosting plan (Railway for the backend, Supabase-managed Postgres) drafted before any real deployment occurred. **Superseded for backend/database hosting by §0 above.** Kept for the Vercel frontend guidance (still accurate) and in case Supabase Storage is adopted later for file uploads independent of where Postgres/the API run.

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
