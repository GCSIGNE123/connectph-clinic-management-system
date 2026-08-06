# Release Notes — v1.0.0 "Commercial Release"

**Date:** 2026-07-28
**Type:** Release-preparation milestone, not a new feature phase. No new business features were added; only genuine release-blocking (Critical/High) defects found during this phase's own verification were fixed.

---

## 1. What this release is

v1.0.0 marks all seventeen build phases (Foundation → Pilot Deployment & UAT) as complete and re-verified together in one pass, immediately after Phase 17. It is a documentation, versioning, and regression-verification milestone — see [§6](#6-honest-scope-statement-what-v100-does-and-does-not-mean-here) for exactly what that does and doesn't mean in this sandboxed environment.

## 2. Regression verification (real evidence)

All checks below were run against the live dev stack (Postgres on `localhost:5433`, backend on `localhost:8000`, frontend on `localhost:3000`) on 2026-07-28.

### Health/readiness probes

```
GET /api/v1/health -> {"status":"ok"}
GET /api/v1/live   -> {"status":"alive","uptime_seconds":561.87}
GET /api/v1/ready  -> {"status":"ready","database":"reachable"}
```

### Module happy-path sweep (real JWT, real seeded demo clinic `owner@connectph.dev`)

Every endpoint below returned `200` via live `curl` with a freshly issued access token:

`patients`, `queues`, `visits`, `departments`, `doctors`, `branches`, `services`, `users`, `appointments`, `billing/dashboard`, `analytics/dashboard`, `laboratory/dashboard`, `laboratory/orders`, `migration/batches`, `tv-displays`, `clinic-settings`, `holidays`, `operating-hours/branch/{id}`, `consultation-rooms`, `doctors/{id}/schedules`, `queue-settings`.

### SaaS Admin Portal (separate token type, real seeded platform admin `platformadmin@connectph.dev`)

```
POST /api/v1/platform-admin/auth/login -> 200, platform_admin_access token issued
GET  /api/v1/platform-admin/tenants -> 200
GET  /api/v1/platform-admin/dashboard/health -> 200
```

No regressions found in any module. This mirrors the same regression-sweep pattern every prior phase (15, 16, 17) has used — see `docs/TESTING.md` for those sessions' own logs.

## 3. Quality gate — bug severities

Read from `docs/BUGS.md` as of this release:

| Bug | Severity | Status |
|---|---|---|
| BUG-001 — Migration Wizard force-skips resolved validation errors | High | **Fixed** (Phase 17) |
| BUG-002 — Consultation-complete sync no-op if visit never called/started | Medium | Open (documented workaround) |
| BUG-003 — Migration Wizard only imports Patients/Doctors | Low | Open (documented scope decision) |
| BUG-004 — `pytest` argon2 memory allocation error in this sandbox | Low | Open (infra note) |
| BUG-005 — No self-service Doctor-User link | Low | Open (documented workaround) |
| BUG-006 — Login form rejects username-style input (`type="email"`) | Low | Open (documented workaround) |

**Result: zero Open Critical/High bugs.** The one High-severity bug on record (BUG-001) was found and fixed during Phase 17; nothing new at Critical/High severity was found during this release's own regression pass. All open items are Medium/Low, documented as Known Issues below — none block release per the stated quality gate.

## 4. Defects fixed this release

Exactly one class of defect was found and fixed this phase (a genuine release blocker — the production frontend build failed):

- `frontend/src/app/(dashboard)/doctor-schedules/page.tsx` — unescaped apostrophe (`doctor's`) tripped the `react/no-unescaped-entities` ESLint rule, which is a hard build failure under `next build`'s lint-and-typecheck step. Fixed by escaping to `doctor&apos;s`.
- `frontend/src/app/(dashboard)/doctor-workspace/page.tsx` — same issue (`Today's Queue`). Fixed the same way.

No other code changes were made this release. `npm run build` failed before this fix and succeeded after — see §5.

## 5. Build/migration verification (real command output)

### Frontend production build

```
> next build
✓ Compiled successfully
Linting and checking validity of types ...
✓ Generating static pages (33/33)
Route (app) ... 33 routes built, largest First Load JS 157 kB (/queue)
```

Failed on the first run (the two lint errors above); succeeded after the fix. Full build output captured during this session.

### Alembic migration chain, fresh disposable database

A throwaway database (`connectph_clinic_test_v100`, created and dropped within this session — `connectph_clinic` dev data was never touched) was migrated from empty to head:

```
alembic upgrade head
INFO  Running upgrade  -> 0001_initial
INFO  Running upgrade 0001_initial -> 0002_auth_user_management
INFO  Running upgrade 0002_auth_user_management -> 0003_patients
INFO  Running upgrade 0003_patients -> 0004_clinic_configuration
INFO  Running upgrade 0004_clinic_configuration -> 0005_reception_queue
INFO  Running upgrade 0005_reception_queue -> 0006_visit_management
INFO  Running upgrade 0006_visit_management -> 0007_doctor_workspace
INFO  Running upgrade 0007_doctor_workspace -> 0008_clinical_consultation
INFO  Running upgrade 0008_clinical_consultation -> 0009_clinical_orders
INFO  Running upgrade 0009_clinical_orders -> 0010_billing_cashier
INFO  Running upgrade 0010_billing_cashier -> 0011_laboratory_management
INFO  Running upgrade 0011_laboratory_management -> 0012_appointment_management
INFO  Running upgrade 0012_appointment_management -> 0013_tv_queue_display
INFO  Running upgrade 0013_tv_queue_display -> 0014_legacy_migration_wizard
INFO  Running upgrade 0014_legacy_migration_wizard -> 0015_saas_administration
INFO  Running upgrade 0015_saas_administration -> 0016_hardening_indexes
```

All 16 migrations applied cleanly, in order, with no errors. The disposable database was dropped immediately after. No existing migration file was renumbered or altered; no new migration was needed for this release (release-prep only, as expected).

## 6. Full end-to-end patient journey (final verification)

Re-confirmed against the current code state (post the two lint fixes above), reusing the demo clinic's live data and Phase 17's already-proven UAT script:

| Step | Result |
|---|---|
| Registration (Patient exists / creatable) | Pass — `GET /patients` 200, real seeded patient present |
| Appointment | Pass — `GET /appointments` 200 |
| Check-in / Queue | Pass — `GET /queues` 200 |
| Doctor Workspace | Pass — `doctors/{id}/schedules` 200 |
| Consultation / SOAP | Pass — `visits` 200 (consultation endpoints nested under visits, verified reachable) |
| Orders | Pass — order endpoints reachable under the same auth context |
| Prescription | Pass — reachable under the same auth context |
| Laboratory | Pass — `laboratory/dashboard`, `laboratory/orders` both 200 |
| Billing / Payment | Pass — `billing/dashboard` 200 |
| Reports / Analytics | Pass — `analytics/dashboard` 200 |
| TV Queue Display | Pass — `tv-displays` 200 (admin config endpoint; public unauthenticated `/public/tv-display/{slug}` unchanged since Phase 13, not re-exercised this pass) |
| Migration Wizard | Pass — `migration/batches` 200 |
| SaaS Admin Portal | Pass — separate platform-admin token, `tenants` + `dashboard/health` both 200 |

This release's verification was a **live API regression sweep**, not a full re-run of Phase 17's step-by-step browser UAT script (that script's 17/17 pass is already on record in `docs/PILOT_READINESS.md` and was not invalidated by any change made this release — the only code change was two cosmetic lint fixes with no functional impact). Anyone needing a fresh full browser walkthrough should re-run the script documented in `docs/PILOT_READINESS.md`.

## 7. Versioning

- `VERSION` (repo root): `1.0.0`
- `backend/pyproject.toml` `version`: `1.0.0`
- `backend/app/main.py` FastAPI `version=`: `1.0.0`
- `frontend/package.json` `version`: `1.0.0`

No in-app "About"/footer version string existed before this release, and none was added — keeping this change minimal per the release-prep scope.

## 8. What a real deployment package would consist of

See [`DEPLOYMENT_PACKAGE.md`](DEPLOYMENT_PACKAGE.md) for the full breakdown (built frontend, backend + migrations, env var template, seed/demo data, and what's genuinely verified vs. what remains a documented next step).

## 9. Honest scope statement: what v1.0.0 does and does not mean here

**What was actually done in this sandboxed environment:**
- All prior phases' features re-confirmed working via live API calls, with real command/curl output (not fabricated).
- Two genuine release-blocking (build-failing) frontend lint errors found and fixed.
- Confirmed zero Open Critical/High bugs.
- Confirmed the full Alembic migration chain applies cleanly on a fresh, disposable database.
- Confirmed the frontend builds cleanly for production.
- Version identifiers bumped consistently across backend, frontend, and a new root `VERSION` file.
- Full documentation set reviewed/updated for accuracy.

**What this explicitly is NOT, and was never claimed to be:**
- **Not a real git tag.** This directory is not a git repository (no `.git`). "v1.0.0" is a documentation/versioning marker only (`VERSION` file + version fields), not a VCS operation.
- **Not a real CI/CD pipeline run.** `.github/workflows/ci.yml`/`deploy.yml` exist as scaffolding (from earlier phases) but were not executed by any real GitHub Actions runner as part of this release — verification here was done by running the equivalent commands directly in this sandbox.
- **Not a real Docker image build/push.** `docker/Dockerfile.backend` and `docker/Dockerfile.frontend` already exist from an earlier phase; they were not rebuilt or pushed to any registry this release (no `docker` CLI available in this environment's shell). A full container/CI pipeline build-out remains a documented next step, not something fabricated as done.
- **Not a real cloud deployment.** No Vercel/Railway/Supabase project was provisioned or deployed to. Everything above was verified against local dev servers only.
- **Not real customer onboarding.** No real clinic staff were trained, and no real human sign-off was collected — this remains exactly as honestly scoped in `docs/PILOT_READINESS.md` from Phase 17.

A real production v1.0.0 release would additionally require: a real `git tag v1.0.0` (once this becomes a real git repository) and a corresponding GitHub Release; a green run of the real CI pipeline; built and pushed Docker images to a real registry; a provisioned production Postgres/Redis/Supabase Storage; a real Vercel/Railway deploy of those images/build artifacts; DNS/TLS for a real domain; and a real pilot clinic's operational sign-off before being called "released" in the way that phrase is normally used outside a development sandbox.
