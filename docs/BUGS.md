# Bug Tracker

This is the living bug tracker for CONNECT.PH Clinic Platform. It is a lightweight, git-tracked log intended for small-team use during the foundation stage. Once the team adopts a dedicated issue tracker (GitHub Issues, Linear, Jira, etc.), this file should be migrated and retired in favor of that tool — but for now it is the source of truth.

## Status: Phase 19 (Patient Self-Service Appointment Booking) findings logged

Phase 19 (adding patient-initiated booking on top of Phase 11's appointment engine) found and fixed four real bugs live during implementation/verification (BUG-010 through BUG-013 — a doctor-picker filter bug, a missing import that silently broke reschedule under Python 3.14's lazy annotations, a partial unique index missing from the test schema, and a first-of-day counter race), and logged two Medium/Low items deferred as out of this phase's scope (BUG-008: no Service step in the booking wizard per the given spec order, blocking check-in until reception adds one; BUG-009: the pre-existing staff-facing reschedule path lacks the same IntegrityError→409 handling added to the patient-facing one). Everything found in earlier phases remains as previously logged.

---

## Process

1. **Anyone** who finds a bug adds an entry to the [Open Bugs](#open-bugs) table below, using the next sequential ID (`BUG-001`, `BUG-002`, ...).
2. Fill out a full entry using the [Entry Format](#entry-format) below in the "Details" section beneath the table — don't just add a table row.
3. Assign a **Severity**:
   - **Critical** — data loss, security issue, tenant data leaking across clinics, production down.
   - **High** — a core workflow is broken with no workaround.
   - **Medium** — a workflow is broken but has a workaround, or a non-core feature is broken.
   - **Low** — cosmetic, minor UX annoyance, edge case.
4. When work starts, set **Status** to `In Progress` and assign an owner.
5. When fixed, link the PR/commit, set **Status** to `Fixed`, and move the row to [Resolved Bugs](#resolved-bugs) with the resolution date.
6. If a reported bug turns out not to be a bug (expected behavior, duplicate, cannot reproduce), set **Status** to `Closed` and note why in Details — do not delete the entry.

## Severity vs. response expectation

| Severity | Expectation |
|---|---|
| Critical | Fix immediately, out-of-band of normal sprint work; notify the team |
| High | Fix within the current sprint/iteration |
| Medium | Scheduled into an upcoming iteration |
| Low | Backlog; fixed opportunistically or batched |

---

## Entry Format

```markdown
### BUG-XXX: <short descriptive title>

- **Reported by:** <name>
- **Date reported:** YYYY-MM-DD
- **Severity:** Critical | High | Medium | Low
- **Status:** Open | In Progress | Fixed | Closed
- **Area:** frontend | backend | db | infra | docs
- **Environment:** local | staging | production

**Description**
What is wrong, observed behavior.

**Steps to reproduce**
1. ...
2. ...

**Expected behavior**
What should happen instead.

**Actual behavior**
What actually happens (include error messages/stack traces/screenshots as needed).

**Root cause** (fill in once diagnosed)
...

**Fix / PR**
Link to the commit or PR that resolves this.

**Resolution date**
YYYY-MM-DD
```

---

## Open Bugs

| ID | Title | Severity | Status | Area | Owner |
|---|---|---|---|---|---|
| BUG-002 | Consultation-complete → Visit-complete sync silently no-ops if reception never drove Visit through Called/InConsultation | Medium | Open | backend | unassigned |
| BUG-003 | Legacy Migration Wizard only actually imports Patients/Doctors; Visits/Consultations/Prescriptions/Laboratory/Billing/Payments entities are defined but silently skipped | Low | Open | backend | unassigned |
| BUG-004 | Local pytest run hits `argon2.exceptions.HashingError: Memory allocation error` in this sandboxed dev environment | Low | Open | infra | unassigned |
| BUG-005 | No self-service way to link a Doctor-role User account to its Doctors master-data record (requires a direct DB update) | Low | Open | backend | unassigned |
| BUG-006 | Login page's email field is `type="email"` with HTML5 validation, silently rejecting username-style logins the backend actually accepts | Low | Open | frontend | unassigned |
| BUG-007 | Running two `pytest app/tests` invocations concurrently against the same disposable test database causes spurious deadlocks/failures | Low | Open | infra | unassigned |
| BUG-008 | Patient self-service booking wizard never collects a Service, so a patient-booked appointment can't be staff-checked-in until reception edits it to add one | Medium | Open | backend/frontend | unassigned |
| BUG-009 | Staff-side `AppointmentService.reschedule_appointment` has no `IntegrityError` handling around its re-insert, unlike the patient-facing path fixed this phase — a staff reschedule racing another booking for the same slot would surface a raw 500 instead of a clean 409 | Low | Open | backend | unassigned |
| BUG-015 | Browser reported `Error: [object Event]` (Next.js unhandled rejection overlay) | Low | Closed | frontend | unassigned |
| BUG-016 | No dedicated clinic-side Audit Log list/filter page or endpoint for Owner/Administrator — only the Owner Dashboard's Real-time Activity Feed (unfiltered, not paginated/searchable) surfaces `audit_logs` data, and the only structured `audit-logs` API is SaaS-level (`platform-admin/audit-logs`, a different portal/tenant model entirely) | Low | Open | backend/frontend | unassigned |
| BUG-017 | Sidebar shows every staff nav item (Users, Clinic Configuration section, Doctor Workspace, Laboratory, Billing, etc.) to every role regardless of actual access — only Analytics/TV Displays/Migration are role-gated | Medium | Open | frontend | unassigned |
| BUG-028 | `PATCH /clinics/{clinic_id}` and `DELETE /clinics/{clinic_id}` had no role restriction — any authenticated user of any role (incl. Receptionist, Doctor) could rename or soft-delete the clinic | Critical | Fixed | backend | unassigned |
| BUG-033 | The clinic-wide `QueueSetting` row saved from `/queue-settings` (branch_id always submitted as `null`) can never actually be selected by `_resolve_prefix`/`_resolve_max_daily_queue`, because resolution requires an EXACT `branch_id` match against the queue ticket's own (never-null) `branch_id`. The clinic-wide prefix currently "works" in production only by accident — because when no `QueueSetting` row matches, the code falls back to the hardcoded `DEFAULT_QUEUE_PREFIX = "A"`, which happens to equal what most clinics configure anyway. A clinic that changes its clinic-wide prefix or max-daily-queue via the Queue Settings page would find the change silently has zero effect on real tickets. Found while adding this session's per-doctor/department prefix overrides (which had to be built branch_id-aware to actually take effect, confirmed live via a real API+DB round trip) - not fixed inline since it's a pre-existing, unrelated defect, out of scope for the additive TV-display feature. | High | Open | backend | unassigned |
| BUG-034 | Running `app/tests/test_queues.py` together with `test_tv_display.py`/`test_doctor_workspace.py` (or even `test_queues.py` alone in full) intermittently but reproducibly 429s 2 of its own tests (`test_doctor_scoped_prefix_override_and_independent_sequencing`, `test_tenant_isolation`) with `"Too many attempts. Please try again later."` — both tests pass individually every time. Root cause: `RATE_LIMIT_LOGIN_MAX_ATTEMPTS=10` per 60s (`core/config.py`) is a real, shared, non-test-mode-bypassed limiter, and `test_queues.py` alone calls `_login()` well past 10 times across its full suite; running it back-to-back with other login-heavy files within the same ~60s window exhausts the budget for whichever test happens to log in last. Not caused by, or specific to, the Multi-Department TV Queue Display feature — reproduced twice, both times against the pre-existing `_login`/`_owner_headers` test helper shared by every test in the file, unrelated to any of this feature's own code. A real test-infra gap (the rate limiter should be disabled or reset between tests in the test environment), not a product bug — logged rather than fixed inline per this feature's "no unrelated changes" scope. | Medium | Open | infra | unassigned |

## Resolved Bugs

| ID | Title | Severity | Resolved | PR/Commit |
|---|---|---|---|---|
| BUG-030 | `PUT /consultations/{id}/soap` (Doctor's Assessment/Plan save) silently wiped every Subjective/Objective/vitals field back to `null` whenever the request didn't re-include them — which the Assessment/Plan UI has no reason to do, since Reception already saved vitals separately | Critical | 2026-08-06 | `backend/app/api/v1/consultations.py` (`save_soap`: `payload.model_dump(exclude_unset=True)`), `backend/app/services/consultation_service.py` (`ConsultationService.save_soap`: merge against existing row instead of blind overwrite, matching the sibling `save_soap_subjective_objective`) |
| BUG-022 | TV Queue Display does not re-announce a Recall of an already-"Now Serving" ticket — only genuinely new entries trigger the TTS announcement on the public display | High | 2026-08-06 | Root cause was two-layered: (1) backend `DoctorWorkspaceService.recall_patient()` (`backend/app/services/doctor_workspace_service.py`) never refreshed the linked `Queue.called_at` timestamp, so no consumer had any signal a recall had happened at all — fixed by stamping `called_at = now()` on the queue row during recall; (2) frontend `TvDisplayScreen.tsx` (`frontend/src/features/tv-display/components/TvDisplayScreen.tsx`) tracked only ticket *id* presence (`prevCalledIdsRef`), so even a changed `called_at` wouldn't have re-triggered the announcement — fixed by tracking id→`calledAt` pairs (`prevCalledAtRef`) and re-announcing when a known id's `calledAt` changes, not just when a new id appears. Both fixes verified live: recalling a ticket now visibly bumps `called_at` in `GET /tv-displays/{id}/preview`, confirmed via direct API re-check after a fresh backend restart (the first live check silently failed against a stale/zombie backend process that hadn't reloaded the service-layer file — a recurrence of this environment's documented zombie-backend issue, resolved by restarting the backend fresh per `docs/TESTING.md`'s standard workaround). Upgraded from the original Medium classification found during this session's UAT: recall's entire practical purpose in a live clinic is audibly re-paging a patient in the waiting room who missed the first call, so a Recall that is visually correct but audibly silent defeats the feature for its primary real-world use case — a core clinic operation. |
| BUG-001 | Legacy Migration Wizard: resolving a validation Error (Merge/Overwrite/CreateNew) had no effect — row still force-skipped and miscounted as a "duplicate" | High | 2026-07-27 | `backend/app/services/migration/migration_service.py` (uncommitted local fix, this phase) |
| BUG-027 | Vitals-before-Queue feature never actually triggered — frontend/backend `service_code` allowlists (`CONS`/`FOLLOWUP`) didn't match the real seeded codes (`CONSULT`/`FOLLOW-UP`) | High | 2026-07-29 | `backend/app/services/queue_service.py` (`PRE_QUEUE_VITALS_SERVICE_CODES`), `frontend/src/features/queue/components/NewQueueDialog.tsx` (`PRE_QUEUE_VITALS_SERVICE_CODES`) |
| BUG-026 | Doctor Session Control: starting a session on the same day a prior session was already ended crashed with a `500` (unhandled `IntegrityError`) | High | 2026-07-29 | `backend/app/services/doctor_workspace_service.py` (`start_session`: reopen the existing same-day row instead of always inserting) |
| BUG-020 | TV Queue Display showed an empty "Now Serving"/"Next in Queue" even with real, active (`Waiting`/`Called`/`Serving`) queue tickets for the clinic — `TvDisplayService._build_display_data` filtered `Queue.queue_date == date.today()`, where `date.today()` resolves to the **server process's OS-local timezone**, while every other "today" computation in the codebase (`QueueService.create_ticket`'s duplicate-check/queue_date default, `DoctorWorkspaceService`) explicitly uses `datetime.now(UTC).date()`. On this dev box the OS-local date had already rolled to the next calendar day while UTC (and every stored `queue_date`) was still on the previous day, so the TV display's "today" filter matched nothing even though `/queues` showed the same tickets correctly for the real UTC "today". Confirmed live: a `Serving` ticket (`A010`) and a `Waiting` ticket (`A011`) existed in the DB with `queue_date` matching UTC-today, but `GET /public/tv-display/{slug}` returned `now_serving: [], next_waiting: []` until the fix. Root cause reproduced with a direct DB query showing `date.today()` (`2026-07-29`) one day ahead of `datetime.now(UTC).date()` (`2026-07-28`) in the same process. | Critical | 2026-07-28 | `backend/app/services/tv_display_service.py` (`_build_display_data`/`get_public_display_data`: replaced `date.today()` with `datetime.now(UTC).date()`, matching `queue_service.py`'s existing convention; also fixed the same call for announcement filtering) |
| BUG-019 | "Remove Discount" (Round 2, item 3) had no backend endpoint at all — only "Apply Discount" existed, despite the client-approved item explicitly listing both | High | 2026-07-28 | `backend/app/repositories/invoice_repository.py` (`get_discount`/`delete_discount`), `backend/app/services/invoice_service.py` (`remove_discount`), `backend/app/api/v1/billing.py` (`DELETE /invoices/{id}/discounts/{id}`), `frontend/src/features/billing/api/billing-api.ts`/`hooks/use-invoice-mutations.ts` (`removeDiscount`/`useRemoveDiscount`), `frontend/src/app/(dashboard)/billing/[id]/page.tsx` (Remove button per discount) |
| BUG-024 | Invoice discount audit trail (`invoice.discount_applied`/`invoice.discount_removed`) was missing the user-typed `reason` field in its metadata — `reason` was correctly stored on the `InvoiceDiscount` row itself, but never copied into the audit log, so the audit trail showed User/Date/Amount/Discount-type but not Reason, undermining its use as a "why was this discount given" record | Low | 2026-07-29 | `backend/app/services/invoice_service.py` (`apply_discount`/`remove_discount`: added `"reason"` to the `metadata` dict passed to `audit_service.log_event`) |
| BUG-021 | `POST /shifts/{id}/close` and `POST /shifts/{id}/reopen` (Phase 21: Receptionist Shift Management) both 500'd with `sqlalchemy.exc.MissingGreenlet` — `Shift.updated_at` (an `onupdate=func.now()` DB-side column) gets expired after the `UPDATE`, and building the response's `ShiftRead(...)` read `shift.updated_at` synchronously right after, triggering an implicit lazy-refresh outside an awaited context | High | 2026-07-29 | `backend/app/services/shift_service.py` (`close_shift`/`reopen_shift`: added `await self.session.refresh(shift)` after `flush()`) |
| BUG-010 | `patient-portal/appointments/doctors` filtered out every doctor with no `branch_id`/`department_id` assigned (strict equality, not `OR IS NULL`), so patients could not book the clinic's only seeded doctor at all | Medium | 2026-07-28 | `backend/app/api/v1/patient_portal/appointments.py` (Phase 19) |
| BUG-011 | Missing import (`PatientAppointmentRescheduleRequest`) in the new patient booking router silently misparsed the reschedule endpoint's body as a query param (`422` on every real reschedule call) — Python 3.14's lazy annotation evaluation (PEP 649) meant the missing name wasn't caught until FastAPI evaluated the route's type hints, not at module import time | Medium | 2026-07-28 | `backend/app/api/v1/patient_portal/appointments.py` (Phase 19) |
| BUG-014 | `npm run build` failed ESLint's `react/no-unescaped-entities` on two pre-existing Phase 18 files (`patient-portal/billing/page.tsx`, `patient-portal/login/page.tsx`, unescaped apostrophes) | Low | 2026-07-28 | `frontend/src/app/patient-portal/billing/page.tsx`, `frontend/src/app/patient-portal/login/page.tsx` (escaped to `&apos;`) |
| BUG-012 | The partial unique index preventing appointment double-booking (`uq_appointments_doctor_slot_active`, migration 0012) only existed via raw SQL in the migration, never in the SQLAlchemy model's `__table_args__` — so `Base.metadata.create_all()` (how `conftest.py`'s test-database schema is built) never created it, meaning any test asserting on it (this phase's concurrency test included) was silently running against a schema missing the real guarantee it claimed to prove | Medium | 2026-07-28 | `backend/app/models/appointment.py` (Phase 19) |
| BUG-013 | `AppointmentNumberGenerator`'s daily counter (`system_settings`-backed, Phase 9) locks its row with `SELECT ... FOR UPDATE`, which only protects concurrent *updates* — the very first booking of the day for a clinic still races on the counter row's own `INSERT` if two requests hit it simultaneously, surfacing as a raw `IntegrityError`/500 instead of the intended clean 409. Found by this phase's concurrent-booking test. Fixed for the patient-facing create/reschedule paths by widening the existing `try/except IntegrityError` to also cover number generation; the shared Phase 9 counter implementation itself (also used by Orders/Prescriptions) was not touched | Medium | 2026-07-28 | `backend/app/services/appointment_service.py` (Phase 19) |

---

## Phase 17 Entries

### BUG-001: Legacy Migration Wizard silently force-skips rows with a resolved validation Error

- **Reported by:** Phase 17 UAT (agent-run, Legacy Migration Wizard hands-on test)
- **Date reported:** 2026-07-27
- **Severity:** High
- **Status:** Fixed
- **Area:** backend
- **Environment:** local

**Description**
`POST /migration/batches/{id}/issues/{issue_id}/resolve` lets an admin resolve a validation Error to `Merge`/`Overwrite`/`CreateNew`/`Skip` before running the import — the whole point of the "resolve" step. But `MigrationService.import_entity` (and `preview_entity`) computed the skip-set from *every* row with an Error-severity issue, regardless of its `resolution` field. So resolving an issue to anything other than the literal string `Skip` had zero effect: the row was still force-skipped during import, and worse, it was counted into `total_duplicates` in the batch summary — a legacy CSV missing an optional field with a safe default (e.g. `civil_status`, which `_import_one` already defaults to `Single`) imported **zero** patients, with the summary misleadingly suggesting they were duplicates rather than validation errors.

**Steps to reproduce**
1. Create a migration batch, upload a `patients.csv` that has no `civil_status` column (a very common real-world legacy export shape).
2. `POST .../validate?entity_type=Patients` — 1 Error per row ("Required field 'civil_status' missing").
3. Resolve each issue via `PATCH .../issues/{id}/resolve` with `{"resolution": "CreateNew"}`.
4. `POST .../preview?entity_type=Patients` still reports `rows_to_import: 0, rows_to_skip: 5`.
5. Running the import imports 0 patients; batch summary shows them under `total_duplicates`.

**Expected behavior**
Once an issue is resolved (any value other than `Unresolved`), its row should be imported normally — only an *unresolved* Error, or a resolution explicitly set to `Skip`, should hold the row back.

**Actual behavior**
See above — `error_row_ids` was computed purely from `severity == ERROR`, ignoring `resolution` entirely.

**Root cause**
`backend/app/services/migration/migration_service.py`, `import_entity()` (and the analogous set in `preview_entity()`): `error_row_ids = {i.source_row_identifier for i in issues if ... severity == ERROR}` — missing an `and i.resolution == MigrationIssueResolution.UNRESOLVED` filter.

**Fix / PR**
`backend/app/services/migration/migration_service.py` — both `error_row_ids` (in `import_entity`) and `error_rows` (in `preview_entity`) now additionally require `resolution == MigrationIssueResolution.UNRESOLVED`. Verified live: after the fix, resolving all 5 issues on a real batch and re-running `preview`/`retry-batch` imported all 5 patients (`total_records_imported` went from 2 (Doctors only) to 7 (5 Patients + 2 Doctors)), confirmed via `GET /migration/batches/{id}/verify` (`expected == imported` for every entity) and `GET /patients`.

**Resolution date**
2026-07-27

---

### BUG-002: Consultation-complete → Visit-complete sync silently no-ops if reception/doctor never explicitly called/started the visit

- **Reported by:** Phase 17 UAT (agent-run, scripted patient-journey walkthrough)
- **Date reported:** 2026-07-27
- **Severity:** Medium
- **Status:** Open
- **Area:** backend
- **Environment:** local

**Description**
`Visit.status` only reaches `Completed` via a legal path through `VISIT_STATUS_TRANSITIONS` (`Waiting → Called → InConsultation → Completed`). `ConsultationService.complete_consultation()` correctly declines to force an illegal transition when the Visit is stuck earlier in the chain — but it does this *silently*: no warning, no error, no flag on the response. In the first UAT run, a visit was checked in (`Waiting`) and taken straight to opening a consultation, recording SOAP notes, orders, a prescription, completing the consultation, and fully paying the resulting invoice — every one of those steps returned `200 OK` — yet the Visit was still sitting at `Waiting` at the end, with nothing in any response indicating why. The real UI flow (Doctor Workspace's "Call" and "Start Consultation" buttons) does drive the Visit through the required transitions, so this is a workaround-available gap, not a fully broken workflow — but a same-shaped bypass (e.g. a future API-driven integration, or a UI path that opens a consultation without the two Doctor Workspace calls) would reproduce it with no error surfaced anywhere.

**Steps to reproduce**
1. Check in an appointment (Visit → `Waiting`).
2. Skip `POST /doctor-workspace/visits/{id}/call` and `.../start-consultation`.
3. Open a consultation directly via `POST /visits/{id}/consultation/open`, complete SOAP/orders/prescription, then `POST /consultations/{id}/complete`.
4. Pay the auto-created invoice in full.
5. `GET /visits/{id}` still shows `"status": "Waiting"`.

**Expected behavior**
Either the intended flow should be enforced/documented clearly enough that this can't be silently bypassed, or `complete_consultation`/the invoice-paid path should surface a warning when a Visit is left un-synced instead of a bare no-op.

**Actual behavior**
No error, no warning; Visit is left stuck at `Waiting` with the consultation, orders, prescription, and invoice all in fully-completed states.

**Root cause**
`backend/app/services/consultation_service.py::complete_consultation()` — the sync block is gated on `VisitStatus.COMPLETED in VISIT_STATUS_TRANSITIONS.get(visit.status, set())` and does nothing (not even a log line visible to the API caller) when that's false.

**Fix / PR**
Not fixed this phase (Medium, workaround exists via the documented Doctor Workspace call/start-consultation actions — this was a test-script gap, not a blocking product defect, once the correct endpoints were used). Recommended follow-up: emit a structured warning (e.g. on the Consultation-complete response, or an audit-log entry) when this no-op path is hit, so a future silent-bypass isn't invisible.

**Resolution date**
n/a

---

### BUG-003: Legacy Migration Wizard only implements Patients/Doctors import; other entity types are silently skipped

- **Reported by:** Phase 17 UAT (agent-run)
- **Date reported:** 2026-07-27
- **Severity:** Low
- **Status:** Open
- **Area:** backend

**Description**
`MigrationEntityType` enumerates 17 entities (Clinic, Branches, Departments, Doctors, Users, Patients, Services, Visits, QueueHistory, Consultations, Diagnoses, Prescriptions, Laboratory, Billing, Payments, Attachments, AuditLogs), but `IMPLEMENTED_ENTITIES = {PATIENTS, DOCTORS}` — every other entity type is marked `Skipped` during import with a warning-level log line, not an error. This is an explicit, code-commented scope decision from Phase 14, not a regression, but the Phase 17 spec asked for a migration test against "patients/doctors/visits/prescriptions/laboratory/billing records" — Visits/Prescriptions/Laboratory/Billing cannot actually be exercised end-to-end yet.

**Expected behavior / recommendation**
Documented here for visibility rather than fixed (out of scope for Phase 17, which fixes only bugs found in existing code, not new features). A future phase should either implement the remaining entity importers or make the Migration Wizard UI clearly communicate "supported entities: Patients, Doctors" up front so an admin doesn't upload a full legacy export expecting all of it to land.

**Status:** Open (informational / scope-tracking, not a defect to fix under Phase 17's own-bugs-only rule).

---

### BUG-004: `pytest` fails in this sandboxed dev environment with an argon2 memory allocation error

- **Reported by:** Phase 17 (agent, attempting to run `app/tests/test_migration.py` against the disposable `connectph_clinic_test` database)
- **Date reported:** 2026-07-27
- **Severity:** Low
- **Status:** Open
- **Area:** infra

**Description**
Running `pytest app/tests/test_migration.py` against the disposable `connectph_clinic_test` database (verified safe per `conftest.py`'s "test"-in-name guard) fails during fixture setup with `argon2.exceptions.HashingError: Memory allocation error` inside `passlib`'s argon2 hasher (`memory_cost=65536`, i.e. 64 MB per hash). This reproduced consistently in this sandbox and looks like an environment memory ceiling rather than an application bug — the same interpreter runs the full FastAPI app under uvicorn without issue. Not investigated further this phase (infra/environment, not app code); flagging so whoever manages the sandbox's resource limits can decide whether to raise them or lower argon2's `memory_cost` for test runs specifically.

**Status:** Open (infra note).

---

### BUG-005: No self-service way to link a Doctor-role User to its Doctors master-data record

- **Reported by:** Phase 17 UAT (agent, setting up the pilot tenant's doctor user)
- **Date reported:** 2026-07-27
- **Severity:** Low
- **Status:** Open
- **Area:** backend

**Description**
`POST /users` (create staff user) accepts a `role_id` but has no field to set `User.doctor_id`, the column that `ConsultationService`'s edit-access check (`current_user.doctor_id == visit.doctor_id`) depends on. To get a working Doctor-role login for this phase's UAT, the link had to be set with a direct `UPDATE users SET doctor_id = ...` SQL statement — there's no API/UI path for an Administrator to do this themselves.

**Expected behavior**
`UserCreate`/`UserUpdate` (or a dedicated endpoint) should let an Administrator set/change which Doctors record a Doctor-role user is linked to.

**Status:** Open (feature gap noted during setup, not fixed — out of scope for Phase 17's fix-only-what-this-phase-found-broken rule, since it's a missing capability rather than a regression in existing code).

---

### BUG-006: Login form rejects username-style credentials the backend accepts

- **Reported by:** Independent Phase 17 verification (browser check, resuming the pilot tenant login after the agent's own report)
- **Date reported:** 2026-07-28
- **Severity:** Low
- **Status:** Open
- **Area:** frontend

**Description**
`POST /auth/login` accepts a `email_or_username` field and the pilot tenant's Owner account was created with `username: "pilotowner"` (plus a real email on file, `pilotowner@example.com`). The login page's field is rendered with `type="email"`, so the browser's built-in HTML5 validation ("Enter a valid email address") blocks submission entirely when a plain username is typed — the request never reaches the backend at all. Login only succeeds when the associated email address is used instead.

**Steps to reproduce**
1. Go to `/login`.
2. Type `pilotowner` into the email field, a valid password into the password field.
3. Click "Sign in".

**Expected behavior**
Either the field should accept plain-text input (matching the backend's `email_or_username` support), or the UI should make clear that only email addresses are accepted for login, not usernames.

**Actual behavior**
Client-side browser validation silently blocks the request before it reaches the API; the only feedback is "Enter a valid email address," which doesn't explain that a username would otherwise be a valid credential per the backend.

**Root cause**
The login form's email input is declared with `type="email"` rather than `type="text"`, so the browser enforces RFC-5322-ish email shape client-side regardless of what the backend actually accepts.

**Fix / PR**
Not fixed this pass — cosmetic/UX only, not a functional blocker since every account in this system has an email on file and the frontend never surfaces a username-only account. Recommended follow-up: change the input to `type="text"` with a placeholder/label update ("Email or username"), or drop username-based login support entirely if it's not meant to be UI-facing.

**Resolution date**
n/a

---

### BUG-007: Concurrent `pytest app/tests` runs against the same test database cause spurious deadlocks/failures

- **Reported by:** Phase 18 (Patient Portal) agent, while verifying the full suite still passes after adding `test_patient_portal.py`
- **Date reported:** 2026-07-28
- **Severity:** Low
- **Status:** Open
- **Area:** infra

**Description**
The session-scoped `engine` fixture in `conftest.py` runs `DROP SCHEMA public CASCADE` / recreates it at the start of every `pytest` session. If a previous `pytest` process against the same `connectph_clinic_test` database is still alive (e.g. an earlier invocation that was killed via a shell `timeout` wrapper without the killed process's own DB connections being cleanly closed, leaving a connection "idle in transaction"), a second concurrent `pytest` invocation's schema-drop deadlocks against it (`asyncpg.exceptions.DeadlockDetectedError`), which then cascades into ~180 fixture-setup errors for the rest of that run. This is a test-infra race, not an application bug — a single, uncontested `pytest app/tests` run (verified by checking `Get-Process` for stray `python.exe -m pytest` processes and terminating any lingering idle-in-transaction connections via `pg_terminate_backend` first) passes cleanly.

**Steps to reproduce**
1. Start a `pytest app/tests` run and kill it mid-run via an external process-level timeout (not `pytest`'s own signal handling), leaving a DB connection "idle in transaction".
2. Immediately start a second `pytest app/tests` run against the same database.
3. Observe `DeadlockDetectedError` on `DROP SCHEMA public CASCADE` and a cascade of fixture-setup errors.

**Expected behavior**
Either the test suite should be resilient to a stale/dangling connection, or (more practically) tooling/CI should never run two `pytest` invocations concurrently against one shared test database in the first place.

**Actual behavior**
A stale connection from a previously-killed run causes the next run's schema-drop to deadlock, producing a wall of unrelated-looking fixture errors that could easily be mistaken for a real regression.

**Root cause**
`conftest.py`'s `engine` fixture unconditionally does a hard `DROP SCHEMA public CASCADE` at session start with no retry/backoff and no check for other active connections against the target database.

**Fix / PR**
Not fixed this pass — workaround (verify no other `pytest` process holds the test DB, terminate any lingering `idle in transaction` backends first) is sufficient and this is solely a local-dev/CI-hygiene concern, not a product defect. Recommended follow-up: wrap the schema-drop in a retry-with-backoff, or `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid()` before dropping.

**Resolution date**
n/a

---

### BUG-008: Patient booking wizard never collects a Service, blocking staff check-in until reception edits the appointment

- **Reported by:** Phase 19 (Patient Self-Service Appointment Booking) agent, during live browser + curl verification of the check-in → Queue/Visit flow
- **Date reported:** 2026-07-28
- **Severity:** Medium
- **Status:** Open
- **Area:** backend, frontend

**Description**
The spec's booking flow step order is exactly Branch → Department → Doctor → Type → Date → Time → Confirm — no Service step. `AppointmentService.check_in_appointment` (Phase 11, unchanged) requires both `department_id` AND `service_id` to be set, raising `400` otherwise. Since the patient booking endpoint accepts `service_id` as optional and the wizard never collects one, every patient-booked appointment has `service_id = None` and cannot be checked in by reception until someone edits the appointment to add a service first.

**Steps to reproduce**
1. Book an appointment through `/patient-portal/appointments/book` end to end.
2. As staff, attempt `POST /appointments/{id}/check-in`.
3. Observe `400 This appointment is missing a department/service and cannot be checked in.`

**Expected behavior**
Either the booking wizard collects a Service (would mean an 8th step, contradicting the given exact step order), or check-in derives a sensible default service from the appointment type/department when none was chosen at booking time.

**Actual behavior**
Confirmed via live curl test: an appointment created with `service_id` explicitly supplied checks in cleanly and creates a linked Queue+Visit exactly like a staff booking (see `docs/TESTING.md`'s Phase 19 section for the full request/response evidence); one created through the actual UI wizard (no service_id) hits the `400` above.

**Root cause**
The wizard's step order was specified without a Service step; `check_in_appointment`'s existing service_id requirement (Phase 11) was written assuming staff bookings always set one via the fuller staff form.

**Fix / PR**
Not fixed this pass — out of scope (the step order is explicitly given by spec). Recommended follow-up: either add an optional Service selector to step 4 (Type), or have reception's check-in flow prompt for a service inline when missing rather than hard-rejecting.

**Resolution date**
n/a

---

### BUG-009: Staff-side `reschedule_appointment` has no `IntegrityError` handling, unlike the patient-facing path

- **Reported by:** Phase 19 (Patient Self-Service Appointment Booking) agent, while adding concurrency-safety handling to the new patient-facing reschedule path and noticing the pre-existing staff-facing one lacked the equivalent
- **Date reported:** 2026-07-28
- **Severity:** Low
- **Status:** Open
- **Area:** backend

**Description**
`AppointmentService.reschedule_appointment` (staff-facing, Phase 11) re-inserts a new `Appointment` row for the new date/time with no `try/except IntegrityError` around it. If two staff users raced a reschedule onto the same doctor/date/time slot, the loser would get a raw `500` instead of a clean `409` from the partial unique index `uq_appointments_doctor_slot_active`. The patient-facing equivalent (`reschedule_patient_appointment`, added this phase) has this handling; the staff one does not.

**Steps to reproduce**
1. Two staff sessions reschedule two different appointments onto the exact same doctor/date/start_time simultaneously.
2. One raises `IntegrityError`, uncaught, surfacing as `500`.

**Expected behavior**
A clean `409 Conflict`, matching every other booking/reschedule path in this phase.

**Actual behavior**
Not reproduced live (would require orchestrating two genuinely concurrent staff sessions, out of this phase's scope), but confirmed by code inspection — `reschedule_appointment` (line ~209 in `backend/app/services/appointment_service.py`) has no try/except around its `self.repo.create(...)` call, unlike `_create_appointment_impl` and `reschedule_patient_appointment`.

**Root cause**
Pre-existing Phase 11 gap; not touched by this phase's review since the staff-facing path was reference-only, not part of Phase 19's scope to modify.

**Fix / PR**
Not fixed this pass — flagged for a follow-up patch mirroring the same `try/except IntegrityError → 409` wrap already applied to `_create_appointment_impl`/`reschedule_patient_appointment` in `backend/app/services/appointment_service.py`.

**Resolution date**
n/a

---

### BUG-010: Patient doctor picker excluded every doctor with no branch/department assignment

- **Reported by:** Phase 19 agent, live browser walkthrough of the booking wizard against the real dev database
- **Date reported:** 2026-07-28
- **Severity:** Medium
- **Status:** Fixed
- **Area:** backend

**Description**
`GET /patient-portal/appointments/doctors?branch_id=...&department_id=...` filtered with strict equality (`Doctor.branch_id == branch_id`). The dev database's only seeded doctor (Maria Santos) has `branch_id = NULL`/`department_id = NULL` (meaning "available at any branch/department", consistent with how `TimeSlotService` itself ignores these fields entirely). The strict-equality filter silently excluded her, so the Doctor step of the booking wizard showed "No doctors available for this branch/department" and no patient could book any appointment at all.

**Steps to reproduce**
1. Log in to the patient portal, click "+ Book Appointment".
2. Select the one seeded branch, then Department, then reach the Doctor step.
3. Observe empty doctor list despite an active doctor existing.

**Expected behavior**
A doctor with no branch/department assignment should be selectable regardless of which branch/department the patient picked, matching the slot-availability engine's own behavior.

**Actual behavior**
Confirmed and fixed live: after the fix, "Dr. Maria Santos" appears correctly at the Doctor step; re-verified via a fresh browser walkthrough all the way to a successful booking (`APT-20260729-000003`).

**Root cause**
`backend/app/api/v1/patient_portal/appointments.py::list_doctors` used `Doctor.branch_id == branch_id`/`Doctor.department_id == department_id` instead of `OR IS NULL`. The staff-side `DoctorRepository.search` has the identical gap (not fixed, staff endpoints are out of this phase's scope — pre-existing).

**Fix / PR**
`backend/app/api/v1/patient_portal/appointments.py` — filters now use `or_(Doctor.branch_id == branch_id, Doctor.branch_id.is_(None))` (same for department_id).

**Resolution date**
2026-07-28

---

### BUG-011: Missing import silently broke the patient reschedule endpoint (422 on every real call)

- **Reported by:** Phase 19 agent, while writing and running the reschedule/cancel integration test
- **Date reported:** 2026-07-28
- **Severity:** Medium
- **Status:** Fixed
- **Area:** backend

**Description**
`backend/app/api/v1/patient_portal/appointments.py` used `PatientAppointmentRescheduleRequest` as a body-parameter type annotation but never imported it (only `PatientAppointmentCreateRequest`/`PatientAppointmentCancelRequest`/etc. were imported). Python 3.14's lazy annotation evaluation (PEP 649) meant this didn't fail at module-import time — `app.main` imported cleanly, `python -c "import app.main"` passed, and the app even started and served other routes normally. It only surfaced when FastAPI evaluated that specific route's type hints (at first request to it, or at `app.openapi()`/schema-generation time), at which point it silently treated the whole `payload` parameter as a required scalar *query* parameter instead of a JSON body model, so every real reschedule call failed with `422 {"detail":[{"type":"missing","loc":["query","payload"], ...}]}` — a confusing error that gives no hint the real problem is a missing import.

**Steps to reproduce**
1. `python -c "import app.main"` — passes silently, no error.
2. Call `PATCH /patient-portal/appointments/{id}/reschedule` with a valid JSON body.
3. Observe `422`, `payload` reported as a missing *query* param.

**Expected behavior**
A missing import should be caught at import time (as it always was pre-3.14) or at minimum by `app.openapi()`/route registration, not silently misroute a real, valid request.

**Actual behavior**
Confirmed and fixed: added `PatientAppointmentRescheduleRequest` to the import list; `typing.get_type_hints(reschedule_appointment)` and `app.openapi()` both now resolve cleanly, and the reschedule integration test (`test_patient_reschedule_and_cancel_and_isolation`) passes.

**Root cause**
Incomplete import list in `backend/app/api/v1/patient_portal/appointments.py`, undetected earlier because Python 3.14's PEP 649 lazy annotations defer `NameError`s that older Python versions would have raised immediately on `def` execution.

**Fix / PR**
`backend/app/api/v1/patient_portal/appointments.py` — added the missing import.

**Resolution date**
2026-07-28

---

### BUG-012: Partial unique index preventing double-booking was missing from the test database schema

- **Reported by:** Phase 19 agent, while investigating why the concurrency test's "loser" request wasn't getting the expected 409
- **Date reported:** 2026-07-28
- **Severity:** Medium
- **Status:** Fixed
- **Area:** backend, db

**Description**
`uq_appointments_doctor_slot_active` (the partial unique index preventing exact double-booking, added in migration 0012) was created only via raw SQL inside that migration's `upgrade()`, never expressed in `Appointment.__table_args__`. `app/tests/conftest.py`'s `engine` fixture builds the entire test-database schema via `Base.metadata.create_all()`, which only knows about SQLAlchemy-declared constraints/indexes — it never runs Alembic migrations. This meant the test database has been missing this constraint since Phase 11 shipped, and any test asserting on the double-booking guarantee (this phase's concurrency test included, before this fix) was silently running against a schema that didn't actually have it — the app-level `has_conflicting_booking` pre-check was doing all the work in tests, not the DB.

**Steps to reproduce**
1. Query `pg_indexes` for `uq_appointments_doctor_slot_active` against a freshly-`create_all()`'d test database.
2. Observe zero rows, versus one row against a database built via `alembic upgrade head`.

**Expected behavior**
The test schema should include every real production constraint, especially one a concurrency test is specifically asserting against.

**Actual behavior**
Confirmed and fixed: added an equivalent `Index(..., unique=True, postgresql_where=...)` to `Appointment.__table_args__` (same name, so it's a no-op against an already-migrated dev/prod database, and additive for `create_all()`-built test databases). Re-verified via `pg_indexes` in the test DB and by re-running the concurrency test, which now genuinely exercises the Postgres-level guarantee (confirmed by inspecting the actual `IntegrityError` raised, which references `uq_appointments_doctor_slot_active` by name).

**Root cause**
Postgres partial-index `WHERE` clauses aren't expressible via plain `UniqueConstraint`, so the original Phase 11 implementation reasonably used raw `op.execute()` in the migration — but never mirrored that same index declaratively in the model for `create_all()`-based schemas (a gap that predates this phase and evidently was never caught because no earlier phase wrote a genuine concurrent-request test against it).

**Fix / PR**
`backend/app/models/appointment.py` — added the declarative partial `Index` to `__table_args__`.

**Resolution date**
2026-07-28

---

### BUG-013: Appointment number counter's first-of-day INSERT isn't concurrency-safe

- **Reported by:** Phase 19 agent, via the concurrent-booking test (after fixing BUG-012 above, the test then failed a second way)
- **Date reported:** 2026-07-28
- **Severity:** Medium
- **Status:** Fixed (patient-facing paths only)
- **Area:** backend

**Description**
`_DailyNumberGenerator._get_or_create_counter` (`backend/app/services/clinical_number_generator.py`, Phase 9, shared by Appointment/Order/Prescription number generators) locks its `system_settings` counter row with `SELECT ... FOR UPDATE` before incrementing it — but that only protects concurrent *updates* of an *existing* row. The very first booking of a given day for a clinic has no row yet, so two simultaneous first-bookings both attempt to `INSERT` the initial counter row, and the loser hits `uq_system_setting_clinic_key`, raising an uncaught `IntegrityError` (translated to a raw `500`, not the intended clean `409`) instead of the appointment-table race being what's exercised.

**Steps to reproduce**
1. Ensure no `system_settings` row exists yet for `appointment_number_counter_<date>` in a given clinic.
2. Fire two concurrent `AppointmentService.create_patient_appointment` calls for the same doctor/date/time (or even different times — any two concurrent *first* bookings of the day race on this).
3. Observe one succeeds, the other raises `IntegrityError` on `system_settings`, not on `appointments`.

**Expected behavior**
Exactly one request succeeds, the other gets a clean `409`, regardless of which specific constraint it lost to.

**Actual behavior**
Confirmed and fixed for the patient-facing create/reschedule paths: widened the existing `try/except IntegrityError` block in `_create_appointment_impl`/`reschedule_patient_appointment` to also wrap `AppointmentNumberGenerator.next_number()`, so this race now correctly surfaces as `409` too. Re-ran the concurrency test 6 times consecutively after the fix — all passed, asserting exactly one success and one `409`, and that exactly one `appointments` row exists for the contested slot.

**Root cause**
`_DailyNumberGenerator`'s lock-based concurrency safety (Phase 9) only covers the UPDATE path, not the counter row's own first-time INSERT — a known class of "SELECT-then-INSERT" race that `SELECT ... FOR UPDATE` alone cannot prevent (there's no row to lock yet). This is shared infrastructure also used by Orders/Prescriptions, not touched directly.

**Fix / PR**
`backend/app/services/appointment_service.py` — moved `generator.next_number(...)` inside the same `try/except IntegrityError` as the appointment INSERT, for both the create and patient-reschedule paths. The staff-facing `reschedule_appointment` has the identical gap and was NOT fixed (see BUG-009). The shared `_DailyNumberGenerator` itself was intentionally left unchanged (used by Orders/Prescriptions too; a real fix there — e.g. `INSERT ... ON CONFLICT DO NOTHING` then re-select — is a separate, cross-cutting change out of this phase's scope).

**Resolution date**
2026-07-28

---

### BUG-014: `npm run build` fails on pre-existing Phase 18 ESLint errors

- **Reported by:** Phase 19 agent, running `npm run build` as a stronger check than `npx tsc --noEmit` alone
- **Date reported:** 2026-07-28
- **Severity:** Low
- **Status:** Open
- **Area:** frontend

**Description**
`npm run build` (`next build`) fails ESLint's `react/no-unescaped-entities` rule on two files this phase did not touch: `frontend/src/app/patient-portal/billing/page.tsx:59` and `frontend/src/app/patient-portal/login/page.tsx:59` (both a literal `'` that needs `&apos;`/`&rsquo;`). `npx tsc --noEmit` (a pure type check, no lint) passes cleanly for the whole project, and `npx eslint` against this phase's own new/changed files (`appointments/book/page.tsx`, `appointments/page.tsx`, `dashboard/page.tsx`, `features/patient-portal/api/appointments.ts`) is clean.

**Steps to reproduce**
1. `cd frontend && npm run build`.
2. Observe `Failed to compile` after two `react/no-unescaped-entities` errors.

**Expected behavior**
`npm run build` should succeed in CI/production.

**Actual behavior**
Confirmed: build fails on these two pre-existing files; this phase's own code compiles and lints clean in isolation.

**Root cause**
Pre-existing Phase 18 code with a literal apostrophe in JSX text, never caught because Phase 18's own verification apparently used `tsc --noEmit` rather than a full `next build`.

**Fix / PR**
`frontend/src/app/patient-portal/billing/page.tsx` and `frontend/src/app/patient-portal/login/page.tsx` — both literal apostrophes replaced with `&apos;`. Verified: `npm run build` re-run and completed cleanly (45 routes generated, no errors).

**Resolution date**
2026-07-28

---

### BUG-015: Browser reported `Error: [object Event]` (Next.js unhandled rejection overlay) — investigated, closed as dev-environment-only

- **Reported by:** User, live browser session
- **Date reported:** 2026-07-28
- **Severity:** Low
- **Status:** Closed (not reproduced as an application defect)
- **Area:** frontend

**Description**
The browser surfaced `Error: [object Event]` via Next.js's `createUnhandledError`/`onUnhandledRejection` dev overlay. Investigated per explicit instruction: search all `fetch`/`axios`/`EventSource`/`WebSocket`/`addEventListener("error")` usages, add logging if needed, and replace any generic Event rejections with proper `Error` objects — or confirm no such code path exists.

**Steps to reproduce**
Not independently reproducible on demand. Occurred during a session where two background agents (Phase 19 build, full-system QA audit) were concurrently editing frontend files and repeatedly restarting/rebuilding the dev server.

**Expected behavior**
Any rejected Promise reaching the browser should carry a real `Error` with a useful message, not a raw DOM `Event`.

**Actual behavior**
A live reproduction attempt during investigation surfaced a related but distinct and correctly-handled case: the backend was down (`net::ERR_CONNECTION_REFUSED`, likely killed by a concurrent background agent), which the patient-portal API client correctly wrapped as a readable `"Failed to fetch"` `PatientApiError` — not `[object Event]`. Separately, running `npm run build` (which shares the `.next` directory with the running `next dev` process) left that dev server serving a corrupted, inconsistent webpack module graph — confirmed via real server-log errors (`Cannot find module './7627.js'`, `TypeError: __webpack_modules__[moduleId] is not a function`, `ENOENT ... vendor-chunks/clsx.js`) that only cleared after fully killing and restarting the dev server process; clearing `.next` on disk alone was not sufficient, since the running Node process held stale in-memory module references.

**Root cause**
No application code was found responsible. Grepped all of `frontend/src` for `fetch(`, `EventSource`, `WebSocket`, `addEventListener("error", ...)`, `.onerror =`, `.onload =`, `new Promise(`, and `Promise.reject(`. The only `WebSocket.onerror` handlers found (`features/tv-display/hooks/use-tv-display-realtime.ts:93`, `features/queue/hooks/use-queues.ts`) just close the socket or no-op — neither rejects a Promise with the event. The most probable actual source is Next.js/webpack's own internal dynamic-chunk-loading machinery (framework-generated `webpack-runtime.js`, not application source), which is known to reject with a raw `Event` from a failed `<script>` load when a dev-mode rebuild invalidates in-flight chunk requests — directly corroborated by the concurrent `next dev`/`next build` corruption observed later the same session.

**Fix / PR**
No code changed — there is nothing in application source to fix. `npm run build` and `npm run start` were both verified clean (no console errors, no network failures) as a control, confirming this does not reproduce under a real production build.

**Resolution date**
2026-07-28 (closed as a development-only incident; see `docs/TESTING.md`'s "Incident: browser-reported `[object Event]`" section for full detail — reopen and update both if ever reproduced against a clean production deployment).

---

### BUG-016: No dedicated clinic-side Audit Log list/filter page or endpoint for Owner/Administrator

- **Reported by:** End-to-end clinic workflow validation pass
- **Date reported:** 2026-07-28
- **Severity:** Low
- **Status:** Open
- **Area:** backend/frontend
- **Environment:** local

**Description**
The task's Administrator workflow requires being able to "view the audit log list, confirm it actually contains real entries." There is no `GET /api/v1/audit-logs` (or equivalent) endpoint scoped to a clinic's own Owner/Administrator role, and no dedicated Audit Log list page in the frontend. The only structured `audit-logs` API in the whole system is `GET /api/v1/platform-admin/audit-logs`, which belongs to the entirely separate SaaS Administration Portal (Phase 15) — a platform-operator surface, not something a clinic's own Owner account can reach (confirmed: a clinic-staff `access` token is rejected by platform-admin routes, per Phase 15/18's token-isolation design). Individual entity pages (Patient profile, Consultation page) each have their own "Audit Log"/"Timeline" tab, but those read the entity's own timeline/history, not a clinic-wide `audit_logs` query.

**Steps to reproduce**
1. Log in as `owner@connectph.dev` (Owner role).
2. Look for a way to view the raw `audit_logs` table contents for the clinic — no sidebar entry, no route, and `curl .../api/v1/audit-logs` (guessed) returns `404`; `openapi.json` confirms no such path exists.
3. The closest available substitute is the Owner Dashboard's "Real-time Activity Feed", which does correctly display live `audit_logs`-backed entries (confirmed during this pass — every action performed showed up there, in order, with a human-readable label) but offers no date-range filter, entity-type filter, user filter, or pagination beyond what fits in the feed.

**Expected behavior**
Either a clinic-scoped `GET /api/v1/audit-logs` (or similar) endpoint plus a proper searchable/filterable/paginated Audit Log page, matching the level of detail the raw `audit_logs` table actually contains (clinic_id/user_id/action/entity_type/entity_id/metadata/created_at).

**Actual behavior**
No such endpoint or page exists. The Real-time Activity Feed is a reasonable stopgap for casual visibility but isn't a substitute for compliance-grade audit review (can't search, filter by user/date, or export).

**Root cause**
Never built — the Real-time Activity Feed (part of the Owner Dashboard/Analytics module) was apparently judged sufficient at implementation time, and a dedicated audit-log viewer was never separately scoped.

**Fix / PR**
Not fixed this pass — building a new endpoint plus a new frontend page is feature work, out of scope for a verification pass that is limited to fixing only Critical/High bugs. Logged for a future phase to pick up.

**Resolution date**
(open)

---

### BUG-017: Sidebar nav is not role-filtered for most items

- **Reported by:** Test Account Inventory / UAT login-matrix pass (live browser verification, logged in as a real Cashier account)
- **Date reported:** 2026-07-28
- **Severity:** Medium
- **Status:** Open
- **Area:** frontend

**Description**
`frontend/src/components/layout/Sidebar.tsx` only role-gates three nav destinations (`canSeeAnalytics`, `canSeeTvDisplays`, `canSeeMigration`, all keyed off the same `ANALYTICS_ROLES` set). Every other sidebar link — Users, the entire "Clinic Configuration" section (Clinic Settings, Branches, Departments, Doctors, Doctor Schedules, Consultation Rooms, Services, Queue Settings, Operating Hours, Holidays, Laboratory Templates), Doctor Workspace, Laboratory, Billing — is rendered unconditionally for every logged-in role, regardless of whether that role can actually use the destination page.

**Steps to reproduce**
1. Log in as a Cashier-role account (e.g. `uat.cashier@connectph.dev`).
2. Observe the sidebar: "Users" and the full "Clinic Configuration" section (Branches, Departments, Doctors, etc.) are visible and clickable, despite the Cashier role having no legitimate access to user management or clinic configuration.

**Expected behavior**
A role should only see sidebar links to pages/actions it can actually perform, per the explicit UAT requirement to verify "each account sees only the menus and permissions appropriate for its role."

**Actual behavior**
Every role sees the full staff nav menu (minus the three already-gated items). Clicking an inaccessible link does not expose any data — the backend correctly returns `403` (independently verified live this pass: a Cashier token got `403` on `POST /users` and `GET /analytics/dashboard`) — so this is a UX/navigation gap, not a security/data-isolation defect.

**Root cause**
`Sidebar.tsx` was written with role-gating only for the three items called out above; the rest of the nav array has no `roles`/visibility field checked against `currentUser.role` at all.

**Fix / PR**
Not fixed this pass, per this task's explicit instruction to fix only Critical/High severity bugs — this is Medium (a real gap, but with no workaround-free broken workflow: the backend's own permission checks are the actual security boundary, and are correct). Recommended fix for a future pass: extend the existing `ANALYTICS_ROLES`-style gating pattern to every nav item, driven by each role's real permitted routes (the same set the backend already enforces per-endpoint), so the two never drift apart again.

**Resolution date**
(open)

---

### BUG-018: Receptionist gets 403 on "Apply Discount" and "Record Payment" (Phase 20, items 1 & 2)

- **Reported by:** Client UAT / Phase 20 Client Acceptance Revisions
- **Date reported:** 2026-07-28
- **Severity:** Critical (live bug blocking billing operations)
- **Status:** Fixed
- **Area:** backend (`backend/app/core/dependencies.py`, `backend/app/api/v1/billing.py`)

**Description**
Receptionist-role users received a 403 "You do not have permission to perform this action." error when attempting to apply a discount (`POST /invoices/{invoice_id}/discounts`) or record a payment (`POST /invoices/{invoice_id}/payments`) from the Billing invoice detail screen.

**Steps to reproduce (verified live)**
1. Logged in as `uat.reception@connectph.dev` (Receptionist role) against the running dev backend.
2. Called `POST /api/v1/invoices/{id}/discounts` and `POST /api/v1/invoices/{id}/payments` with a valid token.
3. Both returned `403 {"detail": "You do not have permission to perform this action."}`.

**Root cause**
Both endpoints were gated by `require_billing_manage_role`, backed by `BILLING_MANAGE_ROLES = {"Owner", "Administrator", "Cashier"}` (Phase 9's original spec: "Reception: Read-only" for Billing). Receptionist was never in that set, so every discount/payment attempt 403'd regardless of invoice state — this was a role-permission gap, not a data or logic bug. Per this client revision (Phase 20, item 1/2), Receptionist should now be able to perform these two actions, so the fix is the deliberate permission change described below, not a "restore prior behavior" fix.

**Fix / PR**
Split `BILLING_MANAGE_ROLES` into narrower dependencies in `backend/app/core/dependencies.py`:
- `require_billing_discount_role` (`BILLING_DISCOUNT_ROLES` = Owner/Administrator/Cashier/**Receptionist**) now gates `POST /invoices/{invoice_id}/discounts`.
- `require_billing_payment_record_role` (`BILLING_PAYMENT_RECORD_ROLES` = Owner/Administrator/Cashier/**Receptionist**) now gates `POST /invoices/{invoice_id}/payments`.
- `require_billing_void_role` (`BILLING_VOID_ROLES` = Owner/Administrator/Cashier, unchanged — Receptionist intentionally excluded) now gates `POST /payments/{payment_id}/void`, so voiding a payment is still restricted.
- Refund approval (`require_billing_refund_role`) is untouched (Administrator/Owner only).

Verified live: Receptionist token now gets past the role gate on discounts/payments (422 on a malformed body, and a legitimate business-rule 400 "Cannot edit invoice items once the invoice is Paid" on a real Paid invoice — i.e., it reaches the service layer instead of 403ing at the dependency), while still getting `403` on `POST /payments/{id}/void`.

**Resolution date**
2026-07-28

---

### BUG-019: "Remove Discount" had no backend implementation at all

- **Reported by:** Independent verification during Round 2 (Client Acceptance Revisions) — a background agent claimed items 2/3 (the discount RBAC reversal) were "code-complete, no endpoint or service code changes needed," but this was checked and found incorrect for the removal half specifically.
- **Date reported:** 2026-07-28
- **Severity:** High
- **Status:** Fixed
- **Area:** backend/frontend

**Description**
Round 2's item 3 explicitly lists both "Apply Discount" and "Remove Discount" as capabilities a Doctor should have. "Apply Discount" already existed (`POST /invoices/{invoice_id}/discounts`, from Phase 10). "Remove Discount" did not exist anywhere in the codebase — no repository method, no service method, no API route, confirmed by grepping for `remove_discount`/`delete_discount`/`void_discount` and any `DELETE` route under `/invoices/.../discounts` across the entire `backend/app/` tree, finding nothing.

**Steps to reproduce**
1. Apply a discount to an invoice as a Doctor (works).
2. Attempt to remove that discount — no endpoint exists to call.

**Expected behavior**
A Doctor (per the RBAC reversal in the same round) should be able to remove a previously-applied discount, with the invoice's `grand_total`/`balance_due`/`discount_total` recalculating correctly and an audit log entry recorded.

**Actual behavior**
No such capability existed prior to this fix.

**Root cause**
Never built. Phase 10 (original Billing & Cashier phase) only implemented discount *application*, not removal, and no subsequent phase added it until this round explicitly called for it.

**Fix / PR**
- `backend/app/repositories/invoice_repository.py` — added `get_discount(discount_id, invoice_id, clinic_id)` and `delete_discount(discount)`, following the exact pattern already used for `get_item`/`delete_item`.
- `backend/app/services/invoice_service.py` — added `remove_discount()`: looks up the discount scoped to clinic+invoice (404 if not found), deletes it, refreshes and recomputes invoice totals, writes an `invoice.discount_removed` audit log entry with `actor_id`, commits.
- `backend/app/api/v1/billing.py` — added `DELETE /invoices/{invoice_id}/discounts/{discount_id}`, gated by the same `require_billing_discount_role` dependency used for applying discounts (so the RBAC reversal in items 2/3 covers both apply and remove with one role-set edit).
- Frontend: `billingApi.removeDiscount()`, `useRemoveDiscount()` hook, and a "Remove" button per discount row on the Invoice Detail page (`frontend/src/app/(dashboard)/billing/[id]/page.tsx`), only shown while the invoice is in an editable status — mirrors the existing line-item Remove button's pattern exactly.

**Verified live**: applied a discount as Doctor (invoice `grand_total` 300→265 with two discounts active), then removed one via `DELETE` as Doctor — `grand_total` correctly recalculated back to 290, remaining discount unaffected. Receptionist and Cashier both confirmed `403` on the removal endpoint. `audit_logs` confirmed both `invoice.discount_applied` and `invoice.discount_removed` rows exist, attributed to the Doctor's `user_id`. Also verified live in the browser: logged in as Doctor, clicked "Remove" on a discount row, watched the totals update in real time without a page reload (TanStack Query cache sync via the existing `useSyncInvoiceCache` pattern).

**Resolution date**
2026-07-28

---

### BUG-021: Closing/reopening a Shift 500'd (`MissingGreenlet`) after the ORM's `updated_at` column expired post-UPDATE

- **Reported by:** Self-caught during this phase's own live verification pass (Phase 21: Receptionist Shift Management), before the feature shipped. (Numbered BUG-021, not BUG-020 — BUG-020 was already claimed by a concurrently-running agent's TV Queue Display fix.)
- **Date reported:** 2026-07-29
- **Severity:** High (would have blocked the core close/reopen flow entirely)
- **Status:** Fixed
- **Area:** backend

**Description**
`POST /shifts/{id}/close` and `POST /shifts/{id}/reopen` both returned a generic `500 Internal server error` the first time they were exercised live.

**Steps to reproduce**
1. Start a shift, record a payment against it.
2. Call `POST /shifts/{id}/close` with an `actual_cash_count`.

**Expected behavior**
`200` with the closed shift's full detail (summary, expected/actual cash, variance).

**Actual behavior**
`500`, logged server-side as `sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called; can't call await_only() here.`

**Root cause**
`ShiftService.close_shift`/`reopen_shift` mutate the ORM row then `await self.session.flush()`. Because `Shift.updated_at` has `onupdate=func.now()` (a DB-side trigger, not a Python-computed value), SQLAlchemy marks that column **expired** after the `UPDATE` - the ORM doesn't know the new value without a round-trip. The very next line built a Pydantic response by reading `shift.updated_at` in a plain (non-awaited) attribute access inside `ShiftRead(...)`'s constructor call. Triggering an implicit lazy-refresh from a synchronous attribute-get, outside of an `await`ed expression, isn't valid under SQLAlchemy's async/greenlet model - hence `MissingGreenlet`.

**Fix / PR**
`backend/app/services/shift_service.py` - added `await self.session.refresh(shift)` immediately after `await self.session.flush()` in both `close_shift` and `reopen_shift`, so the expired `updated_at` (and any other server-generated column) is reloaded inside an awaited call before the row is read synchronously for serialization.

**Verified live**: re-ran the full open → pay → close → reopen → close chain via both direct API calls and the browser UI after the fix; all steps returned `200`/correct data, no further `500`s. See `docs/TESTING.md`'s Phase 21 section for the full verification trace.

**Resolution date**
2026-07-29

---

### BUG-022: TV Queue Display doesn't repeat the TTS announcement on Recall of an already-serving ticket

- **Reported by:** Independent verification of the "Configurable Queue Announcement" / audible calling feature; re-confirmed live and fixed during the RC1 full clinic-journey UAT pass (2026-08-06)
- **Date reported:** 2026-07-29
- **Severity:** High (upgraded from Medium during the RC1 UAT pass — see rationale below)
- **Status:** Fixed
- **Area:** backend/frontend

**Description**
The spec requires: "When RECALL is pressed: Repeat the latest announcement." The Doctor Workspace/Reception Queue side of this is correct — `useCallPatient`/`useRecallPatient` (`frontend/src/features/doctor-workspace/hooks/use-doctor-actions.ts`) call `announceQueueNumber(data.queue_number)` unconditionally in the mutation's own `onSuccess`, so whoever presses Call or Recall always hears the announcement on their own device. However, the **TV Queue Display** (`frontend/src/app/tv/[slug]/page.tsx`) — the shared public screen in the waiting room, which is the surface patients actually rely on to hear their number — only announced a queue entry the *first* time its `queueId` appeared in the realtime "Now Serving" data (`prevCalledIdsRef`, a seen-ids set). Recalling a ticket that is already in "Now Serving" did not add a new id to that set, so the TV Display's own speaker never repeated the announcement, even though the underlying queue/visit event fired correctly and the calling staff member's own device did announce it.

**Steps to reproduce**
1. Open the TV Display (`/tv/{slug}`) in a browser tab, click "Enable Sound."
2. As a Doctor, Call a Waiting patient — TV Display correctly announces it (new entry).
3. As the same Doctor, Recall that same now-"Called" patient again.
4. The TV Display does not announce anything a second time (confirmed via instrumenting `speechSynthesis.speak`/`cancel` — zero additional calls recorded after the recall, despite the underlying `visit.recalled`-equivalent event reaching the display's realtime feed).

**Expected behavior**
A Recall should re-trigger the TTS announcement on the TV Display, not just on the calling staff member's own device — the waiting room is the actual intended audience for a repeated announcement (e.g. a patient who didn't hear it the first time).

**Actual behavior (before fix)**
Silent no-op on the TV Display for a recall of an already-"Now Serving" ticket.

**Root cause**
Two layers, both required for a real fix:
1. **Backend**: `DoctorWorkspaceService.recall_patient()` (`backend/app/services/doctor_workspace_service.py`) never refreshed `Queue.called_at` — it only logged activity/audit and broadcast a `visit.called` WS event with `recall: true`, without updating any queryable field. So even a consumer that *did* diff on the right field would see identical data before and after a recall.
2. **Frontend**: `prevCalledIdsRef` in `TvDisplayScreen.tsx` (the file actually used by both `/tv` and `/tv/[slug]`, per its own module docstring — not `tv/[slug]/page.tsx` itself, which is now just a thin slug-resolving wrapper) only detected entries new to the "Now Serving" set by id; a recall doesn't remove-then-re-add the id, so the "is this new?" check never fired again for it even in principle.

**Fix / PR**
- `backend/app/services/doctor_workspace_service.py` (`recall_patient`): now looks up the visit's linked `Queue` row and stamps `called_at = datetime.now(UTC)` directly (bypassing the stricter status-transition machinery, since the status itself isn't changing on a recall — only the timestamp needs to move).
- `frontend/src/features/tv-display/components/TvDisplayScreen.tsx`: replaced the id-only `prevCalledIdsRef: Set<string>` with `prevCalledAtRef: Map<string, string | null>` (id → last-seen `calledAt`), and the "is this new?" check now also fires when a known id's `calledAt` has changed, not just when the id itself is new.

**Verified live**: reproduced the original bug first (confirmed zero additional `speechSynthesis.speak` calls after a Recall, via a real browser tab with `speechSynthesis.speak` instrumented and the public `/tv/{slug}` page genuinely rendering "Now Serving"/"Next in Queue" from live data). After the backend fix, confirmed via direct API re-check (`GET /tv-displays/{id}/preview`) that `called_at` for the recalled ticket visibly advances on every Recall (e.g. `01:34:48Z` → `01:39:29Z` → `01:45:16Z` across three separate recalls of the same ticket). The very first live re-check after editing `doctor_workspace_service.py` still showed no timestamp change — a recurrence of this environment's documented "zombie backend" issue (the file-watcher reloaded `consultations.py` for a sibling fix in the same session but silently missed this file); restarting the backend process fresh (per the standard documented workaround) made the fix take effect immediately, confirmed by the timestamp advancing on the next recall. `backend: python -c "import app.main"` and `frontend: npx tsc --noEmit` both clean after the change.

**Why the severity was upgraded from Medium to High during this UAT pass**: recall's entire practical purpose in a live clinic is audibly re-paging a patient in the waiting room who missed the first call (that's the whole reason a receptionist/doctor would press "Recall" instead of just re-reading the still-correct on-screen number). A Recall that updates the screen correctly but never makes a sound defeats the feature for its primary real-world use case, which the task's UAT checklist explicitly named as a checkpoint — this is a core clinic workflow gap, not a cosmetic one.

**Resolution date**
2026-08-06

### BUG-023: Bare `/tv` route has no way to resolve a clinic's default display without an env var (no DB-level default concept exists)

- **Reported by:** Self-found during the bare `/tv` route implementation
- **Date reported:** 2026-07-29
- **Severity:** Low
- **Status:** Open
- **Area:** backend/frontend

**Description**
The new zero-configuration `/tv` route (see `docs/FEATURES.md` and `docs/TESTING.md`'s 2026-07-29 section) resolves which display to show via `NEXT_PUBLIC_DEFAULT_TV_SLUG`, an env var — this fully covers the "single clinic, single on-prem TV" deployment case the round asked for. What it does *not* cover: a shared multi-tenant deployment where a clinic wants `/tv` (no slug) to resolve to "whichever display this clinic marked as its default" without setting a frontend build-time env var per clinic. That would require (a) an `is_default`/`is_primary` boolean on `tv_display_configs` (none exists today — confirmed in `backend/app/models/tv_display_config.py`), and (b) a new public endpoint to resolve "the" default display for a clinic without any clinic-identifying parameter in the URL (the existing public endpoint deliberately takes only an unguessable `public_slug`, by design, for its no-auth security model — see `backend/app/api/v1/tv_display.py`'s module docstring), which would need its own anti-enumeration protection design before it could safely ship.

**Steps to reproduce**
1. Deploy the frontend without setting `NEXT_PUBLIC_DEFAULT_TV_SLUG`.
2. Open `/tv`.
3. Falls through to the "No display configured" message — correct/non-crashing, but there is no automatic way for a clinic operator to make `/tv` "just work" without manually setting that env var and rebuilding/redeploying the frontend.

**Expected behavior**
n/a — this is a scope/follow-up note, not a regression. Filed so a future round has the concrete design questions above (schema addition + endpoint anti-enumeration approach) already scoped rather than rediscovering them.

**Actual behavior**
`/tv` only resolves via the build-time env var; no DB-driven per-clinic default exists.

**Root cause**
No `is_default`/`is_primary` column or public "resolve my clinic's default display" endpoint exists yet; adding one was judged out of scope for this round per the task's own "check first whether something already covers this before adding new schema" guidance, since the env var path alone satisfies the stated on-prem single-TV requirement.

**Fix / PR**
Not fixed — intentionally deferred, see Description.

**Resolution date**
n/a

### BUG-024: "Could not open this visit's consultation" shown for any failure when a Receptionist enters vitals, hiding the real cause (unassigned-doctor queue tickets)

- **Reported by:** Client Acceptance Revisions — Round 3, item 4
- **Date reported:** 2026-07-29
- **Severity:** Medium
- **Status:** Fixed
- **Area:** frontend/backend

**Description**
`ReceptionVitalsDialog` (`frontend/src/features/consultation/components/ReceptionVitalsDialog.tsx`) called `consultationApi.openForReception(visitId)` and, on *any* rejected promise, set the same hardcoded string: "Could not open this visit's consultation." This swallowed the real backend error, including a legitimate, reachable 400 from `ConsultationService.open_consultation_for_reception` (`backend/app/services/consultation_service.py`) when the visit's queue ticket has no doctor assigned — the New Queue Ticket dialog explicitly allows "Any / unassigned" as a Doctor selection, and `Consultation.doctor_id` is a NOT NULL FK (`backend/app/models/consultation.py`), so a consultation genuinely cannot be opened until a doctor is assigned. Receptionists hit this on any walk-in queued without picking a doctor and got no indication of why or what to do about it.

**Steps to reproduce**
1. Log in as Receptionist.
2. Create a New Queue Ticket, leaving Doctor as "Any / unassigned".
3. On the Reception Queue, click "Enter Vitals" for that ticket.
4. Dialog shows: "Could not open this visit's consultation." — no indication a doctor needs to be assigned.

**Expected behavior**
The error message should say what's actually wrong and what to do, and only fire for this specific unassigned-doctor case — a queue ticket with a doctor already assigned should always let the Receptionist open the vitals dialog and save, with no error.

**Actual behavior (before fix)**
Every failure path (network error, unassigned doctor, anything else) rendered the exact same generic string.

**Root cause**
1. `ReceptionVitalsDialog`'s `.catch()` discarded the actual error and its message.
2. `open_consultation_for_reception`'s 400 detail ("Visit has no assigned doctor.") was correct but not actionable/specific enough once surfaced.

**Fix / PR**
- `frontend/src/features/consultation/components/ReceptionVitalsDialog.tsx`: now surfaces `err.message` from `ApiError` (`frontend/src/lib/api-client.ts` already maps FastAPI's `{"detail": "..."}` shape onto `ApiError.message`) instead of a hardcoded string, falling back to the generic message only when there's no `ApiError` detail to show.
- `backend/app/services/consultation_service.py::open_consultation_for_reception`: reworded the 400 detail to "This visit has no doctor assigned yet. Assign a doctor to the queue ticket before entering vitals."

**Verification (live, 2026-07-29)**
Logged in as Receptionist. Created ticket A007 (Juan Dela Cruz) with Doctor left "Any / unassigned" — reproduced the original generic error live, then confirmed post-fix it now reads "This visit has no doctor assigned yet. Assign a doctor to the queue ticket before entering vitals." Confirmed ticket A006 (Doctor: Maria Santos, already assigned) opens the vitals dialog with no error and successfully saves ("Saved." shown). Confirmed the dialog only ever exposes Chief Complaint + vitals fields (no Assessment/Plan) in both cases — the existing Receptionist/Doctor SOAP boundary from an earlier round is unweakened by this fix.

**Resolution date**
2026-07-29

### BUG-025: Daily queue-number ceiling (`QueueSetting.max_daily_queue`, default 200) was never enforced

- **Reported by:** Client Acceptance Revisions — Round 3, item 13
- **Date reported:** 2026-07-29
- **Severity:** Low
- **Status:** Fixed
- **Area:** backend

**Description**
Investigating item 13 ("unique daily queue numbers per prefix, up to 200, reset daily") found that per-prefix, per-day, sequential numbering already existed and was already correct (`QueueCounter` keyed on `(clinic_id, branch_id, queue_prefix, counter_date)`, `SELECT ... FOR UPDATE`-locked in `QueueNumberGenerator._get_or_create_counter`, `backend/app/services/queue_number_generator.py`), and `QueueSetting.max_daily_queue` (default 200, `backend/app/models/queue_setting.py`) already existed as a configured ceiling — but nothing ever read `max_daily_queue` or stopped `next_number()` from incrementing past it. A 201st ticket for the same prefix/day would have silently been issued as `A201` instead of being rejected.

**Steps to reproduce (pre-fix, by code inspection — not exercised to 200 live due to time)**
1. Create 200 queue tickets for the same clinic/branch/prefix on the same day.
2. Create a 201st.
3. Pre-fix: `A201` would be created with no error. Post-fix: expected 409 Conflict.

**Expected behavior**
The 201st ticket for a given (clinic, branch, prefix, day) should be rejected with a clear error, never silently created or wrapped/reused.

**Root cause**
`QueueNumberGenerator.next_number()` had no ceiling parameter and no check against `max_daily_queue` at all.

**Fix / PR**
- `backend/app/services/queue_number_generator.py::next_number`: added a `max_daily_queue` parameter (default 200); raises `HTTPException(409, ...)` with a clear message identifying the prefix and limit instead of continuing to increment.
- `backend/app/services/queue_service.py`: added `_resolve_max_daily_queue()` (mirrors the existing `_resolve_prefix()` department/branch/clinic-default resolution via `QueueSettingRepository.get_effective_for_department`) and wired it into `create_queue()`.

**Verification**
Backend `python -c "import app.main"` and frontend `npx tsc --noEmit` both pass clean after the change. **Not yet verified live**: did not create 200+ tickets against the running dev backend to confirm the 409 actually fires at #201 and that #1-200 are unaffected — flagged here so a follow-up pass can close the loop with a real load test.

**Resolution date**
2026-07-29 (code fix landed; live volume test still outstanding)

---

### BUG-033: Clinic-wide `QueueSetting` row can never actually be selected because it's saved with `branch_id = null`, which never matches a real ticket's `branch_id`

- **Reported by:** self-discovered while implementing Post-RC1 Multi-Department/Multi-Doctor TV Queue Display
- **Date reported:** 2026-08-09
- **Severity:** High
- **Status:** Open
- **Area:** backend

**Description**
`QueueSettingRepository.get_for_branch(clinic_id, branch_id, department_id, doctor_id)` filters on an EXACT match of all four columns, including `branch_id`. `Queue.branch_id` is a required, never-null column (see `models/queue.py`) - every real queue-creation call passes `payload.branch_id` as a real UUID, never `None`. But the existing "clinic-wide queue configuration" form on `/queue-settings` (`frontend/src/app/(dashboard)/queue-settings/page.tsx`) always submits `branch_id: null`. That means the saved row can only ever be found by a resolve call that itself passes `branch_id=None` - which never happens for a real ticket. `QueueService._resolve_prefix`/`_resolve_max_daily_queue` therefore always fall through to the hardcoded `DEFAULT_QUEUE_PREFIX = "A"` / `200` default instead of whatever the clinic actually configured on that page.

**Why this went unnoticed:** most clinics' desired clinic-wide prefix is "A" anyway (the same as the hardcoded fallback), so behavior looks correct by coincidence. A clinic that changed the prefix or the max-daily-queue ceiling via this page would silently see zero effect on real tickets - the change would appear to save successfully (200 OK, row visible in `GET /queue-settings`) but never influence numbering.

**How it was found:** while building this session's per-doctor/per-department prefix overrides, a first attempt at a test created an override row with `branch_id=null` and it never resolved for a real queue ticket - tracing `get_effective_for_doctor` -> `get_for_branch` showed the exact-match requirement, which then also applies to the pre-existing, already-shipped clinic-wide form. Confirmed by inspection of both the resolution chain and the frontend form's submitted payload; not separately reproduced against a live clinic-wide "change the prefix to something other than A" scenario (out of scope for this session - this is a pre-existing, unrelated defect logged here per this session's "don't fix unrelated bugs inline" instruction).

**Expected behavior**
Either the clinic-wide form should submit the clinic's actual (single, or currently-selected) branch id, or `get_for_branch`'s branch matching should treat a `NULL` stored `branch_id` as "any branch" (mirroring how `department_id`/`doctor_id` already work as "no override" sentinels) rather than as its own exact-match scope.

**Suggested fix (not applied here)**
Either (a) have the frontend form select/require a branch like this session's new per-department/per-doctor override form now does, or (b) change `get_for_branch`'s resolution to widen a `branch_id=NULL` row to "clinic default, any branch" - the latter is a more invasive query-semantics change (affects the existing partial-branch-scoping feature) and needs its own design pass, not a quick fix bundled into this feature's diff.

**Resolution date**
Not yet resolved.

---


### BUG-030: Doctor's Assessment/Plan save (`PUT /consultations/{id}/soap`) silently destroyed the patient's recorded vitals and chief complaint

- **Reported by:** Full end-to-end clinic-journey UAT (RC1 sign-off pass)
- **Date reported:** 2026-08-06
- **Severity:** Critical
- **Status:** Fixed
- **Area:** backend

**Description**
Every real Doctor consultation flow saves vitals/subjective data via Reception's `PUT /consultations/{id}/soap/subjective-objective` first, then the Doctor separately saves Assessment/Plan via `PUT /consultations/{id}/soap` (the full-SOAP endpoint, gated to Doctor/Owner/Administrator). The Assessment/Plan UI has no reason to resubmit the vitals fields it never touched — but doing so silently erased them.

**Steps to reproduce**
1. As Reception, `PUT /consultations/{id}/soap/subjective-objective` with chief complaint + vitals (BP, pulse, temp, height, weight, etc.) — saved correctly.
2. As Doctor, `PUT /consultations/{id}/soap` with only Assessment/Plan fields (`clinical_impression`, `assessment_notes`, `treatment_plan`, `patient_instructions`) — `200 OK`.
3. `GET /consultations/{id}/soap` — every Subjective/Objective/vitals field (`chief_complaint`, `blood_pressure`, `pulse_rate`, `respiratory_rate`, `temperature`, `height_cm`, `weight_kg`, `oxygen_saturation`, `bmi`) is now `null`. Only the Assessment/Plan fields from step 2 survive.

**Expected behavior**
Saving Assessment/Plan should merge into the existing SOAP note, preserving whatever Subjective/Objective content already exists — exactly like the sibling `save_soap_subjective_objective` already correctly does in the other direction (its own docstring explicitly states this is "what keeps a Receptionist/Nurse call from ever being able to wipe a Doctor's Assessment/Plan entries").

**Actual behavior**
A full-record overwrite: any field not included in the specific `PUT /soap` request body was written back as `null`, regardless of what was previously saved.

**Root cause**
`backend/app/api/v1/consultations.py::save_soap` called `payload.model_dump()` with no `exclude_unset=True`, so every `SoapNoteUpsert` field the Doctor didn't set came through as an explicit `None` rather than being omitted. `ConsultationService.save_soap` then built its `fields` dict as `{k: payload.get(k) for k in SOAP_FIELDS}` — a blind full-field copy from that payload with zero merge against the existing row, unlike `save_soap_subjective_objective`, which explicitly starts from `existing` and only overlays fields present in the payload.

**Fix / PR**
- `backend/app/api/v1/consultations.py` (`save_soap`): `payload.model_dump(exclude_unset=True)`, matching the sibling endpoint.
- `backend/app/services/consultation_service.py` (`ConsultationService.save_soap`): now starts `fields` from the existing note's values (`getattr(existing, f)` per `SOAP_FIELDS`) and only overwrites keys actually present in `payload`, mirroring `save_soap_subjective_objective`'s merge pattern exactly.

**Verified live**: reproduced the data loss first (confirmed `blood_pressure`/`height_cm`/`weight_kg`/`chief_complaint`/etc. all went to `null` after a real Doctor Assessment/Plan save that never touched those fields). After the fix, restored vitals via Reception, had the Doctor save Assessment/Plan again with the identical minimal payload, and confirmed via `GET /consultations/{id}/soap` that every vitals/subjective field (including the derived `bmi`) survived unchanged while the new Assessment/Plan content was also present. (The very first live re-check after this edit still showed data loss — a recurrence of this environment's documented "zombie backend" issue, where the file-watcher's auto-reload silently missed `consultation_service.py`; restarting the backend process fresh made the fix take effect, confirmed by the same test passing cleanly afterward.) `backend: python -c "import app.main"` clean after the change.

**Resolution date**
2026-08-06

---

### BUG-028: Clinic Settings endpoints (`PATCH`/`DELETE /clinics/{clinic_id}`) had no role restriction — any authenticated staff role could rename or soft-delete the clinic

- **Reported by:** Admin/Owner UAT pass (RBAC spot-check, item 7), v1.7.0-rc1 feature-freeze verification
- **Date reported:** 2026-08-06
- **Severity:** Critical
- **Status:** Fixed
- **Area:** backend

**Description**
`backend/app/api/v1/clinics.py`'s `update_clinic` (`PATCH /clinics/{clinic_id}`) and `delete_clinic` (`DELETE /clinics/{clinic_id}`, a soft-delete) only depended on `get_current_user` — any authenticated user, regardless of role, could rename or deactivate/soft-delete the clinic. Every other Admin-only surface in this codebase (Users list, Queue Settings write, Config write) correctly gates on `require_config_manage_role` (`Owner`/`Administrator` only per `CONFIG_MANAGE_ROLES` in `backend/app/core/dependencies.py`), but `clinics.py` was never wired to it.

**Steps to reproduce (reproduced live before fixing)**
1. Log in as `uat.reception@connectph.dev` (Receptionist) and as `maria.santos@connectph.dev` (Doctor).
2. `PATCH /api/v1/clinics/{clinic_id}` with `{"name": "hack"}` using either token.

**Expected behavior**
403 for any role other than Owner/Administrator, matching every other clinic-configuration write endpoint.

**Actual behavior (before fix)**
Both the Receptionist token and the Doctor token got `200` and the clinic's real `name` ("CONNECT.PH Demo Clinic") was actually overwritten to `"hack"` in the live dev database both times. `DELETE` (soft-delete) had the identical gap, unverified further to avoid taking down the shared dev clinic other concurrent UAT work depends on, but the code path is identical.

**Root cause**
`update_clinic`/`delete_clinic` used the bare `get_current_user` dependency instead of the existing `require_config_manage_role` (`Owner`, `Administrator`) already used elsewhere in the codebase for identical-shaped clinic-configuration writes.

**Fix / PR**
`backend/app/api/v1/clinics.py`: imported `require_config_manage_role` from `app.core.dependencies` and changed `update_clinic`'s and `delete_clinic`'s `_current_user` dependency from `Depends(get_current_user)` to `Depends(require_config_manage_role)`.

**Verification**
Live before/after: before the fix, `PATCH` as Receptionist → `200` (clinic name actually changed, confirmed and immediately reverted to `"CONNECT.PH Demo Clinic"` via an Owner token, cross-checked against the real seeded value in `backend/backups/backup-20260727T115114-*.sql`). After the fix (backend hot-reloaded), the identical `PATCH` as Receptionist → `403 {"detail":"You do not have permission to perform this action."}`; the same call as Owner and as Administrator both still → `200`. `backend/app/tests/conftest.py`'s DB-name guard was not touched. Compile check: `python -c "import app.main"` → clean.

**Resolution date**
2026-08-06

---

### BUG-027: Vitals-before-Queue never triggered due to a service_code allowlist mismatch

- **Reported by:** Follow-up verification pass on the interrupted "Phase 21 (Vitals-before-Queue)" work
- **Date reported:** 2026-07-29
- **Severity:** High
- **Status:** Fixed
- **Area:** backend/frontend

**Description**
The prior (interrupted) implementation gated the whole "Consultation/Follow-up requires vitals before a queue ticket can be created" feature behind a `service_code` allowlist — `PRE_QUEUE_VITALS_SERVICE_CODES = {"CONS", "FOLLOWUP"}` in both `backend/app/services/queue_service.py::service_requires_pre_queue_vitals()` and the mirrored frontend constant in `NewQueueDialog.tsx`. The real seeded `ClinicService` rows for these two services actually have `service_code = "CONSULT"` and `service_code = "FOLLOW-UP"` (confirmed via `GET /api/v1/services`). Since neither matched the allowlist, `requiresVitals` was always `false`: selecting Consultation or Follow-up in New Queue Ticket showed "Create Queue Ticket" immediately (no vitals step), and the backend's `POST /queues` never took the pre-queue-required branch either — so a Consultation/Follow-up ticket could be created with zero vitals captured, silently defeating the entire feature end-to-end despite the backend enforcement code around it being otherwise correct.

**Steps to reproduce**
1. As Receptionist, open New Queue Ticket, select a patient and the "Consultation" service.
2. Observe the submit button reads "Create Queue Ticket" (not "Enter Vitals") and Doctor is optional.
3. Submit — a queue ticket is created immediately with no vitals captured.

**Expected behavior**
Selecting Consultation or Follow-up should show "Enter Vitals", require a doctor, and block ticket creation until vitals are saved (both as a UX affordance and as a real backend 400 if bypassed).

**Actual behavior**
The vitals gate never activated in either direction (frontend button, backend enforcement) because the code-matching logic used codes that don't exist in the seeded data.

**Root cause**
A naming mismatch between the allowlist constants introduced by the interrupted prior session and the actual `service_code` values already seeded in the dev database — never caught because no live test had actually selected the Consultation/Follow-up service in the UI and inspected the button label.

**Fix / PR**
`backend/app/services/queue_service.py` line 55: `PRE_QUEUE_VITALS_SERVICE_CODES = {"CONSULT", "FOLLOW-UP"}`. `frontend/src/features/queue/components/NewQueueDialog.tsx`: `PRE_QUEUE_VITALS_SERVICE_CODES = new Set(["CONSULT", "FOLLOW-UP"])`. Verified live end-to-end after the fix (see `docs/TESTING.md`).

**Resolution date**
2026-07-29

---

### BUG-026: Doctor Session restart on the same day crashed with a 500 (unhandled IntegrityError)

- **Reported by:** Independent verification of Round 3 item 14 (Doctor Session Control), following up on the implementing agent's own explicit note that `end_session` and a same-day restart were "not verified"
- **Date reported:** 2026-07-29
- **Severity:** High
- **Status:** Fixed
- **Area:** backend

**Description**
`DoctorSession` has a `UniqueConstraint("clinic_id", "doctor_id", "session_date")` — one row per doctor per day, regardless of whether that session is currently open or already ended. `DoctorWorkspaceService.start_session()` only checked for an *open* session (`get_open_for_doctor`, filtered on `ended_at IS NULL`) before deciding whether to insert a new row. A doctor who ends their session and then starts a new one later the same day has no open session, so the code proceeded to `INSERT` a second row for the same `(clinic_id, doctor_id, session_date)` — violating the unique constraint and raising an unhandled `IntegrityError`, surfaced to the client as a bare `500 Internal Server Error`.

**Steps to reproduce**
1. As a Doctor, `POST /doctor-workspace/session/start` — succeeds.
2. `POST /doctor-workspace/session/end` — succeeds.
3. `POST /doctor-workspace/session/start` again, same day — `500`.

**Expected behavior**
Restarting a session on the same day should reopen the existing (now-ended) row for that day, not attempt to create a second one.

**Actual behavior**
Unhandled `IntegrityError` → `500`, no useful error message to the client.

**Root cause**
`start_session()`'s existence check (`get_open_for_doctor`) doesn't distinguish "no session today" from "a session today that's already ended" — both return `None`, so both paths fell through to an unconditional `create()`.

**Fix / PR**
`backend/app/services/doctor_workspace_service.py::start_session()` — now also checks `get_for_doctor_and_date()` (a repository method that already existed but was unused for this purpose) for *any* row matching today's date. If one exists, it's reopened in place (`started_at`/`started_by` updated, `ended_at` cleared) instead of inserting a new row; only creates a fresh row when no row exists for today at all.

**Verified live**: reproduced the crash first (confirmed `500` on the exact repro steps above) before fixing. After the fix and a full backend restart (the running dev process didn't pick up the change via its file-watcher — a recurrence of this environment's previously-documented "zombie process" issue where a stale worker keeps serving traffic without reloading; worked around by starting a fresh instance on an alternate port and repointing the frontend, per the same pattern used earlier in this project's history), the exact same start → end → start sequence completed cleanly (`200` at every step, `active: true`/`false`/`true` in the expected order).

**Resolution date**
2026-07-29

---

### BUG-000: Example — login form allows empty password submission

- **Reported by:** Jane Dev
- **Date reported:** 2026-07-01
- **Severity:** Medium
- **Status:** Fixed
- **Area:** frontend
- **Environment:** local

**Description**
The login form's submit button is not disabled when the password field is empty, allowing a request to be sent with an empty password.

**Steps to reproduce**
1. Go to `/login`.
2. Enter a valid email, leave password blank.
3. Click "Sign in".

**Expected behavior**
Client-side Zod validation should block submission and show "Password is required."

**Actual behavior**
Request is sent to `/api/v1/auth/login` with an empty password string; backend correctly rejects with 401, but no inline error shown, so it looks broken.

**Root cause**
Zod schema for the login form was missing a `.min(1)` constraint on `password`.

**Fix / PR**
`frontend/src/features/auth/schemas.ts` — added `.min(1, "Password is required")`.

**Resolution date**
2026-07-02
