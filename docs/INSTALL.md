# Install / Local Development Setup

Step-by-step setup for running the full CONNECT.PH Clinic Platform locally. For hosted deployment (Vercel + VPS/Nginx, see Post-RC1 Phase 2.5) see [`DEPLOYMENT.md`](DEPLOYMENT.md) instead — this doc is local dev only. For physical clinic-hardware setup (workstations, TV display, printers, network) see [`INSTALLATION_GUIDE.md`](INSTALLATION_GUIDE.md) — this doc covers the software only.

---

## Prerequisites

- Node.js 20+ and npm
- Python 3.12+
- Docker Desktop (for Postgres + Redis, or the full compose stack)
- (Optional) a Supabase project, if you want to develop against hosted Postgres/Storage instead of local Docker Postgres

## 1. Clone and configure environment

```bash
cp frontend/.env.example frontend/.env.local
cp backend/.env.example backend/.env
```

Fill in `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, and (if used) Supabase keys. See [`DEPLOYMENT.md`](DEPLOYMENT.md) for the full variable reference and [`SECURITY.md`](SECURITY.md) for what each secret protects.

## 2. Start infrastructure (Postgres + Redis)

```bash
docker compose -f docker/docker-compose.yml up -d postgres redis
```

Or run the full stack, including backend/frontend containers built from `docker/Dockerfile.backend` / `docker/Dockerfile.frontend`:

```bash
docker compose -f docker/docker-compose.yml up --build
```

## 3. Backend (FastAPI)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -e ".[dev]"

alembic upgrade head            # apply all migrations (0001 -> 0016)
uvicorn app.main:app --reload --port 8000
```

Backend runs at `http://localhost:8000`; interactive API docs at `http://localhost:8000/docs`. Verify with:

```bash
curl http://localhost:8000/api/v1/health   # {"status":"ok"}
curl http://localhost:8000/api/v1/ready    # {"status":"ready","database":"reachable"}
```

## 4. Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:3000`.

## 5. Demo / pilot logins

A seeded demo clinic exists for local exploration (created through the real `POST /auth/register` endpoint, not raw SQL):

| Clinic | Login | Password |
|---|---|---|
| CONNECT.PH Demo Clinic | `owner@connectph.dev` | `OwnerPass123!` |
| Pilot Clinic | `pilotowner@example.com` | `PilotPass123!` |
| Platform Admin Portal (`/platform/login`) | `platformadmin@connectph.dev` | `PlatformAdmin123!` |

Note: the clinic login page's email field requires a real email address, not a bare username, even though the backend's `email_or_username` field would accept either — see [`BUGS.md`](BUGS.md) BUG-006.

## 6. Running tests

```bash
# Frontend
cd frontend && npm run test

# Backend — CRITICAL: only ever against a database whose name contains "test".
# backend/app/tests/conftest.py enforces this with a hard guard; never weaken it
# or point pytest at your dev database (connectph_clinic).
cd backend && DATABASE_URL=postgresql+asyncpg://clinic_user:clinic_password@localhost:5433/connectph_clinic_test pytest
```

See [`TESTING.md`](TESTING.md) for the full testing approach and CI details.

## 7. Building for production locally (sanity check)

```bash
cd frontend && npm run build     # must complete with no ESLint/type errors
cd backend  && alembic upgrade head   # against a disposable DB, never connectph_clinic
```

Both are re-verified as part of every release pass — see [`RELEASE_NOTES_v1.0.0.md`](RELEASE_NOTES_v1.0.0.md) for the v1.0.0 verification run.

## Helper scripts

See [`scripts/README.md`](../scripts/README.md) for one-shot dev bootstrap scripts (`setup-dev.ps1` / `setup-dev.sh`).

## Troubleshooting

See [`SUPPORT_GUIDE.md`](SUPPORT_GUIDE.md) for common local-dev issues (port conflicts, stale `.env`, migration drift) and [`BUGS.md`](BUGS.md) for known issues.
