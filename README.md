# CONNECT.PH Clinic Platform

**CONNECT.PH Clinic Platform** is a commercial, multi-tenant Medical Clinic Management System (SaaS). It replaces a legacy Windows desktop clinic application with a modern, cloud-native web platform covering patient records, appointments, queueing, billing, pharmacy/prescriptions, laboratory workflows, and reporting for multiple independent clinics on a single shared platform.

> **Status: v1.0.0 — Commercial Release.** All eighteen build phases (Foundation through Pilot Deployment & UAT) are complete: Auth, Users, Patients, Clinic Configuration, Reception/Queue, Visits, Doctor Workspace, Consultation/SOAP, Orders, Prescriptions, Laboratory, Billing, Appointments, TV Queue Display, Owner Dashboard/Analytics, Legacy Migration Wizard, and a SaaS Admin Portal are all built and verified. See [`docs/FEATURES.md`](docs/FEATURES.md), [`docs/ROADMAP.md`](docs/ROADMAP.md), and [`docs/RELEASE_NOTES_v1.0.0.md`](docs/RELEASE_NOTES_v1.0.0.md).
>
> **Honest scope note:** this repository is developed and verified in a sandboxed local environment. "v1.0.0" here is a documentation/versioning milestone, not a real deployment — see [`docs/RELEASE_NOTES_v1.0.0.md`](docs/RELEASE_NOTES_v1.0.0.md) for exactly what that does and doesn't mean.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15 (App Router), React 19, TypeScript (strict), TailwindCSS, shadcn/ui, TanStack Query, React Hook Form + Zod, Lucide icons |
| Frontend hosting | Vercel (target) |
| Backend | FastAPI, Python 3.12, SQLAlchemy 2.0 (async), Alembic, JWT auth (passlib argon2) |
| Backend hosting | Railway (target) |
| Database | PostgreSQL (via Supabase, or self-hosted) |
| File storage | Supabase Storage |
| Cache / rate limiting | Redis |
| Realtime | WebSockets |
| CI/CD | GitHub Actions |
| Local dev | Docker Compose |

## Directory Structure

```
CMS/
├── frontend/                  # Next.js 15 app (feature-based, App Router)
│   └── src/
│       ├── app/                # App Router: (auth) and (dashboard) route groups
│       ├── components/         # ui/ (shadcn primitives) + layout/
│       ├── features/           # feature-based modules (auth, patients, billing, ...)
│       ├── lib/                 # API client, utils, config
│       ├── hooks/                # shared React hooks
│       └── types/                # shared TypeScript types
├── backend/                   # FastAPI app (Clean Architecture)
│   ├── app/
│   │   ├── core/                # config, security, settings
│   │   ├── db/                   # session, base, engine
│   │   ├── models/                # SQLAlchemy models
│   │   ├── schemas/                # Pydantic schemas
│   │   ├── repositories/            # data-access layer (tenant-scoped)
│   │   ├── services/                 # business logic layer
│   │   ├── api/v1/                    # routers
│   │   ├── middleware/                 # tenant context, error handling, etc.
│   │   └── tests/                       # Pytest suite
│   └── alembic/versions/        # DB migrations (0001 → 0016, linear chain)
├── docker/                    # Dockerfiles + docker-compose.yml
├── .github/workflows/         # CI/CD pipelines
├── scripts/                   # dev bootstrap scripts
└── docs/                      # project documentation (see below)
```

## Documentation

| Doc | Purpose |
|---|---|
| [`docs/INSTALL.md`](docs/INSTALL.md) | Local development setup, step by step |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Clean architecture layering, multi-tenancy strategy, DI pattern |
| [`docs/DATABASE.md`](docs/DATABASE.md) | Full schema, relationships, indexes, legacy migration strategy |
| [`docs/API.md`](docs/API.md) | REST API reference, organized by module |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Auth model, tenant isolation, password hashing, known limitations |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Vercel / Railway / Supabase setup and CI/CD deploy flow |
| [`docs/DEPLOYMENT_PACKAGE.md`](docs/DEPLOYMENT_PACKAGE.md) | What a real deployment package consists of for v1.0.0 |
| [`docs/TESTING.md`](docs/TESTING.md) | Frontend (Vitest/RTL) and backend (Pytest) testing approach |
| [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md) | End-user guide (clinic staff) |
| [`docs/ADMINISTRATOR_GUIDE.md`](docs/ADMINISTRATOR_GUIDE.md) | Clinic admin/owner guide |
| [`docs/SUPPORT_GUIDE.md`](docs/SUPPORT_GUIDE.md) | Support/troubleshooting playbook |
| [`docs/MIGRATION.md`](docs/MIGRATION.md) | Legacy data migration wizard guide |
| [`docs/BACKUP.md`](docs/BACKUP.md) | Backup/restore procedure |
| [`docs/FEATURES.md`](docs/FEATURES.md) | What is built vs. planned |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Phased delivery plan |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | Full version history, Phase 1 → v1.0.0 |
| [`docs/RELEASE_NOTES.md`](docs/RELEASE_NOTES.md) / [`docs/RELEASE_NOTES_v1.0.0.md`](docs/RELEASE_NOTES_v1.0.0.md) | Per-version and v1.0.0-specific release notes |
| [`docs/BUGS.md`](docs/BUGS.md) | Living bug tracker |
| [`docs/PILOT_READINESS.md`](docs/PILOT_READINESS.md) | Phase 17 pilot go-live checklist |

## Quickstart

See [`docs/INSTALL.md`](docs/INSTALL.md) for full local development setup (prerequisites, env files, Docker Compose, migrations, seed data, running both apps and their test suites).

```bash
cp frontend/.env.example frontend/.env.local
cp backend/.env.example backend/.env
docker compose -f docker/docker-compose.yml up -d postgres redis
cd backend && alembic upgrade head && uvicorn app.main:app --reload --port 8000
cd frontend && npm install && npm run dev
```

Backend: `http://localhost:8000` (docs at `/docs`). Frontend: `http://localhost:3000`.

## Version

Current version: **1.0.0** (see [`VERSION`](VERSION), `backend/pyproject.toml`, `frontend/package.json`). No real git tag exists in this environment (not a git repository) — see [`docs/CHANGELOG.md`](docs/CHANGELOG.md) for the honest account of what "v1.0.0" means here.

## Contributing / Process

This is a private commercial project. See [`docs/BUGS.md`](docs/BUGS.md) for the bug-tracking process and [`docs/ROADMAP.md`](docs/ROADMAP.md) for what's next.

## License

Proprietary — all rights reserved. Not licensed for external use, copying, or distribution.
