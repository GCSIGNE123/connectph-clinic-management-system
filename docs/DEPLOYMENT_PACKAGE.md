# Deployment Package — v1.0.0

What a real deployment package for CONNECT.PH Clinic Platform v1.0.0 consists of, and what has/hasn't actually been verified in this sandboxed development environment. See [`DEPLOYMENT.md`](DEPLOYMENT.md) for hosting setup (Vercel/Railway/Supabase) and [`RELEASE_NOTES_v1.0.0.md`](RELEASE_NOTES_v1.0.0.md) for the release's overall verification report.

---

## 1. Package components

| Component | What it is | Status in this environment |
|---|---|---|
| Built frontend | `frontend/.next` production build output (or a Docker image built from `docker/Dockerfile.frontend`) | **Verified**: `npm run build` in `frontend/` completes cleanly (33 routes, all pages generated) — see `RELEASE_NOTES_v1.0.0.md` §5 for real output. Not packaged into an artifact/zip; that's a CI-pipeline step, out of scope here. |
| Backend + migrations | The `backend/app` FastAPI application plus `backend/alembic/versions/` (0001 → 0016) | **Verified**: the full migration chain applies cleanly, in order, on a fresh disposable database (`connectph_clinic_test_v100`, created and dropped within this session) — see `RELEASE_NOTES_v1.0.0.md` §5. |
| Env var template | `backend/.env.example`, `frontend/.env.example` | Already exist from earlier phases; reviewed, still accurate against current code (no new env vars introduced this release, since no schema/feature changes were made). |
| Seed / demo data script | The demo clinic (`owner@connectph.dev`) and pilot clinic (`pilotowner@example.com`) were created through the real `POST /auth/register` endpoint, not a raw SQL seed script — there is no standalone `seed.py`/fixture script that recreates them from scratch in one command today. `backend/scripts/` has operational scripts (load test, platform-admin seeding) but not a full demo-data bootstrap script. | **Documented gap**, not fixed this release (no schema change and no new script needed per the release's own scope — flagging as a real next step below). |
| Docker images | `docker/Dockerfile.backend`, `docker/Dockerfile.frontend`, `docker/docker-compose.yml` | Already exist from an earlier phase. **Not rebuilt or pushed this release** — no `docker` CLI is available in this sandbox's shell, so building/pushing real images could not be verified here. This is the single largest gap between this environment and a real release; see §3. |

## 2. What was actually verified this release (with evidence)

- **Frontend build**: `cd frontend && npm run build` — compiled successfully, 33 routes generated, no ESLint/TypeScript errors (after fixing two lint errors that were genuinely failing the build — see `RELEASE_NOTES_v1.0.0.md` §4).
- **Migration chain**: `alembic upgrade head` against `postgresql+asyncpg://clinic_user:clinic_password@localhost:5433/connectph_clinic_test_v100` — a throwaway database, never `connectph_clinic` — ran all 16 migrations in order with no errors, then the database was dropped.
- **Runtime health**: `/health`, `/live`, `/ready` all returned correct `200` responses against the running dev backend.

## 3. What a real deployment package would additionally need (not done here, not fabricated as done)

- **Docker images actually built and pushed** to a real registry (e.g. GitHub Container Registry, Docker Hub, or Railway's own build pipeline) — the Dockerfiles exist and are believed correct (they mirror the same `docker-compose.yml` used for local dev) but were not exercised with a real `docker build` in this session.
- **A real CI pipeline run**: `.github/workflows/ci.yml` exists and documents the intended lint/test/build gate, but no GitHub Actions runner executed it as part of this release — the equivalent commands were run directly in this sandbox instead (see `RELEASE_NOTES_v1.0.0.md` §5).
- **A demo-data bootstrap script**: a single script (e.g. `backend/scripts/seed_demo.py`) that creates the demo/pilot clinics, users, and sample master data from empty in one command, rather than relying on data already present in this session's long-lived dev database. Recommended as a near-term follow-up so a genuinely fresh environment can stand up a working demo without replaying dozens of manual API calls.
- **A real cloud target**: no Vercel project, Railway service, or Supabase project was provisioned this release. `DEPLOYMENT.md` documents exactly what each of those needs when a real one is set up.
- **A real git tag / GitHub Release**: this directory is not a git repository. Once it is, `git tag v1.0.0` (or a GitHub Release referencing this changelog) is the remaining step to make "v1.0.0" a real, addressable artifact rather than just a version string in these files.

## 4. Recommended order of operations for a real first production release

1. Initialize git, commit, push to a real remote.
2. Provision Supabase (Postgres + Storage) and Redis (or Railway's Redis addon) for a production environment; fill in `backend/.env` from `backend/.env.example`.
3. Run `alembic upgrade head` against the real production database once, before any traffic is routed to it.
4. Build and push real Docker images (or let Railway build directly from `docker/Dockerfile.backend`); deploy the frontend to Vercel per `DEPLOYMENT.md`.
5. Point `CORS_ALLOWED_ORIGINS` / `NEXT_PUBLIC_API_BASE_URL` at the real production domains (both are dev-only values today).
6. Run the real CI pipeline (`ci.yml`) green on the release commit; tag it `v1.0.0`.
7. Re-run the Phase 17 UAT script (`docs/PILOT_READINESS.md`) against the real production deployment, not just local dev, before onboarding a real clinic.
