# Pilot Readiness Report — Phase 17 (v0.17.0)

This report is honest about what "Phase 17 UAT" means in this codebase's
actual environment: **a fully scripted, agent-run technical walkthrough
against a real running dev instance, with real HTTP calls and real
database rows — not a human clinic administrator's sign-off, and not a
real production deployment.** Both of those still need to happen with
real people before this platform runs a real clinic's real patients.
This document draws the line clearly between the two.

## What was verified as technically ready

### 1. Deployment readiness (config/documentation, not a live cloud deploy)

- `backend/.env.example` and `frontend/.env.example` reviewed for
  completeness against what the running app actually reads
  (`DATABASE_URL`, `JWT_*`, `REDIS_URL`, `SMTP_*`, `SUPABASE_*`,
  `CORS_ORIGINS`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_AUTH_COOKIE_NAME`)
  — no missing variables found.
- HTTPS reverse-proxy expectations, Railway/Vercel/Supabase setup steps,
  required secrets, and the CI/CD flow are documented in
  `docs/DEPLOYMENT.md` (built up through Phase 16; re-reviewed this
  phase, still accurate — no changes needed).
- Database config: Alembic migration chain confirmed at a single linear
  head (`0016_hardening_indexes`, no Phase 17 schema changes needed).
- File storage config: Supabase Storage bucket-per-clinic-prefix pattern
  documented in `docs/DEPLOYMENT.md`.
- Scheduled/background jobs: the Legacy Migration Wizard's import runs
  as a FastAPI `BackgroundTasks` job (no external job-queue dependency);
  documented in `docs/MIGRATION.md`.
- Logging/monitoring: request-ID header, structured error envelope,
  `/health`/`/live`/`/ready` probes — built and verified in Phase 16,
  re-confirmed reachable this phase.
- Automatic backups: `pg_dump`-based backup service exists and was
  verified working in Phase 16 (see `docs/BACKUP.md`); **scheduling it**
  (cron/managed-provider automation) and off-host storage remain real
  gaps for a production deployment, documented as such, not silently
  glossed over.
- **Not done, and not claimed to be done**: no real cloud host was
  provisioned or deployed to this phase. Everything above is verified
  against the local dev stack (Postgres on port 5433, backend on
  8006/8007, frontend on 3000/3001).

### 2. Pilot tenant setup — real, live, verified

A clinic tenant ("Pilot Community Clinic") was created via
`POST /auth/register` and configured end-to-end via real API calls
(not a seed script bypass), verified by reading each resource back:

| Resource | Status |
|---|---|
| Branch (Main Branch) | Created, verified |
| Departments | Seeded via `/departments/seed-defaults`, verified |
| Services | Seeded via `/services/seed-defaults`, verified |
| Consultation Room | Created, verified |
| Doctor (Dr. Juan Dela Cruz) + weekly schedule (Mon–Fri, 08:00–17:00) | Created, verified |
| Operating Hours (Mon–Fri) | Created, verified |
| Queue Settings + Priority Types (Senior/PWD/Pregnant/Emergency/VIP, seeded) | Created, verified |
| Staff users (Owner + a Doctor-role login linked to the Doctors record) | Created, verified — see BUG-005 for the one manual step this required |

### 3. Legacy Migration Wizard — real hands-on end-to-end test

Full detail in `docs/MIGRATION.md`'s new Phase 17 section. Summary: a
realistic 5-patient / 2-doctor CSV sample (deliberately missing a
`civil_status` column, matching a common real-world legacy-export gap)
was run through Choose Source → Connect → Analyze → Map Fields →
Preview → Validate & Resolve → Import → Verify. This exposed and led to
fixing **BUG-001** (a High-severity bug where resolving a validation
issue had no effect on import — see `docs/BUGS.md`). After the fix, all
5 patients and 2 doctors imported correctly, confirmed via the
Verification Report (`overall_ok: true`) and independently via
`GET /patients`/`GET /doctors`.

Only Patients and Doctors actually write to the database in this build
— the other 15 entity types in the migration wizard's 17-step order are
mapping/validation-ready but intentionally skipped on import (a
pre-existing, code-documented scope decision from Phase 14, tracked as
informational **BUG-003**, not fixed or newly introduced this phase).

### 4. User Acceptance Testing — full scripted patient journey, 17/17 steps passing

Executed as a Python script driving real HTTP calls against the live
backend (port 8007) with a real pilot patient, appointment, doctor
login, and payment — not mocked, not a dry run. Full step list and
result:

| # | Step | Result |
|---|---|---|
| 1 | Registration (create patient, duplicate-check override) | PASS |
| 2 | Lookup doctor/branch/service/department master data | PASS |
| 3 | Appointment booking (via real available-slots lookup) | PASS |
| 4 | Appointment confirm | PASS |
| 5 | Check-in (creates Queue ticket + Visit) | PASS |
| 6 | Queue list reflects the new ticket | PASS |
| 7 | Queue call-in and start-consultation (Doctor Workspace) | PASS |
| 8 | Consultation open | PASS |
| 9 | Consultation SOAP notes (as the assigned doctor) | PASS |
| 10 | Clinical order (Laboratory — CBC) | PASS |
| 11 | Prescription (Paracetamol, full dosage/frequency/duration) | PASS |
| 12 | Consultation complete (auto-creates Draft invoice) | PASS |
| 13 | Laboratory workflow: collect → start-processing → enter results → release | PASS |
| 14 | Billing: fetch the auto-created invoice | PASS |
| 15 | Billing: record full payment | PASS |
| 16 | Billing: printable receipt | PASS |
| 17 | Completion: Visit status reaches `Completed` | PASS |

**17 / 17 passed.** Getting to 17/17 required two real script
corrections along the way that are worth being explicit about (neither
was a product bug — both are documented in `docs/USER_MANUAL.md`/
`docs/BUGS.md` BUG-002 as real UX/workflow subtleties a real user would
also need to learn):

- Step 7 had to be added — a first pass that skipped straight from
  check-in to opening the consultation left the Visit stuck at
  `Waiting` even after full payment (this is what BUG-002 documents).
  The correct flow uses the Doctor Workspace's **Call** then **Start
  Consultation** actions, which is what a real doctor's UI does.
- The Doctor-role login used for steps 9–13 needed its `User.doctor_id`
  manually linked to the Doctors record first (BUG-005) — there's no
  self-service way to do this yet.

## Bugs found and their disposition

See `docs/BUGS.md` for full entries. Summary:

| ID | Severity | Disposition |
|---|---|---|
| BUG-001 | High | **Fixed this phase** — Legacy Migration Wizard resolution-aware skip logic |
| BUG-002 | Medium | Logged, not fixed — workaround exists (use Doctor Workspace's Call/Start-Consultation) |
| BUG-003 | Low | Logged, not fixed — pre-existing documented scope decision, informational |
| BUG-004 | Low | Logged, not fixed — sandboxed dev environment resource limit (pytest/argon2), not an app bug |
| BUG-005 | Low | Logged, not fixed — missing self-service capability, not a regression |

Per this phase's scope, only Critical/High bugs found during this
phase's own testing were fixed. BUG-001 was the one High-severity
finding; it's fixed. No Critical issues were found.

## What remains — explicit next steps for a REAL pilot

These are not things an agent can complete. They require real people and
a real production environment:

1. **Real user training sessions.** `docs/USER_MANUAL.md` and
   `docs/ADMINISTRATOR_GUIDE.md` are the reference material for this,
   but no actual Reception/Doctor/Laboratory/Cashier/Administrator/Owner
   staff have been trained. Schedule real, hands-on training sessions
   with the actual pilot clinic's staff before go-live.
2. **Real sign-off from each role.** This report confirms the scripted
   technical walkthrough passed end-to-end. It is explicitly **not** a
   substitute for a real Receptionist, Doctor, Laboratory technician,
   Cashier, Administrator, and Owner each independently trying their own
   real daily tasks in the system and confirming, in their own words,
   that it works for them. Get that sign-off, in writing, before
   treating this as pilot-ready in the business sense.
3. **A real production host cutover.** Nothing in this phase touched a
   real cloud deployment — `docs/DEPLOYMENT.md` documents how to do
   this (Vercel/Railway/Supabase), but no production Vercel/Railway/
   Supabase project exists yet for this pilot. Provision one, run
   through the Phase 16 production checklist in `docs/DEPLOYMENT.md`
   section 8 against the real production environment (not just the dev
   environment it was originally verified in), and complete the
   production-only TODOs listed there (real `CORS_ORIGINS`, a reachable
   production Redis, off-host backup storage/scheduling).
4. **A real legacy data migration**, if this pilot clinic is cutting
   over from an existing system — the wizard works (see above), but it
   needs to be run against that clinic's actual export, not a synthetic
   sample, with a real administrator reviewing every validation issue
   and verification report before trusting the result.
5. **Real support infrastructure** — see `docs/SUPPORT_GUIDE.md`'s
   closing note: this pilot has no on-call rotation, SLA, or ticketing
   system yet.

## Verification evidence

- Backend (`backend/app/main.py` import, `py_compile` of the changed
  file) compiles cleanly; a second backend instance was started on port
  8007 specifically to load the BUG-001 fix (the original dev instance
  on 8006 is a separately-managed long-running process this session
  could not restart in-place).
- Frontend `npx tsc --noEmit` — clean, no errors.
- A second frontend dev server was started on port 3001 pointing at the
  fixed backend (`frontend/.env.local` updated to
  `NEXT_PUBLIC_API_URL=http://localhost:8007/api/v1`).
- All UAT steps above and the migration-wizard run were executed via
  real HTTP calls (Python `urllib`/curl) against the live port-8007
  backend and the real dev Postgres database (port 5433) — every
  "PASS" reflects an actual `2xx` response and, where relevant, an
  independent follow-up read (`GET /patients`, `GET /visits/{id}`,
  `GET /migration/batches/{id}/verify`) confirming the state actually
  changed, not just that the write call returned success.
