# Changelog

Chronological version history, Phase 1 (Foundation) through v1.0.0 (Commercial Release). This is a condensed summary derived from [`RELEASE_NOTES.md`](RELEASE_NOTES.md) (per-version detail) and [`ROADMAP.md`](ROADMAP.md) (phase sequencing) — see those files for the full narrative on any entry below. Follows a changelog convention (newest first); it does not renumber or alter any existing release-notes entry.

---

## v1.0.0 — Commercial Release (2026-07-28)

Release-preparation milestone, not a new feature phase. See [`RELEASE_NOTES_v1.0.0.md`](RELEASE_NOTES_v1.0.0.md) for the full verification report.

- Regression-verified every module's core happy path (Auth, Users, Patients, Clinic Config, Reception/Queue, Visits, Doctor Workspace, Consultation/SOAP, Orders, Prescriptions, Laboratory, Billing, Appointments, TV Queue Display, Migration Wizard, SaaS Admin Portal, health/ready/live probes) via live API calls against the running dev stack — all passing.
- Fixed two release-blocking frontend build errors (unescaped apostrophes in `doctor-schedules` and `doctor-workspace` pages tripping the Next.js ESLint gate on `npm run build`) — the only code changes made this phase, per the "fix only genuine Critical/High defects found this phase" rule.
- Confirmed zero Open Critical/High bugs in `BUGS.md` (one prior High — BUG-001 — was fixed in Phase 17; the three currently open items are Low severity with documented workarounds).
- Verified the Alembic migration chain (`0001_initial` → `0016_hardening_indexes`) runs cleanly end-to-end on a fresh, disposable database.
- Verified `frontend` builds cleanly for production (`npm run build`).
- Version bumped to `1.0.0` in `backend/pyproject.toml`, `frontend/package.json`, `backend/app/main.py` (FastAPI `version=`), and a new root `VERSION` file.
- New docs: `README.md` (rewritten), `docs/INSTALL.md`, `docs/CHANGELOG.md`, `docs/RELEASE_NOTES_v1.0.0.md`, `docs/DEPLOYMENT_PACKAGE.md`. Reviewed (not rewritten) `DEPLOYMENT.md`, `USER_MANUAL.md`, `ADMINISTRATOR_GUIDE.md`, `DATABASE.md`, `MIGRATION.md`, `BACKUP.md`, `API.md`, `SECURITY.md`, `ARCHITECTURE.md` for accuracy; fixed one stale `API.md` example (`/health` response shape no longer matched the real endpoint).
- **Explicitly not done, and not claimed to be done**: no real git tag (this is not a git repository), no real CI/CD pipeline run, no real Docker image build/push, no real cloud deployment, no real customer onboarding. See `RELEASE_NOTES_v1.0.0.md` for the full honest scope statement.

## v0.17.0 — Pilot Deployment & User Acceptance Testing (Phase 17)

- Reviewed deployment readiness (env vars, migration state, storage config, background jobs, logging/monitoring, backups) against the running dev stack; no real cloud host provisioned.
- Created and fully configured a real pilot tenant via live API calls.
- Exercised the Legacy Migration Wizard hands-on with a realistic sample dataset; found and fixed a real High-severity bug (BUG-001 — resolving a validation issue had no effect on import, rows were still force-skipped).
- Ran a full scripted UAT of the patient journey (Registration → Appointment → Check-in → Queue → Consultation → Orders → Prescription → Laboratory → Billing → Completion) — 17/17 steps passing against a live backend.
- Logged two Medium/Low findings (BUG-002, BUG-005) with documented workarounds, not fixed (out of scope for the phase's fix-only-Critical/High rule).
- New docs: `PILOT_READINESS.md`, `USER_MANUAL.md`, `ADMINISTRATOR_GUIDE.md`, `SUPPORT_GUIDE.md`.

## v0.16.0 — Production Hardening (Phase 16)

- Added genuinely-missing DB indexes (`laboratory_orders.branch_id`/`.doctor_id`, composite `(clinic_id, status)`/`(clinic_id, invoice_date)`) based on real `EXPLAIN ANALYZE`/FK-index analysis.
- Added `/live` and `/ready` health probes, request-id middleware (`X-Request-ID`), and a standardized `{"detail", "request_id"}` error envelope.
- Reviewed CORS/rate-limiting (sound, no changes needed); found and fixed a real file-upload validation gap (consultation/laboratory attachments, migration wizard uploads).
- Added an in-process TTL cache with real invalidation on mutation (departments list, feature flags).
- Added real `pg_dump`-backed backup verification and `docs/BACKUP.md`.
- Ran a real load test (`backend/scripts/load_test.py`) against a live dev server with real p50/p95 numbers reported.
- Partial, honestly-scoped cross-browser/accessibility pass.

## v0.15.0 — SaaS Administration Portal (Phase 15)

- New structurally-separate platform-admin data model, JWT claim shape, and dependency chain — verified never interoperable with clinic-scoped tokens in either direction.
- Cross-tenant tenant management (list/search/create/suspend/reactivate/archive), subscription/license management, 8 feature flags (1 wired end-to-end), tenant user administration, System Health dashboard, platform audit log.
- Four platform roles with a documented read/write matrix.
- New `app/platform/` frontend portal, structurally separate from the clinic portal (own layout, login, token storage).

## v0.14.0 — Legacy Migration Wizard (Phase 14)

- Real, resumable, idempotent import engine (CSV/Excel fully working; SQLite/Access/SQL Server/MySQL/PostgreSQL adapters architecture-only) plus an 8-step wizard UI.
- Backfilled `LegacyMixin` columns onto `branches`/`departments`/`doctors`/`services` (an audit finding from this phase, fixed in the same migration).
- Fuzzy/synonym field-mapping engine, 3 real transforms, validation reusing Phase 3's duplicate-detection pattern.
- Only Patients and Doctors write to real destination tables this phase; 15 other entity types get full mapping/validation but are marked `Skipped` on import (documented scope decision, BUG-003).

## v0.13.0 — Live TV Queue Display (Phase 13)

- Public, unauthenticated fullscreen kiosk display reading the existing Phase 5 realtime queue channel via a `public_slug` credential instead of a JWT.
- Patient identification reduced to initials only, server-side, never a full name.
- First reconnect-with-exponential-backoff logic in the project.
- Text-to-speech announcement templating is architecture-only; no audio synthesis implemented.

## v0.12.0 — Owner Dashboard & Reports (Phase 12)

- Read-only aggregation/reporting layer over every operational table built so far — no new tables.
- 16-stat Owner Dashboard, activity feed, threshold alerts, six report endpoints with date-range filters and chart-ready series.
- Real CSV/Excel export; PDF export explicitly stubbed (`501`).
- Owner/Administrator-only access, verified 403 for every other role.

## v0.11.0 — Appointment Management (Phase 11)

- Full appointment lifecycle (Booked → Confirmed → Checked-in → Queue Generated → Visit Created → Consultation → Billing).
- Time Slot Engine computed on demand (never persisted) from doctor schedule minus lunch/bookings/holidays/blocks.
- Check-in reuses the existing Phase 5/6 queue/visit creation flow rather than reimplementing it.
- Frontend Calendar (Day/Week/Month/Agenda) and Doctor Schedule admin page.

## v0.10.0 — Laboratory Management (Phase 10)

- Laboratory department workflow (collection → processing → multi-parameter results → release) layered on Phase 9's Laboratory-category orders via a 1:1 `laboratory_orders` table.
- Every lab-workflow transition mirrors onto the underlying `Order.status` (a real bug of this class was found and fixed live).
- Idempotent billing integration; a real cross-order id-collision bug was found and fixed live.
- Configurable test/pricing/reference-range template catalog.

## v0.9.0 — Clinical Orders & Prescriptions (Phase 9)

- Laboratory/Radiology/Vaccination/Custom Orders, Procedures, Referrals, and Prescriptions during an in-progress consultation.
- Non-blocking prescription validation (warnings, never blocks save); allergy-conflict checking is architecture-only (no drug database yet).
- New Laboratory role, scoped to Laboratory-category orders only.

## v0.17.0 (legacy numbering) — Billing & Cashier

> Numbering collision, intentionally left as-is — see `RELEASE_NOTES.md`'s note on this entry. Chronologically this shipped as Phase 9/10-era work, well before the real v0.17.0 (Pilot Deployment) above.

- Consultation-complete auto-creates a Draft invoice with a priced Consultation Fee line item (idempotent).
- Invoice reaching Paid transitions the linked Visit to Completed.
- Split payments, discount handling, printable receipts.
- Receptionist read-only; Cashier + Owner/Administrator manage; refund approval stubbed (no UI).

## v0.8.0 — Clinical Consultation / SOAP (Phase 8)

- SOAP notes, diagnoses, consultation attachments; SOAP note upserted in place on autosave.
- Fixed a bug where completing a Consultation didn't sync the linked Queue ticket's status.
- Stricter role gating: only the assigned doctor edits; Receptionist excluded entirely.

## v0.7.0 — Doctor Workspace (Phase 7)

- `users.doctor_id` link resolves a Doctor-role login to its Doctor record.
- Doctor Dashboard with live stats and contextual Call/Recall/Start/Complete/No-Show/Cancel actions.
- Visit locking with a heartbeat timeout, view-only for other holders (not a hard block).

## v0.6.0 — Visit (Encounter) Management

- Visit as the central transaction, auto-created from every Reception Queue ticket.
- Visit status machine with a legal-transition table and an append-only timeline log.
- Sequential, concurrency-safe visit numbering (`VIS-YYYYMMDD-000001`).

## v0.5.0 — Reception & Queue Management

- Walk-in queue ticketing with priority lanes and a status machine.
- Realtime WebSocket broadcast channel for live queue updates.
- Printable queue slip with a signed QR check-in token.

## v0.4.0 — Clinic Configuration & Master Data

- Ten configuration/master-data modules (Clinic Settings, Branches, Departments, Doctors, Consultation Rooms, Services, Queue Settings, Operating Hours, Holidays, Branding), all tenant-scoped, soft-deletable, role-gated, audit-logged.

## v0.3.0 — Patient Management

- Tenant-scoped master patient database with sequential numbering, duplicate detection, signed QR check-in payload.
- Archive/restore as a business-status change, separate from soft-delete.

## v0.2.0 — Multi-tenant Authentication & User Management

- JWT access + rotating opaque refresh tokens (hashed at rest), account lockout, password reset/email verification flows, rate limiting.
- Roles seeded (Owner, Administrator, Receptionist, Doctor, Nurse, Cashier, Laboratory, Pharmacy, Viewer).

## v0.1.0 — Foundation

- Multi-tenant database foundation (`clinics`, `branches`, `users`, `roles`, `permissions`, `role_permissions`, `audit_logs`, `system_settings`, `subscriptions`), UUID-keyed with soft-delete and `legacy_id`/`legacy_meta` provenance columns.
- Next.js 15 App Router frontend shell; FastAPI Clean Architecture backend skeleton; Alembic migrations; CI/CD and Docker scaffolding.
