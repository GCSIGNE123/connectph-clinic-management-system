# Release Notes

Human-readable, per-version summary of what shipped. For full detail see [`FEATURES.md`](FEATURES.md) (built vs. planned) and [`ROADMAP.md`](ROADMAP.md) (phase sequencing/goals); entries below are intentionally brief. See [`RELEASE_NOTES_v1.0.0.md`](RELEASE_NOTES_v1.0.0.md) for the full v1.0.0 verification report and [`CHANGELOG.md`](CHANGELOG.md) for the complete Phase 1 → v1.0.0 history in one place.

---

## Post-RC1 — Phase 2.7: YAKAP Patient Classification + Receptionist Queue Control

**As of 2026-08-11.** Distinguishes PhilHealth YAKAP beneficiaries from Regular/walk-in patients, and makes the Receptionist the explicit queue controller. `Patient.is_yakap_beneficiary` (standing beneficiary status, patient profile) and `Queue.visit_classification` (per-encounter classification, queue ticket, pre-filled from the patient flag but independently editable) are two deliberately separate, additive fields - not a queue prefix, not a merge of the two concepts. Existing A/B/L/R queue numbering, multi-doctor/multi-department TV Display grouping, and destination-aware announcements are completely untouched. Reception Queue gained a Classification column, an All/YAKAP/Regular filter, and row-level Call/Re-announce actions (reusing the Call/Re-announce mechanism already built for the prior Reception Queue Workflow Improvements release) - the receptionist explicitly chooses who is called next; there is no automatic YAKAP-first prioritization. The public TV Display now shows a YAKAP/REGULAR badge alongside the existing queue number/doctor/room, while continuing to never expose the patient's name (only the pre-existing privacy-safe initials). Live-verified end-to-end with a real Receptionist session: two real patients (one YAKAP, one Regular), two queue tickets with plain sequential numbers, a deliberate out-of-order call (Regular called before YAKAP), correct destination announcements, correct TV Display updates with no patient name exposed, and a clean Re-announce with no duplicate ticket. See `docs/FEATURES.md`/`docs/TESTING.md` for full detail, `docs/DATABASE.md`/`docs/API.md` for schema/endpoint detail. No cloud dependency introduced or exercised - fully functional against the local clinic server alone.

---

## Post-RC1 — Multi-Department / Multi-Doctor TV Queue Display

**As of 2026-08-07, continuing the same narrow freeze exception used throughout Post-RC1**: extends the existing TV Queue Display and queue-prefix configuration to support multiple simultaneous doctors/departments (e.g. Doctor A, Doctor B, Laboratory, Radiology all shown at once, each with their own independent prefix and sequencing), for the Canora Medical Clinic go-live. Explicitly additive on top of the existing Queue/QueueSetting/TvDisplayConfig architecture — no redesign of queue creation, calling, or numbering; no change to existing single-doctor clinic behavior.

**Complete and live-verified, 2026-08-09.** New `queue_settings.doctor_id` column (migration `0025_queue_setting_doctor_prefix`) lets two doctors in the same department get independent prefixes, resolved via a new `get_effective_for_doctor` chain (doctor → department → branch/clinic default → `"A"`) mirroring the existing department-override pattern one level deeper; the `/queue-settings` admin page gained a "Department & doctor prefix overrides" card (previously department scoping existed on the model but had no reachable API/UI at all). `TvDisplayNowServing`/`TvDisplayWaitingEntry` gained `department_id`/`department_name` so the frontend can group/label a mixed result set by destination; `TvDisplayScreen.tsx` now renders one card per active doctor/department when 2+ are simultaneously active, while a single active destination (the ordinary single-doctor-clinic case) still renders the original unchanged flat layout. The queue announcer (`queue-announcer.ts`) now announces every ticket whose `called_at` changed in a fetch cycle (not just the first — a real gap this feature exposed once multiple doctors/departments can be called together), sequencing them through a local speak-queue instead of clobbering via `.cancel()`, and speaks destination-aware text ("...please proceed to Dr. X" / "...please proceed to the Laboratory"). Confirmed live that an unscoped `TvDisplayConfig` (`branch_id`/`department_id`/`doctor_id` all `null`) already returns the full multi-department feed — no new config concept was needed; `/tv` and `/tv/[slug]` (pre-existing routes) already serve this correctly, so no new route was added either. Found and logged (not fixed inline, out of scope for this feature) BUG-033: the pre-existing clinic-wide `queue_settings` form has always saved `branch_id: null`, which can never resolve for a real ticket (whose `branch_id` is never null) — it has been silently relying on the hardcoded `"A"` fallback in production. See `docs/TESTING.md`'s "Post-RC1: Multi-Department / Multi-Doctor TV Queue Display" section for the full 11-scenario live verification (real API/DB/browser evidence), `docs/FEATURES.md` for the full technical summary, `docs/DATABASE.md`/`docs/API.md` for schema/endpoint detail, and `docs/BUGS.md` (BUG-033) for the logged pre-existing defect.

---

## Post-RC1 — Vaccination Administration

**Complete and live-verified, 2026-08-07.** Closes a real gap in the existing Clinical Orders module: a Doctor could already order a Vaccination, but nothing let anyone record it as actually given — only the assigned Doctor could touch order status at all, with no Nurse permission and Receptionist explicitly read-only. New `vaccination_administrations` table (migration `0024`) auto-attaches to a Vaccination-category order the same way Laboratory's workflow table does; a new, deliberately broader permission (`Owner/Administrator/Doctor/Nurse/Receptionist`) lets any Nurse or Receptionist administer a vaccination a doctor ordered — capturing dose, lot number, injection site, route, and notes — not just the ordering doctor. New `/vaccinations` dashboard page for the worklist. Found and fixed BUG-032 (pre-existing missing eager-load in tenant-user management) along the way. See `docs/FEATURES.md`/`docs/DATABASE.md`/`docs/API.md` for full detail.

---

## Post-RC1 — Phase 2.6: Local Production Deployment, Windows Auto-Start (explicit freeze exception, continuation)

**As of 2026-08-06, continuing the same narrow freeze exception used for Milestones 1-2 and Phase 2.5**: "Phase 2.6 – Local Production Deployment (Windows Auto-Start)" converts the doctor-desktop clinic install from a developer workflow (VS Code / `npm run dev` / manual `uvicorn`) into a production local deployment that starts PostgreSQL, the backend, and the frontend automatically on Windows boot, with zero developer-tool interaction required. Explicitly no business-logic, workflow, permission, UI, or schema changes, and no cloud sync work — this is purely local startup/service/installation engineering for the first live install at Canora Medical Clinic. See `docs/TESTING.md` for this phase's own verification section.

**Complete.** New `deploy/windows/` script set: `install_local_clinic.bat` (orchestrator), `start_clinic.bat` / `stop_clinic.bat` / `restart_clinic.bat` (manual control, PostgreSQL → Backend → Frontend order via a shared `_wait_for.bat` poll-with-timeout helper — never a fixed sleep), `check_health.bat` (reuses the existing `GET /api/v1/system/status` and `/api/v1/health`/`/api/v1/ready` endpoints, no backend changes needed), `install-postgres-service.bat` / `install-backend-service.bat` / `install-frontend-service.bat` (NSSM-based Windows Service registration — auto-start, auto-restart on crash, `DependOnService` chaining, `LocalSystem` account, stdout/stderr log files), `open-firewall-ports.bat` (`netsh advfirewall`, TCP 3000/8000, Private profile only), and `launch_clinic_browser.bat` (post-boot browser auto-launch, Startup-folder or Scheduled-Task install documented, not force-installed). New env templates `backend/.env.local-production.example` and `frontend/.env.local-production.example` (a third profile alongside Phase 2.5's dev/cloud-production pair — `DEPLOYMENT_MODE=local` by default since this *is* the local clinic instance, `COOKIE_SECURE=false` since this install deliberately serves plain `http://<LAN-IP>` rather than adding a reverse proxy for HTTPS on day one). New docs `docs/LOCAL_DEPLOYMENT.md`, `docs/WINDOWS_SERVICE_SETUP.md`, `docs/FIRST_CLINIC_INSTALLATION.md`, cross-linked with (not duplicating) Phase 2.5's `DEPLOYMENT.md`/`INSTALLATION_GUIDE.md`.

**Network reality documented honestly**: true bare `http://localhost` (port 80, no reverse proxy) is not achievable without adding new infrastructure this phase deliberately does not force-install for the first clinic rollout; the shipped, documented URL scheme is `http://<Doctor-PC-LAN-IP>:3000` (frontend, including `/tv`) and `:8000` (API) — see `LOCAL_DEPLOYMENT.md` §7 for the full reasoning and the documented future path (a minimal reverse proxy) if a bare-`:80` URL later becomes a real requirement.

**What was verified live, with real evidence, on the shared dev machine** (see `docs/TESTING.md`'s Phase 2.6 section for the full table): the portable `.devdb\` Postgres started cleanly via the existing `backend/scripts/start_dev_postgres.ps1` pattern (port 5433); a real `npm run build` succeeded and the built app was actually served via `npm run start -- --port 3000` (`GET /` → `307` to `/login`, `GET /login` → `200` — this phase is the first to prove `next start` itself works, not just that the build succeeds, since Phase 2.5 only ever shipped the build to Vercel); `check_health.bat` was run for real against the live dev backend/frontend/Postgres and correctly reported all four unauthenticated checks `[ OK ]`, plus the auth-gated `deployment_mode`/`cloud_status`/`pending_sync_jobs` check with a real Owner bearer token; the full `start_clinic.bat` boot-order/polling logic was code-reviewed against this same proven sequence (Postgres tcp-poll → Backend health-poll → Frontend health-poll).

**What was deliberately written but NOT executed** (real, persistent Windows OS-level changes reserved for the actual clinic machine, run by a human with Administrator rights): `install-postgres-service.bat`, `install-backend-service.bat`, `install-frontend-service.bat`, `install_local_clinic.bat` (NSSM Windows Service registration), and `open-firewall-ports.bat` (`netsh advfirewall` real firewall rule). The one acceptance step that inherently requires the real target machine — a real reboot with no one logged in, confirming the three services and browser auto-launch come up unattended — is documented as clinic-IT's final step in `docs/FIRST_CLINIC_INSTALLATION.md`, with the exact command sequence.

**Zero regressions**: `python -c "import app.main"` clean; dev backend restarted fresh on port 8000 and dev frontend restarted fresh on port 3000 (`.next` cleared and rebuilt from scratch after the production-build test, per this environment's shared `.next` gotcha) — `GET /api/v1/health` → `200`, `POST /api/v1/auth/login` (`pilotowner@example.com`) → `200`, `GET /patients` with the resulting Owner token → `200`. No business logic, workflow, permission, UI, or schema code touched; no new Alembic migration.

---

## Post-RC1 — Phase 2.5: Production Cloud Deployment (explicit freeze exception, continuation)

**As of 2026-08-06, continuing the same narrow freeze exception used for Milestones 1 and 2**: "Phase 2.5 – Production Cloud Deployment" prepares the platform for its first real production deployment (frontend on Vercel, backend on a VPS behind Nginx/HTTPS, a real Cloud PostgreSQL as the backup target) without changing the hybrid architecture established in Milestones 1-2. Local Clinic Server remains the sole primary/source-of-truth database; the Cloud Server remains backup/monitoring/support only, uploaded to but never written back from. This is deployment configuration, environment separation, documentation, and Admin dashboard expansion — not new business functionality, and explicitly not bidirectional sync. No existing clinic workflow may change behavior.

**Complete and live-verified.** New `.env.development.example`/`.env.production.example` templates (backend and frontend, alongside the existing `.env.example` pattern; `.gitignore` extended to keep real `.env.development`/`.env.production` files untracked while their `.example` companions stay tracked). New `deploy/connectph-backend.service` (systemd + Gunicorn/Uvicorn-workers) and `deploy/nginx-connectph.conf` (HTTPS reverse proxy, Let's Encrypt/certbot) templates. New `docs/DEPLOYMENT.md` §0 (VPS backend deployment — supersedes the file's earlier Railway/Supabase planning draft for backend/database hosting; Vercel frontend guidance carried over) and new `docs/INSTALLATION_GUIDE.md` (clinic-hardware companion to `docs/INSTALL.md`'s software setup). System Status dashboard extended with Backend Version (`app_version`, sourced from a new `Settings.APP_VERSION` — now the single source for `app.main`'s FastAPI `version=` too) and Frontend Version (self-reported via `NEXT_PUBLIC_APP_VERSION`, since the backend has no way to know a separately-deployed Vercel frontend's build version). Confirmed `/api/v1/health` (no auth, no DB call) is the correct load-balancer/uptime target and is already environment-agnostic. Confirmed CORS (`CORS_ORIGINS`/`cors_origins_list`) and the one cookie this app sets (`COOKIE_SECURE`/`COOKIE_SAMESITE`, refresh-token cookie only — the app is otherwise JWT-bearer) are both already environment-driven, not hardcoded.

**One real production-build blocker found and fixed** (BUG-031, High): `next build` failed outright on `/messages` — a missing `<Suspense>` boundary around `useSearchParams()`, invisible under `next dev` (which never statically prerenders) and therefore undetected since the messaging feature shipped, since no prior phase had run a real production build. Fixed by isolating the search-param read into a `<Suspense>`-wrapped child component; `npm run build` now completes cleanly across all 49 routes with a production-supplied `NEXT_PUBLIC_API_URL` and no dev-only fallback baked into the bundle (grep-audited: every hardcoded-`localhost` occurrence in `frontend/src/` is already an env-var-with-dev-fallback pattern, e.g. `frontend/src/lib/api-client.ts:3`, never an unconditional literal).

**Backup verification re-confirmed live end-to-end** after this phase's config changes, reusing Milestone 2's proof pattern: a fresh throwaway Postgres database + a second real instance of this codebase on port 8002 stood in for "the cloud"; the primary dev instance was temporarily set to `DEPLOYMENT_MODE=hybrid` pointed at it. A real patient created via `POST /patients` (`Phase25 BackupTest`, id `9ccfd183-0924-49d5-a7a0-12623f60d5f5`) produced a `sync_jobs` row that drained within one worker tick, landed as a genuine `synced_records` row in the separate cloud database (confirmed via direct query), and was reflected on `GET /system/status` (`total_uploaded_today` incremented, `last_successful_sync_at` updated, `cloud_status: "up"`) — all re-verified in a real browser session on `/system-status` too. The throwaway cloud instance/database was torn down and the primary instance reverted to its normal local-only `.env` afterward; `DEPLOYMENT_MODE=local` confirmed to return to `not_configured`/fully local behavior with zero lingering state.

**Zero regressions**: `python -c "import app.main"` clean; `npx tsc --noEmit` clean; a real production `npm run build` succeeds (new for this phase — prior milestones only ran `tsc --noEmit`); Reception queue creation, Patients list, Shift `current` summary, and RBAC on `GET /system/status` (401 unauthenticated, succeeds for Owner) all spot-checked live against a freshly restarted backend after all config changes. See `docs/TESTING.md`'s "Post-RC1 Phase 2.5" section for the full evidence table.

---

## Post-RC1 — Phase 2 Milestone 2: Cloud Backup, One-Way Sync (explicit freeze exception, continuation)

**As of 2026-08-06, continuing the same narrow freeze exception used for Milestone 1**: "Phase 2 – Milestone 2: Cloud Backup (One-Way Sync)" builds a persistent local→cloud sync queue, a background sync worker with retry/backoff, authenticated Cloud Backup API endpoints, and an expanded Sync Status Dashboard on top of Milestone 1's Connectivity Service. Explicitly upload-only: local is always the source of truth, the cloud can never write back to or overwrite local data, and no clinic workflow may ever be blocked, slowed, or altered by sync — a queued record that fails to sync stays queued and retries later, it never fails the underlying clinic operation.

**Complete and live-verified.** New `sync_jobs`/`synced_records` tables (migration `0023_sync_jobs`); `sync_queue_service.enqueue()` wired into Patient, Visit, SOAP note, Queue ticket, Prescription, Laboratory order/result, Payment, and Shift's successful-mutation paths (best-effort — any enqueue failure is caught/logged and never affects the primary clinic operation); a background `sync_worker_service` (30s tick, exponential backoff, Internet-Recovery hook off Milestone 1's Connectivity Service); a `POST /api/v1/backup/{entity_type}` endpoint authenticated with a distinct `X-Sync-Api-Key` shared secret (not any existing JWT type); and the System Status dashboard now also shows Pending Sync Jobs, Retry Queue, Total Uploaded Today, Average Sync Time, and Last Successful/Failed Sync, polling every 10s. Proven end-to-end against a real second instance of this codebase on a separate port/database standing in for "the cloud" (no real cloud deployment exists yet) — including retry/backoff genuinely triggered by killing that instance mid-queue and confirming automatic recovery once it came back. `DEPLOYMENT_MODE=local` (the unchanged default) remains behaviorally identical to before this milestone. See `docs/TESTING.md`'s "Post-RC1 Phase 2 Milestone 2" section and `docs/FEATURES.md` for full detail.

---

## Post-RC1 — Phase 2 Milestone 1: Cloud Readiness (explicit freeze exception)

**As of 2026-08-06, the RC1 feature freeze below is explicitly, narrowly lifted for one new initiative**: "Phase 2 – Milestone 1: Cloud Readiness" — config support for Local/Hybrid deployment modes, a Connectivity Service, and an Admin System Status panel. This is a direct client instruction to begin the next phase of work, not a reversal of the freeze policy itself — RC1's own scope (everything documented below) remains otherwise frozen, and this new work is explicitly scoped to NOT touch existing clinic workflows, NOT implement synchronization yet, and preserve full backward compatibility with the current local-only deployment. See `docs/TESTING.md` for this milestone's own verification section once complete.

---

## v1.7.0-rc1 — Release Candidate 1 (feature freeze in effect)

**As of 2026-07-29, CONNECT.PH Clinic Platform is in Release Candidate status.** New feature development is frozen; only bug fixes and genuine production blockers are in scope until RC1 either ships as `v1.7.0` or a defect is found that requires an RC2.

**Why now:** every open bug in `docs/BUGS.md` at this point is Medium or Low severity — no Critical or High severity defect is currently open (the six that were found across this project's history — BUG-001, BUG-019, BUG-020, BUG-021, BUG-026, BUG-027 — are all Resolved, each with live-verified evidence in `docs/TESTING.md`). Both `backend` (`python -c "import app.main"`) and `frontend` (`npx tsc --noEmit`) compile clean.

**Housekeeping done as part of the RC1 declaration**: found and fixed real version-string drift — `VERSION`, `backend/pyproject.toml`, `backend/app/main.py`'s FastAPI `version=`, and `frontend/package.json` were all still stamped `1.2.0` despite this file documenting features all the way through `v1.6.4`. All four now correctly read `1.7.0-rc1`.

**What "bug fixes and production blockers only" means in practice for whoever picks up work from here:**
- DO: fix anything that reproduces as broken, wrong, or unsafe — a Critical/High find always takes priority over everything else.
- DO: harden/verify existing behavior (add a missing check, close a real gap in test coverage, fix a stale doc).
- DO NOT: add a new client-requested capability, workflow, or UI surface that isn't a fix for something already broken — route those into a post-RC1 backlog instead.
- If in doubt whether something is a "fix" or a "feature," treat it as a feature and hold it for after RC1 ships, or ask before proceeding.

**Currently open, Medium/Low only** (see `docs/BUGS.md` for full detail — not blocking RC1, listed here for visibility): BUG-002, BUG-003, BUG-004, BUG-005, BUG-006, BUG-007, BUG-008, BUG-009, BUG-016, BUG-017, BUG-022.

---

## v1.6.4 — Vitals-before-Queue completion, Save-and-Close UI, queue-numbering resync

- **Vitals-required-before-queueing is now complete and working end-to-end.** Consultation/Follow-up services require vitals (BP, Temp, Pulse, RR, SpO2, Height, Weight; BMI auto-computed) to be captured via a draft Visit before a queue ticket can be created, enforced by the backend (not just a disabled button). Fixed a launch-blocking bug (BUG-027) where a `service_code` mismatch between the frontend/backend allowlists and the real seeded service codes silently disabled the entire feature.
- **"Save and Close"** replaces "Save" on both the vitals-entry step and the existing after-queueing vitals-edit dialog: validates, saves, shows a toast, and closes automatically — with inline validation highlighting and keyboard shortcuts (Enter to save, Esc to close).
- **Queue-number generation hardened** with a defensive resync so the per-prefix/per-day counter can never fall behind the actual highest issued number for that bucket, even if some future code path bypasses it — verified with concurrent ticket creation producing strictly increasing, non-reused numbers.

---

## v1.6.3 — Client Acceptance Revisions, Round 3 (vitals-entry error clarity, queue daily-limit enforcement, TV Display/queue realtime verification)

- Fixed a Receptionist-facing error ("Could not open this visit's consultation.") that hid the real cause — a queue ticket with no doctor assigned yet — behind one generic message for every failure. Now shows the actual, actionable reason (BUG-024).
- The per-clinic daily queue-ticket ceiling (`QueueSetting.max_daily_queue`, default 200) is now actually enforced — creating a ticket past the limit for a given prefix/day is rejected with a clear error instead of silently continuing past it (BUG-025).
- Verified live, with no code changes needed: per-prefix/per-day sequential queue numbering, Reception's existing ability to call any Waiting ticket out of order, and the TV Display's automatic instant removal of completed tickets from "Now Serving" — all confirmed already correct via a real Owner-session, two-tab (Reception Queue + public TV Display) test.
- **New: Doctor Session Control.** Doctors can now press "Start Receiving Patients" on the Doctor Workspace and use a new "Next Patient" button to auto-advance past their current patient to the next Waiting one assigned to them. New `doctor_sessions` table (migration `0021_doctor_session`); Reception's existing ability to call any patient out of order is unaffected.
- Vitals-required-before-queueing remains in progress for this round; see `docs/TESTING.md` for current status.

---

## v1.6.2 — Client Acceptance Revisions, Round 3 (sorting, messaging latency, prescription printing, discount RBAC, single-step consultation completion)

- Sortable table headers extended from Reception Queue to Doctor Workspace, Visits, and the Appointments List view.
- Internal messaging polling tightened from 30s to 3s (badge, per-conversation dropdown, and open conversation view) to hit the client's 2-3s target — no WebSocket needed for this feature's scope.
- Prescription print view now looks like a real clinic prescription pad: clinic header (name/logo/address from existing branding fields), doctor/patient details incl. age, an itemized medication list, and a signature line; added a "Half Letter / Prescription pad" paper size option.
- Investigated the "one print job per medication" report — not reproducible; prescriptions already print as a single document.
- Discount-apply/remove authority reversed for a third time: Receptionist, Cashier, Administrator, Doctor, and Owner can all apply Senior Citizen/PWD/Custom discounts (full history in `docs/TESTING.md`). Discount audit log entries now also capture the `reason` field (BUG-024).
- Removed the separate "Sign Consultation" step — completing a consultation now reaches the `Signed` state automatically in one action.

---

## v1.6.1 — Bare `/tv` Kiosk Route (zero-configuration Smart TV convenience)

- **New `/tv` route** (no slug in the URL) for single-clinic/single-TV on-prem deployments: a physical TV can just be pointed at `http://<server>/tv` with zero per-display setup. Resolves via a new `NEXT_PUBLIC_DEFAULT_TV_SLUG` frontend env var; shows a clear "No display configured" message if unset rather than crashing. The existing multi-tenant `/tv/[slug]` route is unchanged for clinics that need to pick a specific display.
- Extracted the shared realtime/announcement/fullscreen/kiosk logic into `frontend/src/features/tv-display/components/TvDisplayScreen.tsx`, used by both routes — no duplicated logic.
- New kiosk-mode behavior (both routes): best-effort `?fullscreen=true` auto-fullscreen on load (confirmed live that the actual browser Fullscreen API is blocked without a user gesture — the maximized visual layout still applies regardless), cursor auto-hide after idle, locked page scrolling, Screen Wake Lock support (feature-detected), and a `vw`/`clamp()`-based type scale verified at 1920x1080, 1366x768, and 4K.
- No backend or database changes. See `docs/BUGS.md` BUG-023 for a scoped-but-deferred follow-up (a DB-level "clinic default display" concept for multi-tenant deployments that don't want to use the env var). Verified live with a real two-tab-style real-time propagation test on the bare `/tv` route (queue ticket created + called via the real API, reflected on the already-open tab with no manual refresh).

---

## v1.6.0 — Client Acceptance Revisions, Round 3 (Messaging preserve-unread, Shift Enforcement, real TTS Queue Calling)

- **Messaging: click-to-open, per-conversation unread preserved.** New `GET /messages/unread-by-conversation` breaks the previously clinic-wide `unread-count` down per sender. The notification bell is now a real dropdown listing each unread conversation; clicking one opens `/messages?with={userId}` with that conversation pre-selected (no more manual "Select a staff member" step) and marks only that conversation read — other conversations' unread badges are untouched. Verified live with two real accounts messaging one Receptionist.
- **New: Shift Enforcement.** A Receptionist can no longer queue a walk-in, check in an appointment (both routed through the same `QueueService.create_queue`), or record a payment without a currently-open Shift (from the prior release's Shift Management feature) — blocked with a `400` reading "Please start your shift before serving patients." and, in the UI, a dialog with a "Start Shift" shortcut to `/shifts`. Does not apply to Owner/Administrator/Cashier/Doctor. Verified live: block → start shift → same action now succeeds, with no partial state left behind by the blocked attempt.
- **Audible Queue Calling upgraded to real Text-to-Speech**, replacing the prior two-tone chime: Call/Recall now speak "Now serving patient number {N}" via the Web Speech API, on the Doctor Workspace, Reception Queue, and TV Queue Display alike, with a new `/queue-announcer-settings` page (voice/rate/volume/enable-toggle, `localStorage`-backed). Overlapping announcements are cancelled before the next one speaks. **Known gap** (BUG-022, Medium): the TV Display's own speaker does not repeat an announcement for a Recall of an already-"Now Serving" ticket, since its realtime diffing only fires on genuinely new entries — the calling staff member's own device does still announce it correctly on every Call and Recall.
- No new migration — all three items are additive read/derived logic or client-side (`localStorage`) preferences.

---

## v1.5.0 — Receptionist Shift Management + Consultation Fee re-verification

- **New: Receptionist Shift Management.** A per-receptionist cash-accountability session: `POST /shifts` to start (opening cash count), a live-computed `GET /shifts/current` summary (cash/GCash/card/other collections, discounts, refunds, all derived at read time from existing `Payment`/`Discount`/`Refund` rows, never stored as a running total), `POST /shifts/{id}/close` (actual cash count → expected/actual/variance), and an Owner/Administrator-only `POST /shifts/{id}/reopen`. New `shifts` table (migration `0020_shift_management.py`, additive-only). Frontend: a new "Shift" page/nav item with a start form, live summary, close form, and a Shift Summary Report (Opening Cash / Cash Sales / Non-Cash Payments / Discounts / Expected Cash / Actual Cash / Variance, labeled Over/Short). Every open/close/reopen is audit-logged. Verified live via API, browser (real payments generated and reflected in the live summary), database, and role permissions (a Receptionist cannot view/close another receptionist's shift or reopen their own; Owner/Administrator can do both). See BUG-021 for one bug found and fixed during this same pass (a `MissingGreenlet` 500 on close/reopen, fixed before shipping).
- **Re-verified (no code changes): Consultation Fee override**, from an earlier phase — a Doctor-entered fee at `POST /consultations/{id}/complete` correctly flows into the auto-created invoice's line item ahead of `Doctor.consultation_fee`/`ClinicService.default_price`. Confirmed live: exact amount flows through to the invoice, Receptionist is blocked (`403`) from editing the resulting line item's price, Cashier is not (documented as the existing, intentional general billing-edit capability, not a bug specific to this fee), and the invoice-creation audit log is correctly attributed to the completing Doctor.

---

## v1.4.0 — Client Acceptance Revisions, Round 2

A follow-up bounded fix/change list from the same UAT round as v1.3.0 — no new modules, no new migration.

- **Critical: TV Queue Display bug fixed.** The public TV Display could show an empty queue despite real, active tickets — root cause was a naive, OS-local `date.today()` filter in `TvDisplayService` inconsistent with the UTC-based "today" used everywhere else in the codebase. Fixed to use `datetime.now(UTC).date()` consistently. Verified live end-to-end, including a two-tab test proving the WebSocket real-time update path (Doctor Workspace Call/Recall → TV Display, no manual refresh). See BUG-020.
- **Critical: discount authority reversed** from Receptionist back to Doctor, and a discount-*removal* endpoint/workflow was added (previously only "apply" existed). See BUG-019.
- **High: Printer Settings** — a per-browser paper-size (A4/Letter/Thermal 80mm, applied via real print CSS) and default-printer preference, plus a print preview added to the existing Prescription/Laboratory Request/Referral print dialog. Browser printer-selection limitations are explicitly documented, not silently glossed over.
- **Medium: Queue Table sorting** — sortable Queue #/Patient/Department/Created columns on the Reception Queue list.
- **Medium: messaging unread-count badge** — the existing unread-count endpoint now drives a visible top-nav badge.
- No new Alembic migration required for any item in this release.

---

## v1.3.0 — Client Acceptance Revisions (Phase 20)

A bounded, client-approved list of RBAC and workflow changes discovered during the v1.2.0 UAT — no new modules, all built on existing Phase 8/9/10 infrastructure.

- **Two Critical billing bugs fixed**: Receptionist was getting `403` on "Apply Discount" and "Record Payment" — root cause was a role-permission gap (`BILLING_MANAGE_ROLES` never included Receptionist), not a logic bug. Since the client wants Receptionist to have this capability now, fixed by splitting the shared dependency into `require_billing_discount_role`/`require_billing_payment_record_role` (now including Receptionist) and a separate, unchanged `require_billing_void_role` (still Cashier/Owner/Administrator only) so voiding a payment remains restricted. See BUG-018.
- **Receptionist gains a narrowly-scoped clinical capability**: can now enter ONLY the Subjective and Objective/vitals sections of a visit's SOAP note (a deliberate, client-requested reversal of Phase 8's "Reception cannot touch SOAP" rule), via a new "Enter Vitals" action on the Reception Queue screen. Assessment, Plan, and completing/signing a consultation remain Doctor/Owner/Administrator-only — enforced at the schema level (the new restricted endpoint's request body has no Assessment/Plan fields at all) as well as the role-gate level. The Doctor's existing SOAP UI automatically shows and can overwrite whatever Reception entered — no doctor-side code changes were needed.
- **Doctor can now override the consultation fee at completion time**: `POST /consultations/{id}/complete` accepts an optional fee that flows straight into the auto-created invoice, ahead of the existing `Doctor.consultation_fee`/`ClinicService.default_price` pricing tiers. Omitting it preserves prior pricing behavior exactly.
- **Printable Prescription, Laboratory Request, and Referral views**, following the same `window.print()` + print-CSS pattern already used for Billing receipts — no new PDF library introduced.
- **Full RBAC cross-role verification** performed with real tokens after the above landed: Receptionist's new capabilities are confirmed narrowly scoped (still blocked from completing consultations, setting Assessment/Plan, voiding/refunding payments, and Administrator-only pages); Doctor/Cashier/Administrator boundaries from prior phases are unchanged.
- **Audible Call/Recall cue**: a single Web Audio API two-tone chime on a successful Call/Recall in the Doctor Workspace.
- **PWA installability**: manifest + minimal pass-through service worker (no offline support).
- **Receptionist ↔ Doctor internal messaging**: a minimal staff-to-staff direct message list (new `internal_messages` table, migration `0019_internal_messaging.py`), polling-based, no threads/attachments/group chat.
- No new Alembic migration was required for items 1-11 — the consultation fee override is passed through in-request rather than persisted on the `Consultation` row. Item 14 (messaging) adds the one new migration for this release.

---

## v1.2.0 — Patient Self-Service Appointment Booking (Phase 19)

Extends the Patient Portal (v1.1.0) with a real booking flow, built entirely on top of the existing Phase 11 appointment engine — no new booking logic, no separate patient-appointments table.

- **New patient-facing endpoints** under `/api/v1/patient-portal/appointments/...`: reference-data reads (branches/departments/doctors), availability (date-range and single-date), create, reschedule, cancel — all behind `get_current_patient`, every write scoped to the caller's own `patient_id` from the JWT, mutations `404` (not `403`) on another patient's appointment.
- **Race-condition safety**: two concurrent bookings for the same doctor/date/time cannot both succeed — enforced by the Postgres partial unique index `uq_appointments_doctor_slot_active` (present since Phase 11's migration 0012, now also declared in the SQLAlchemy model so test databases have it too), with the service layer translating the resulting unique-violation into a clean `409`. Proven by a real concurrent-request test firing two simultaneous requests via `asyncio.gather` against independent DB sessions — passed 6/6 consecutive runs.
- **New migration** `0018_patient_appointment_booking.py`: adds `appointments.booking_source` (`Staff`/`Patient`, indexed) to distinguish provenance.
- **Reception integration verified live**: a patient-booked appointment shows up immediately in the existing staff search (by reference number, patient name, doctor, or date) and staff check-in continues to auto-create a linked Queue ticket + Visit exactly as for a staff booking — zero staff-side code changes needed, confirmed via curl against the real dev database.
- **Frontend**: a 7-step booking wizard (Branch → Department → Doctor → Type → Date → Time → Confirm) at `/patient-portal/appointments/book`, plus Reschedule/Cancel actions on the existing Appointments list, plus a "Book Appointment" entry point on the Dashboard and Appointments pages.
- **Audit**: Created/Rescheduled/Cancelled events logged via the existing `AuditLog` model, attributed to the patient (`user_id = None`, `metadata.principal = "patient"`), matching Phase 18's established pattern.
- **Four real bugs found and fixed live during this phase** (see `docs/BUGS.md` BUG-010 through BUG-013): a doctor-picker filter that excluded every doctor without an explicit branch/department assignment; a missing import that silently broke the reschedule endpoint under Python 3.14's lazy annotation evaluation; the double-booking unique index missing from the test-database schema; and a first-of-day appointment-number-counter race. Two items deferred as out of scope (BUG-008: no Service-selection step in the given wizard order, so check-in requires reception to add one first; BUG-009: the pre-existing staff-facing reschedule path lacks the same concurrency handling added to the patient-facing one).
- **Explicitly out of scope for this phase** (per spec): online payment, SMS/email reminders, teleconsultation, an AI assistant.

---

## v1.1.0 — Patient Portal (Phase 18)

A new business feature phase following the v1.0.0 commercial release: a self-service Patient Portal, built as a THIRD structurally separate principal/auth model alongside clinic staff (`users`) and Phase 15's SaaS Administration Portal (`platform_admin_users`).

- **New patient auth model**: `patient_accounts` (one-to-one with `patients`), a JWT with a distinct `"type": "patient_access"`/`"patient_refresh"` claim, and a new `get_current_patient` FastAPI dependency — verified mutually rejected against the clinic-staff and platform-admin auth chains in both directions.
- **Patient-facing features**: login (email or mobile + password), forgot/reset password, dashboard (appointments/visits/balance/labs/prescriptions), profile + photo upload stub + notification preferences, view-only appointments (tabbed by status), view-only Released-only laboratory results, view-only prescriptions (current vs. past), read-only medical records (only clinician-opted-in diagnoses/attachments via new `patient_visible` columns), read-only billing/invoices/payment history, and an in-app notification feed.
- **New migration** `0017_patient_portal.py`: `patient_accounts`, `patient_password_reset_tokens`, `patient_notification_preferences`, `patient_notifications`, plus additive `patient_visible` (default `false`) columns on `diagnoses` and `consultation_attachments`.
- **Security**: every patient login and profile change is audit-logged; a real cross-patient and cross-clinic isolation test suite (`backend/app/tests/test_patient_portal.py`, 8 tests) proves Patient A's token cannot read Patient B's data and is rejected by every clinic-staff/platform-admin route.
- **New frontend portal**: `frontend/src/app/patient-portal/` — its own layout, login page, and token-storage keys, protected by its own `middleware.ts` branch, verified responsive at mobile/tablet/desktop widths.
- **Explicitly out of scope, architecture notes only**: OTP/social login, online appointment booking, online payments, teleconsultation, AI assistant.

## v1.0.0 — Commercial Release

Release-preparation milestone immediately following Phase 17, not a new feature phase — no new business features were added. Full detail in [`RELEASE_NOTES_v1.0.0.md`](RELEASE_NOTES_v1.0.0.md).

- Re-verified every module's core happy path via live API calls against the running dev stack: Auth, Users, Patients, Clinic Config, Reception/Queue, Visits, Doctor Workspace, Consultation/SOAP, Orders, Prescriptions, Laboratory, Billing, Appointments, TV Queue Display, Migration Wizard, SaaS Admin Portal, and the `/health`/`/live`/`/ready` probes — no regressions found.
- Found and fixed two genuine release-blocking defects: unescaped apostrophes in `doctor-schedules` and `doctor-workspace` pages were failing the Next.js production build's ESLint gate. These were the only code changes made this release.
- Confirmed zero Open Critical/High bugs in `BUGS.md` (all currently open items are Medium/Low with documented workarounds).
- Confirmed the Alembic migration chain (`0001` → `0016`) applies cleanly end-to-end on a fresh, disposable database, and that `frontend`'s production build succeeds.
- Version bumped to `1.0.0` across `backend/pyproject.toml`, `frontend/package.json`, `backend/app/main.py`, and a new root `VERSION` file.
- New docs: `INSTALL.md`, `CHANGELOG.md`, `RELEASE_NOTES_v1.0.0.md`, `DEPLOYMENT_PACKAGE.md`, and a rewritten root `README.md`.
- **Not done, and not claimed to be done**: no real git tag (not a git repository), no real CI/CD pipeline execution, no real Docker image build/push, no real cloud deployment, no real customer onboarding — see `RELEASE_NOTES_v1.0.0.md` §9 for the full honest scope statement.

## v0.17.0 — Pilot Deployment & User Acceptance Testing (Phase 17)

> **Numbering note**: an older entry further down this file is also
> labeled "v0.17.0 (Phase 9's-era numbering — Billing & Cashier)". That's
> a pre-existing inconsistency from this doc having two historical
> numbering passes merged together (the "(Phase N)" suffixes below don't
> always match `ROADMAP.md`'s own phase numbers either — see that file's
> own "Phase 17 — Billing & Cashier" section for the same collision).
> Neither existing entry has been renumbered or altered; this new entry
> is simply the actual latest release, chronologically following
> **v0.16.0 — Production Hardening**, the version this phase started
> from.

The first phase that is deliberately **not** about new business
features — it verifies deployment readiness, exercises the Phase 14
Legacy Migration Wizard end-to-end with a real sample dataset, runs a
full scripted patient-journey UAT against the live dev servers, and
writes up an honest Pilot Readiness Report distinguishing "the scripted
technical walkthrough passed" from "a real clinic team signed off":

- **Deployment readiness reviewed, not newly deployed**: `.env.example` completeness (backend + frontend), database/migration state, file storage config, background jobs, logging/monitoring, and the Phase 16 backup mechanism were all re-verified against the running dev stack. No real cloud host was provisioned this phase — see `docs/PILOT_READINESS.md` for exactly what a real production cutover still needs.
- **A real pilot tenant** ("Pilot Community Clinic") was created and fully configured via live API calls — branch, departments/services (seeded defaults), a doctor with a weekly schedule, operating hours, queue settings + priority types, a Doctor-role staff login — every resource verified by reading it back, not assumed from the request that created it.
- **Legacy Migration Wizard exercised hands-on** with a realistic 5-patient/2-doctor CSV sample deliberately missing a `civil_status` column (a common real-world legacy-export shape). This surfaced and led to fixing a real **High-severity bug**: resolving a validation Error (`Merge`/`Overwrite`/`CreateNew`) had no effect — the row was still force-skipped and miscounted as a "duplicate" in the batch summary, because the import/preview logic checked an issue's `severity` but ignored its `resolution` entirely. Fixed in `backend/app/services/migration/migration_service.py`; re-verified live — all 5 patients + 2 doctors imported correctly, confirmed via the Verification Report and `GET /patients`. See `docs/BUGS.md` BUG-001.
- **Full scripted UAT of the patient journey** — Registration → Appointment → Check-in → Queue (Call/Start-Consultation) → Consultation (SOAP) → Clinical Order (Laboratory) → Prescription → Consultation Complete (auto-invoice) → Laboratory (collect/process/results/release) → Billing (payment, split-payment-capable) → Receipt → Completion (Visit reaches `Completed`) — **17/17 steps passing**, driven by real HTTP calls against a live backend instance, not mocked. Full step-by-step results in `docs/PILOT_READINESS.md`.
- Two Medium/Low findings logged (not fixed, per this phase's fix-only-Critical/High rule): a silent no-op when a Visit's completion-sync is attempted before it's been progressed through the Queue's Call/Start-Consultation actions (BUG-002), and no self-service way to link a Doctor-role user account to its Doctors master-data record (BUG-005). Both have documented workarounds.
- New docs: `docs/PILOT_READINESS.md`, `docs/USER_MANUAL.md`, `docs/ADMINISTRATOR_GUIDE.md`, `docs/SUPPORT_GUIDE.md`. `docs/DEPLOYMENT.md`/`docs/MIGRATION.md`/`docs/BACKUP.md` (built in earlier phases) reviewed and found still accurate, with a short Phase 17 verification note appended to `docs/MIGRATION.md`.
- **Explicitly not done, and not claimed to be done**: no real user training sessions were run, no real human sign-off was collected from Reception/Doctor/Laboratory/Cashier/Administrator/Owner roles, and no real production deployment happened. `docs/PILOT_READINESS.md` lists these as explicit next steps for the real clinic team.

## Known Issues (as of v0.17.0)

See `docs/BUGS.md` for full entries and severities. Open, not fixed this
phase (all have documented workarounds or are informational):

- Visit-completion sync is a silent no-op if a Visit is never progressed through the Queue's Call/Start-Consultation actions before the consultation is completed (Medium — BUG-002).
- The Legacy Migration Wizard only actually imports Patients and Doctors; 15 other entity types are mapping/validation-ready but intentionally skipped on import — a pre-existing Phase 14 scope decision (Low — BUG-003).
- Running `pytest` in this sandboxed dev environment currently fails on an `argon2` memory allocation error unrelated to application code (Low — BUG-004).
- No self-service way to link a Doctor-role User account to its Doctors master-data record; requires a direct database update today (Low — BUG-005).

## v0.9.0 — Clinical Orders & Prescriptions (Phase 9)

Lets a doctor record Laboratory/Radiology/Vaccination/Custom orders, Procedures, Referrals, and Prescriptions during an in-progress consultation, built on top of Phase 8's Consultation the same way Diagnosis was:

- New `orders`/`order_items`, `procedures`, `referrals`, `prescriptions`/`prescription_items` tables (migration `0009_clinical_orders_prescriptions.py`, revision id `0009_clinical_orders`). `ORD-YYYYMMDD-000001`/`RX-YYYYMMDD-000001` numbering, concurrency-safe like every other generator in this codebase.
- **Design decision**: Procedures and Referrals are their own tables, not `orders` rows — the spec lists them as standalone top-level tables and Procedures has no Order Number field. The Consultation page's "Clinical Orders" tab unifies all three into one view.
- **Non-blocking prescription validation**: duplicate medicine / missing dosage / missing duration surface as warnings alongside a successful save, never blocking it — verified live with a deliberately-missing-dosage item. Allergy-conflict checking is an architecture-only placeholder (no drug database yet).
- **The Phase 7/8 lesson applied again**: creating an order/procedure/referral/prescription doesn't change Consultation/Visit status, but every creation writes a timeline event + audit entry so it's correctly visible in the Visit's Orders/Prescription tabs, Timeline, and Patient Profile — verified live via curl, not just unit tests.
- Role gating: assigned doctor edits; Owner/Administrator view-only; **Receptionist read-only**; new **Laboratory** role scoped to Laboratory-category orders only, no access to Prescriptions/Procedures/Referrals.
- Frontend: real Orders/Procedures/Referrals forms and Prescription repeatable line-item form (with inline warnings and a static common-medicines autocomplete) on the Consultation page, read-only Orders/Prescription tabs on Visit Details, and a real Prescriptions view on Patient Profile — all previously placeholders.
- Migration-slot note: this phase and the concurrently-developed Billing & Cashier phase both initially targeted migration slot `0009`; Clinical Orders kept `0009`, Billing was renumbered to `0010`.
- Explicitly out of scope: Billing, Cashier, Laboratory/Radiology *processing* (result entry, specimen tracking), Appointments, TV Display.

## v0.10.0 — Laboratory Management (Phase 10)

The laboratory department's own workflow layered on top of Phase 9's doctor-facing Laboratory-category orders: collection, processing, multi-parameter result entry, and release, plus a configurable test/pricing/reference-range template catalog:

- New `laboratory_orders` (1:1 with a Phase 9 `Order`), `laboratory_results`, `laboratory_attachments`, `laboratory_templates`/`laboratory_template_parameters` tables (migration `0011_laboratory_management.py`).
- **Design decision**: a new `laboratory_orders` table with a 1:1 FK to the existing Phase 9 `orders` row, not an extended `orders` table — keeps the six-value lab-specific status enum (including a terminal `Released` state) off the shared multi-category `orders` table, while reusing `orders.order_number` so there's only one numbering scheme.
- Creating a Laboratory-category order (unchanged Phase 9 endpoint) automatically attaches a `laboratory_orders` workflow record, best-effort matched to a configured template by test name — zero extra doctor-facing steps.
- **The Phase 7/8/9 lesson applied a fourth time**: every lab-workflow transition mirrors onto the underlying Phase 9 `Order.status`, so the Consultation page's Orders tab reflects lab progress instead of staying stuck on `Requested` forever — a real instance of this exact bug class was found and fixed live during this phase.
- **Idempotent billing integration**: completing a template-priced lab order automatically adds/updates an invoice line item via the same auto-invoice path Consultation-completion uses. A real cross-order id-collision bug (two same-named lab orders on one visit briefly shared an `invoice_item_id`) was found and fixed live, with a dedicated regression test.
- Role gating: Laboratory role (+ Owner/Administrator) collects/processes/enters-results/releases/cancels; Doctor still only creates orders; Receptionist read-only; Administrator/Owner-only template mutation.
- Frontend: a Laboratory Dashboard (stat cards + status-contextual worklist), a multi-parameter Result Entry dialog, a real Visit Details "Laboratory" card, a real Patient Profile "Laboratory" tab, and an Administrator-only Laboratory Test Templates admin page — all previously placeholders or non-existent.
- Explicitly out of scope: Pharmacy, Appointments, TV Display, Patient Portal, Reports.

## v0.11.0 — Appointment Management (Phase 11)

Full appointment booking lifecycle (Booked → Confirmed → Checked-in → Queue Generated → Visit Created → Doctor Consultation → Billing), built on top of Phase 4's `doctor_schedules` availability configuration and reusing Phase 5/6's queue/visit creation flow for check-in — the phase with the most cross-entity integration points of any so far:

- New `appointments`, `doctor_schedule_blocks`, `appointment_reminders`, `appointment_notes`, `appointment_history`, `waitlist_entries` tables plus `doctor_schedules` extended in place with lunch-break/slot-duration/daily-cap/recurring-override columns (migration `0012_appointment_management`). `APT-YYYYMMDD-000001` numbering, same concurrency-safe generator pattern as every prior phase.
- **Time Slot Engine**: available slots are computed on demand from the doctor's weekly schedule minus lunch break minus existing bookings minus holidays minus blocked/vacation dates, and never persisted — `TimeSlot` is a computed schema, not a table (see `docs/DATABASE.md` for the staleness rationale).
- **Check-in → Queue → Visit, addressed by design rather than found as a live bug this time**: `check_in_appointment` calls the existing `QueueService.create_queue()` (an additive, backward-compatible `visit_type` kwarg) instead of reimplementing queue/visit creation — verified live in the browser (Appointments page → Check In → the ticket appears on the Reception Queue screen and the linked Visit appears on the Visits list, tagged `Appointment`, in the same page load).
- Reschedule creates a fresh `Booked` row and marks the original `Rescheduled`, recording old/new date-time in `appointment_history`; cancel offers the freed slot to the oldest matching waitlist entry (a real state change, no notification sending — that stays out of scope).
- Role gating: Reception (+Owner/Administrator) create/edit/reschedule/cancel/check-in; Doctor completes/no-shows; doctor schedule administration Administrator-only.
- Frontend: Appointment Dashboard (`/appointments` — search/filter, New Appointment dialog reusing the Queue feature's patient-search pattern plus a live slot picker, status-contextual actions), an Appointment Details dialog with history, a real Patient Profile "Appointments" tab (previously a placeholder), Sidebar nav entry.
- Calendar (Day/Week/Month/Agenda, dependency-free React/CSS grid, Doctor/Department/Branch/Type filters) as a List/Calendar toggle on the Appointment Dashboard, and a Doctor Schedule admin page (`/doctor-schedules`) for working hours/lunch/slot-duration/max-per-day plus vacation/blocked dates — both wired to already-verified backend endpoints and confirmed live (editing a doctor's hours on the admin page immediately changes the slots the booking dialog offers).
- Explicitly out of scope: actual SMS/Email/Push sending, Teleconsultation video, Patient Portal, TV Display.

## v0.12.0 — Owner Dashboard & Reports (Phase 12)

A read-only aggregation/reporting layer over every operational table built so far (Patients, Visits, Queues, Invoices, Payments, Laboratory Orders, Appointments, Prescriptions, Consultations) — no new tables, no duplicated business logic:

- **No migration** — `alembic heads` stays at `0012_appointment_management`. Every metric is a real SQL `COUNT`/`SUM`/`AVG`/`GROUP BY` aggregation, reusing an existing repository method where one already existed from an earlier phase's dashboard (e.g. `InvoiceRepository.sum_todays_revenue` from Phase 9's Cashier Dashboard) and adding new aggregation methods to the *existing* repository that owns each table otherwise — see `docs/DATABASE.md`'s Phase 12 section for the full map.
- `GET /analytics/dashboard`: 16-stat Owner Dashboard (Patients/New Patients/Appointments/Walk-ins Today, Completed Consultations/Cancelled Visits/No Shows, Laboratory Orders/Prescriptions Issued, Pending Payments, Collected Revenue Today, Outstanding Balance, Avg Waiting/Consultation Time, Doctors On Duty, Rooms In Use).
- `GET /analytics/activity-feed`: merges and sorts `visit_timeline_events` + `queue_status_history` + `audit_logs` — a real queried feed, not a new event-logging mechanism.
- `GET /analytics/alerts`: live threshold checks (High Queue Volume, Long Waiting Time, Outstanding Payments) computed on request; System Errors/Failed Backups explicitly out of scope pending a future infra-monitoring phase.
- Six report endpoints (Patient/Doctor/Revenue/Queue/Laboratory/Appointment) with a shared `date_range` filter (`today`/`yesterday`/`last_7_days`/`this_month`/`last_month`/`custom`) plus optional `doctor_id`, and chart-ready `{label, value}` series for every trend.
- **Cross-checked live, matching the spec's explicit acceptance bar**: "Collected Revenue Today"/"Outstanding Balance"/"Pending Payments" match `GET /billing/dashboard` exactly; the Patient Report's `total_visits` for a day matches `GET /visits?date_from=...&date_to=...`'s `total` exactly.
- Export: real working CSV, Excel-compatible reuse of the same CSV body, and an explicit `501 Not Implemented` stub for PDF per the spec's "do not implement PDF styling yet" exclusion.
- Role gating: **Owner and Administrator only** — the simplest, strictest gate in the project; every other role 403s on every `/analytics/*` endpoint, verified for Doctor/Cashier/Receptionist/Laboratory.
- Report-generation audit reuses the existing `audit_logs` table (`action = "analytics.report_generated.<report>"`) rather than a new `report_generation_log` table.
- Frontend `features/analytics/`: Owner Dashboard page (`/analytics`, Sidebar entry shown only to Owner/Administrator, backend still enforces `403` regardless), a grouped stat-card grid, the live Activity Feed, an Alerts banner, and six report sections with date-range filters and zero-dependency inline-SVG bar/line charts (no charting library added — consistent with the project's dependency-free convention). No direct mutations of its own, so staleness is handled by a 30s `refetchInterval` + `refetchOnWindowFocus` polling policy rather than mutation-driven cache invalidation.
- Explicitly out of scope: TV Display, Patient Portal, Migration Wizard, Production Deployment, real PDF export styling.

## v0.13.0 — Live TV Queue Display (Phase 13)

A fullscreen, unauthenticated waiting-area display reading the same realtime queue channel Reception has used since Phase 5, built for continuous kiosk use (Android TV browser, 1080p/4K landscape):

- New `tv_display_configs`/`tv_announcements` tables (migration `0013_tv_queue_display`, `alembic heads` stays linear). Each config narrows scope via nullable `branch_id`/`department_id`/`doctor_id` (clinic-wide → branch → department → doctor; a "Waiting Area TV" is just a branch-scoped config with no department/doctor); `is_public` + a unique 192-bit `public_slug` control the no-auth-required public URL.
- **The most architecturally significant decision in this phase**: the public display authenticates its WebSocket connection to the *existing* `/ws/queues/{clinic_id}` channel (unchanged from Phase 5/7) using its `public_slug` as the `token` query param, in place of a JWT — `ws_queues.py`'s handshake now accepts either credential type, resolving a slug to its own `clinic_id` via `TvDisplayConfigRepository.get_by_public_slug` (which already enforces `is_public`/`is_active`/`is_deleted`) rather than trusting the `{clinic_id}` path segment. This reuses the exact secret-token-as-credential model the public HTTP endpoint already has instead of minting short-lived JWTs for anonymous kiosks; revoking a display is just deactivating its config row.
- `GET /public/tv-display/{public_slug}` takes **zero Authorization header** — verified with an explicit pytest asserting no header is sent, and live via curl. Returns Now Serving + Next N Waiting (patient **initials only**, derived server-side, never a full name) + announcements, filtered to `ACTIVE_QUEUE_STATUSES` (Completed/Cancelled/Skipped/NoShow never appear) and to the config's branch/department/doctor scope. An unknown/private/inactive slug 404s cleanly, never a 500 or another clinic's data — tenant isolation covered by a dedicated cross-clinic test.
- **Realtime strategy**: rather than trying to patch state from each WS event's partial payload, the display re-fetches the full snapshot on *any* `queue.*`/`visit.*` event — simpler and always correct given the extra client-side filtering/truncation (queue_size, ordering, ACTIVE_QUEUE_STATUSES) the display needs beyond what a single event carries.
- **First reconnect-with-backoff logic in the project**: the existing Phase 5 `useQueueRealtime` hook has no reconnect logic at all (relies solely on a 30s poll fallback). This phase's `useTvDisplayRealtime` adds a real exponential-backoff reconnect state machine (unit-tested in isolation) plus its own poll fallback — verified live by killing and restarting the backend with the display tab open and confirming it recovers with zero manual reload.
- Text-to-speech: **architecture only** — `tts_enabled`/`tts_template` columns plus a real string-templating `generate_announcement_text()` in `services/tts_service.py`; no audio synthesis is implemented, by design.
- Frontend: a standalone `/tv/[slug]` route outside both the `(auth)` and `(dashboard)` route groups (no sidebar/topnav, no session required), large high-contrast typography, a live clock/date, a scrolling announcement ticker, a fullscreen toggle, an unobtrusive connection-status indicator, and a Web-Audio-generated notification beep gated behind a one-time "Enable Sound" tap (autoplay-audio policy compliant). A `TvDisplayConfig` gap: `Queue`/`Visit` have no FK to `ConsultationRoom` yet, so "Room" is omitted from the display rather than guessed at — documented in `DATABASE.md`.
- Owner/Administrator-only admin UI under a new "TV Displays" sidebar entry: create/edit/delete display configs and manage per-display or clinic-wide announcements.
- **Bug found (not fixed, out of scope) while writing this phase's tests**: `VisitCounter` is scoped per (clinic, branch, date) but the generated `visit_number` string has no branch component and is unique only per (clinic, visit_number) — two different branches' same-day counters can both produce `VIS-YYYYMMDD-000001` and collide. Flagged in `docs/TESTING.md`; a Phase 6/11 issue, not introduced by this phase.
- Explicitly out of scope: Migration Wizard, Patient Portal, Production Deployment, real TTS audio synthesis.

## v0.14.0 — Legacy Migration Wizard (Phase 14)

The payoff for the `LegacyMixin` columns every entity table has carried since Phase 5 — a real, resumable, idempotent import engine plus a step-by-step wizard, Owner/Administrator only:

- New `migration_batches`/`migration_entity_progress`/`migration_field_mappings`/`migration_validation_issues`/`migration_logs` tables (migration `0014_legacy_migration_wizard`). These meta/process tables intentionally do not carry `LegacyMixin` themselves (documented in the migration's docstring) but do carry `TenantMixin` + timestamps.
- **Audit finding, fixed in the same migration**: `branches`/`departments`/`doctors`/`services` were missing the `LegacyMixin` columns every other entity table already had — backfilled additively before building the import engine.
- **Source scope decision**: CSV and Excel are the only fully-working adapters (stdlib `csv` + `openpyxl`) since no specific legacy client database technology has been identified yet; SQLite/Access/SQL Server/MySQL/PostgreSQL get a real `SourceAdapter` interface + registry, but raise `NotImplementedError` pointing at the CSV/Excel path.
- **Idempotency**: `legacy_id` + `migration_batch_id` (already on every entity table) are looked up before every insert — no separate `sync_hash` column. Proven with a real double-import test (pytest and live curl): the same batch re-run creates zero new rows, including with the resume offset manually reset to force a full re-scan.
- Mapping engine with real fuzzy/synonym matching (e.g. `FName` → `first_name`) and three real transforms (DateFormat/PhoneFormat/Trim). Validation reuses Phase 3's Patient duplicate-detection pattern (name+DOB or mobile) plus required-field/date/phone/email checks reusing the Patient/User schema validators.
- Import engine processes the mandated 17-step entity order in batches of 500 rows per DB transaction (rollback-on-failure), via `BackgroundTasks`, with a live-polling Migration Dashboard (Status/Source/Found/Imported/Duplicates/Warnings/Errors/Elapsed/ETA) and a persisted Verification Report.
- **Entity scope decision**: only Patients and Doctors write to a real destination table in this phase (via `PatientService.create_patient` / a direct `Doctor` create with legacy fields populated); the other 15 entity types get full schema-analysis/mapping/validation support but are marked `Skipped` with an explanatory log entry during import — see `docs/MIGRATION.md`.
- Frontend `/migration` (Owner/Administrator-only, new Sidebar entry): 8-step wizard (Choose Source → Connect → Analyze → Map Fields → Preview → Validate/Resolve Issues → Import → Verify) plus Migration History.
- Explicitly out of scope: production deployment; fully-working non-CSV/Excel adapters (architecture only); importing the 15 non-Patient/Doctor entity types end-to-end.

## v0.15.0 — SaaS Administration Portal (Phase 15)

A second, structurally separate portal for CONNECT.PH platform staff, granting real cross-tenant access for the first time without weakening tenant isolation for any existing clinic-scoped role:

- New `platform_admin_users` (no `clinic_id` — a structurally separate user model from `users`), `tenant_feature_flags`, `platform_audit_logs`, `platform_sessions`, `background_jobs`, `platform_config`, `api_keys`/`oauth_clients`/`webhook_secrets`, `backups` tables (migration `0015_saas_administration`); extended `clinics` (suspend/archive lifecycle) and `subscriptions` (trial/renewal/license-limit fields).
- **Core architecture decision**: a fully separate JWT claim shape (`app/core/platform_admin_security.py`) and a fully separate dependency chain (`get_current_platform_admin`) — never layered on top of `get_current_user`/`require_roles`. Verified live both directions: a Platform Administrator's token gets a clean 401 on every existing clinic-scoped endpoint, and a regular clinic Owner/Doctor's token gets a clean 401 on every `/platform-admin/*` endpoint. Full rationale in `docs/ARCHITECTURE.md` §7.
- **Tenant management**: cross-tenant list/search/create/suspend/reactivate/archive; suspending force-logs-out every user in that clinic and blocks further logins (`AuthService.login` now checks `clinic.status`).
- Subscription/license management, feature flags (8 keys, one — Appointments — wired into a real clinic-facing check as proof of concept), tenant user administration (reset password/lock/unlock/force-logout, reusing Phase 2's account-lockout machinery), System Health dashboard (real Postgres aggregation including `pg_database_size()`), platform audit log.
- Four platform roles with a documented read/write matrix (PlatformAdministrator/SupportEngineer/ImplementationTeam/Auditor — Auditor is read-only everywhere).
- Frontend `app/platform/`: a genuinely separate portal (own layout/branding/login page), distinct token-storage keys and middleware-protection logic from the clinic portal, Platform Dashboard + Tenant Management pages wired to the real API.
- 13 new backend pytest tests (cross-tenant visibility + isolation preservation in both directions is the centerpiece) and 11 new frontend Vitest tests (token/cookie separation, tenant search, feature-flag toggle logic).
- Explicitly out of scope: real payment-gateway billing/automated charging; Patient Portal/Teleconsultation/AI Assistant/Inventory (flags are placeholders only); API-key-based endpoint authentication; real email/SMS/AI/storage provider integration; a real `pg_dump`-backed backup (documented stub — unavailable in this dev sandbox) and real restore (architecture-only); exhaustive feature-flag retrofitting (only Appointments wired).

## v0.16.0 — Production Hardening (Phase 16)

A cross-cutting, evidence-first hardening pass across the whole codebase rather than a new feature module — real analysis first (`EXPLAIN ANALYZE`, FK-index grep, live endpoint timing), then fixes for what the analysis actually found, prioritized by risk/value rather than a generic checklist:

- **Database**: migration `0016_hardening_indexes.py` adds indexes for genuinely-confirmed-missing cases only — `laboratory_orders.branch_id`/`.doctor_id` (every sibling FK had one, these didn't), and composite `(clinic_id, status)`/`(clinic_id, invoice_date)` on `invoices`/`laboratory_orders` (repositories already filter these together; the codebase's existing single-column indexes made Postgres do an extra row-level filter). Honest finding: the real dev dataset is too small for a measurable before/after speedup — no fabricated numbers reported.
- **Observability**: `/live` (liveness, zero dependencies) and `/ready` (readiness, real `SELECT 1`, `503` on DB failure) added alongside the existing `/health`; the Phase 1 request-logging middleware extended with a UUID request-id, returned as `X-Request-ID` and included in every structured log line; a standardized `{"detail", "request_id"}` error envelope across every FastAPI exception handler (`HTTPException`/validation/`500`).
- **Security review**: CORS and rate-limiting reviewed and re-confirmed correct (no changes needed — both already sound); a real file-upload validation gap found and fixed in consultation/laboratory attachment presigned-URL requests (previously zero server-side extension/size checking) and in the legacy migration wizard's real file-relay upload endpoint (previously zero size/extension checking on real bytes written to disk); SQL-injection surface spot-checked with no issue found (SQLAlchemy parameterized queries throughout); secrets/`.env.example` spot-checked with no issue found.
- **Caching**: a simple in-process TTL cache (`app/core/cache.py`, following the same Redis-fallback convention as Phase 2's rate limiter) wired into the departments list and feature-flag checks, with real invalidation on every mutating call — verified live and in pytest that an edit is reflected on the very next read, not after the TTL window.
- **Backup verification**: Phase 15's previously-bare `backups` table now has a real service behind it — an actual `pg_dump` is run, the output verified (non-empty, real PostgreSQL dump header), and the outcome recorded honestly (`Completed`/`Failed` with a real error message). New `docs/BACKUP.md` documents a human-executable restore procedure — restore itself stays intentionally unautomated.
- **Load testing**: a real, runnable `backend/scripts/load_test.py` fires concurrent logins and queue-ticket creations against a dedicated, cleaned-up synthetic test tenant — real numbers reported in `docs/TESTING.md` (queue-ticket creation: 20/20 succeeded at concurrency 20, p50 686.7ms/p95 991.4ms; the login rate limiter correctly rejected logins beyond its configured burst limit, confirming it works under real concurrent load, not a bug).
- **Cross-browser/accessibility**: a real, bounded pass using the one browser engine available in this sandboxed environment — documented honestly as a partial check (accessibility-tree roles/labels confirmed present; real screen readers, real cross-browser engines, real mobile devices, and measured contrast ratios are explicitly out of reach here and tracked as a follow-up checklist in `docs/TESTING.md`, not falsely claimed as covered).
- 11 new backend pytest tests (`test_production_hardening.py`, all passing against `connectph_clinic_test`); full regression check with the real seeded logins across every prior phase's core endpoints, all still `200`.
- Explicitly out of scope, per the phase's own scope boundary: rewriting frontend bundling/code-splitting without a measured problem; database schema restructuring beyond additive indexes; business-logic changes to any of the 15 preceding feature modules.

## v0.17.0 — Billing & Cashier (Phase 17)

Turns a completed Consultation into a billable, payable, receiptable encounter, built on top of Phase 6's Visit and Phase 8's Consultation:

- New `invoices`/`invoice_items`/`invoice_counters`/`discounts`/`payments`/`refunds` tables (migration `0009_billing_cashier`). `INV-YYYYMMDD-000001` invoice numbering, concurrency-safe like every other number generator in this codebase.
- **Consultation → Invoice sync**: completing a consultation now auto-creates a Draft invoice with a priced Consultation Fee line item (idempotent — a repeat complete() call never creates a duplicate), mirroring the same call-into-each-other pattern `VisitService`/`QueueService` already use.
- **Payment → Visit sync**: an invoice reaching Paid transitions the linked Visit to Completed if not already terminal — the spec's "Visit Closed" workflow step — verified live via curl (Cashier login → apply discount → split payment → confirm Visit status).
- Split payments (multiple payment rows per invoice, summing to no more than the balance due), void-payment recomputes status backward from the remaining Completed payments rather than a naive decrement.
- Role gating: Cashier + Owner/Administrator manage; Administrator/Owner-only refund approval (stub only, no UI built); Doctor view-only; **Receptionist read-only** — reads succeed, writes 403 (the spec's explicit "Reception: Read-only," a softer rule than Phase 8's Receptionist-excluded-entirely for SOAP).
- Frontend: Cashier Dashboard (`/billing`), Invoice Details page with split-payment dialog, discount dialog, and a printable receipt dialog reusing the Phase 5 Queue Slip's print-CSS pattern; real "Billing" card on Visit Details and real "Billing History" tab on Patient Profile (both previously placeholders).
- Explicitly out of scope: Laboratory, Pharmacy, Appointments, TV Display, Patient Portal, a full Refund UI (architecture only), Reports.

## v0.8.0 — Clinical Consultation / SOAP (Phase 8)

Turns a Visit into a documented clinical encounter, built on top of Phase 6's Visit lifecycle and Phase 7's locking pattern:

- New `consultations`/`soap_notes`/`diagnoses`/`consultation_attachments` tables (migration `0008_clinical_consultation`) plus `patients.emergency_contact_name`/`_phone`. SOAP note is upserted in place on autosave, not a new row per save.
- Locking reuses Phase 7's `visit_locks` (no second lock table) — a Visit and its Consultation are 1:1.
- **Critical fix, caught during live verification**: completing a Consultation now correctly syncs both `Visit.status` and the linked Queue ticket's status — the same class of bug Phase 7 was bitten by once already (a ticket left stuck on-screen after the encounter ended), this time one hop further down the call chain (Consultation → Visit → Queue). Verified live via curl before and after the fix, and covered by a dedicated regression test.
- Autosave-idempotent SOAP saves: a 30-second autosave interval resubmitting identical content updates `updated_at` silently, never spamming the timeline/audit log.
- Stricter role gating than Phase 7: only the assigned doctor may edit SOAP/diagnosis/attachments; Administrator/Owner are view-only; Receptionist is excluded entirely (403 on view and edit).
- Frontend: tabbed Consultation page (Overview/SOAP/Diagnosis/Orders-placeholder/Prescription-placeholder/Attachments/Timeline/Audit-placeholder) with an always-visible Patient Summary header, live client-side BMI, real dirty-tracking autosave, and the Phase 7 lock banner reused as-is.
- Explicitly out of scope: Prescription, Laboratory Orders (beyond the Lab Requests placeholder), Billing, Cashier, Appointments, TV Display.

## v0.7.0 — Doctor Workspace (Phase 7)

The doctor's daily driver screen, built on top of Phase 6's Visit lifecycle:

- New `users.doctor_id` link resolves a Doctor-role login to its Doctor record, so a doctor only ever sees Visits assigned to them; Owner/Administrator can view/act on any doctor's workspace.
- `consultation_sessions`, `visit_locks`, `doctor_activity` tables (migration `0007_doctor_workspace`) back real consultation-duration stats, an editing-lock handshake between staff, and a domain-specific action log.
- Doctor Dashboard: live stat cards (Waiting/Called/Serving/Completed Today/Cancelled/No-Show/avg consultation time) and a Today's Queue table with contextual Call/Recall/Start/Complete/No-Show/Cancel actions and live-computed waiting time.
- Visit locking: opening a visit for editing locks it to that user; others see who holds it (view-only) rather than being blocked outright; locks release on explicit close, terminal Visit status, or a 15-minute heartbeat timeout.
- Realtime: reuses the Phase 5 WebSocket channel to broadcast call/consultation/lock events, so a future TV Display can subscribe to the same stream.
- Explicitly out of scope: SOAP Notes, Diagnosis, Prescription, Laboratory, Billing, Medical Records, Appointments, TV Display — placeholder tabs only.

## v0.6.0 — Visit (Encounter) Management

- Introduced the Visit as the central transaction every future clinical/billing module attaches to, auto-created transactionally from every Reception Queue ticket.
- Visit status machine (Registered → Waiting → Called → InConsultation → Completed, plus Cancelled/NoShow) with a legal-transition table and an append-only `visit_timeline_events` log.
- Sequential, concurrency-safe visit numbering (`VIS-YYYYMMDD-000001`); search/filter/paginate visits by patient, doctor, department, status, type, and date range.
- Frontend Visit List + Visit Details pages, and a real Patient "Visit History" tab (previously a Phase 3 placeholder).

## v0.5.0 — Reception & Queue Management

- Walk-in queue ticketing: sequential queue numbers, priority lanes (Senior/PWD/Pregnant/Emergency/VIP), and a status machine (Waiting → Called → Serving → Completed, plus Cancelled/NoShow) with a status-history log.
- Duplicate-active-ticket prevention, inactive-doctor/department/service validation, and a printable queue slip with a signed QR check-in token.
- Realtime WebSocket broadcast channel (`/ws/queues/{clinic_id}`) for live queue updates, architecture-ready for a future TV Display/Doctor Console.
- Reception Dashboard frontend: live queue table, ticket creation, status transitions, slip reprint.

## v0.4.0 — Clinic Configuration & Master Data

- Ten configuration/master-data modules consumed by every future clinical module: Clinic Settings, Branches, Departments, Doctors (+ weekly availability schedules), Consultation Rooms, Services catalog, Queue Settings, Operating Hours, Holiday Calendar, and Clinic Branding.
- Every module tenant-scoped, soft-deletable, role-gated, and audit-logged; several ship "seed defaults" endpoints (departments, services, priority types) for fast clinic onboarding.
- Frontend: a shared, config-driven master-data table/dialog pattern reused across most of these modules, plus bespoke pages for Queue Settings, Operating Hours, and Clinic Settings.

## v0.3.0 — Patient Management

- Tenant-scoped master patient database: sequential patient numbering, duplicate detection (name+DOB or mobile match) with an Owner/Administrator override, and a signed QR check-in payload.
- Full CRUD with rich search/filter/sort, archive/restore as a business-status change (separate from soft-delete).
- Frontend patient list, add/edit form, and a patient profile page with real tabs plus "coming soon" placeholders for future modules (Visit History, Appointments, Billing, Laboratory, Prescriptions, Documents, Audit Logs).

## v0.2.0 — Multi-tenant Authentication & User Management

- JWT access + rotating opaque refresh tokens (hashed at rest), account lockout after repeated failed logins, password reset / email verification token flows, and rate limiting on sensitive auth endpoints.
- Every request carries tenant (`clinic_id`) context resolved from the JWT and enforced through the repository layer.
- Roles seeded (Owner, Administrator, Receptionist, Doctor, Nurse, Cashier, Laboratory, Pharmacy, Viewer) with a permissions table.
- Tenant-scoped staff user CRUD (list/search/create/update/disable/enable/admin-reset-password).

## v0.1.0 — Foundation

- Multi-tenant database foundation: `clinics`, `branches`, `users`, `roles`, `permissions`, `role_permissions`, `audit_logs`, `system_settings`, `subscriptions`, all UUID-keyed with soft-delete and `legacy_id`/`legacy_meta` provenance columns ready for a future legacy-desktop-app data migration.
- Next.js 15 App Router frontend shell with `(auth)`/`(dashboard)` route groups, shared UI primitives, and TanStack Query wiring.
- FastAPI Clean Architecture backend skeleton (`core/`, `db/`, `models/`, `schemas/`, `repositories/`, `services/`, `api/v1/`), Alembic migrations, CI/CD and Docker/dev-bootstrap scaffolding.
