# Roadmap

Phased delivery plan for the CONNECT.PH Clinic Platform. Milestones are rough and will shift as scope is validated with real clinic users; this is a planning aid, not a contractual schedule.

> **v1.0.0 milestone reached (2026-07-28):** every phase below through Phase 17 (Pilot Deployment & UAT) is complete and re-verified. See [`RELEASE_NOTES_v1.0.0.md`](RELEASE_NOTES_v1.0.0.md) and [`CHANGELOG.md`](CHANGELOG.md) for the full release. This was a release-prep pass (regression verification, bug-severity gate, documentation, versioning) — no new business features. "Beyond Phase 3 (exploratory)" below remains the forward-looking backlog for whatever comes after v1.0.0.
>
> **RC1 / feature freeze in effect (as of 2026-07-29):** the project is now at `v1.7.0-rc1` and in Release Candidate status — see [`RELEASE_NOTES.md`](RELEASE_NOTES.md) for the full declaration. **No new features until RC1 ships or an RC2 is needed.** Only bug fixes and genuine production blockers are in scope. Zero Critical/High severity bugs are currently open. Anything below this point in the roadmap that isn't already built is frozen backlog, not active work, until further notice.

---

## Phase 0 — Foundation (current)

**Goal:** A secure, deployable, multi-tenant skeleton that later phases build on.

- [x] Repository structure (`frontend/`, `backend/`, `docker/`, `.github/`, `docs/`, `scripts/`).
- [x] Next.js 15 app shell — route groups `(auth)`/`(dashboard)`, shadcn/ui, TanStack Query wiring.
- [x] FastAPI app shell — layered `core/db/models/schemas/repositories/services/api/middleware`.
- [x] Multi-tenant DB foundation schema: `clinics`, `branches`, `users`, `roles`, `permissions`, `role_permissions`, `audit_logs`, `system_settings`, `subscriptions`.
- [x] `TenantMixin` + repository pattern + clinic-context DI.
- [x] JWT auth (login/logout/refresh/register) wired to DB; forgot/reset/verify-email scaffolded.
- [x] Seeded roles: Owner, Administrator, Receptionist, Doctor, Nurse, Cashier, Laboratory, Pharmacy, Viewer.
- [x] `legacy_id`/`legacy_meta` mixin applied to `clinics`, `users`.
- [x] Docker Compose local dev stack; Dockerfiles for both apps.
- [x] CI skeleton (lint/test/build) and deploy skeleton (Vercel + Railway).
- [x] Foundational docs (this set).

**Milestone target:** Foundation merge-ready, deployable to staging with no business data.

---

## Phase 1 — Core Clinical Workflows

**Goal:** A clinic can register, staff can log in, and a patient can be seen end-to-end for a single visit.

- [x] **Patients module** (Phase 3 of implementation, tracked here under this roadmap phase): master patient registry, full demographic/contact/medical-summary fields, `legacy_patient_id` + `legacy_id`/`legacy_meta` mixin applied, clinic-scoped sequential patient numbering, duplicate detection with admin override, QR check-in token, archive/restore, search/filter/sort/pagination, audit logging, presigned-URL photo-upload stub. See [`FEATURES.md`](FEATURES.md) and [`DATABASE.md`](DATABASE.md).
- Appointments module: scheduling, calendar (day/week views), doctor availability, walk-ins. **Not started** — the patient profile page has a disabled "Appointments" placeholder tab ready for this module to fill in.
- Branches: branch-scoped staff assignment and switching.
- Dashboard: real widgets (today's appointments, queue snapshot) replacing shell placeholders.
- Basic role-based UI gating (Receptionist vs. Doctor vs. Admin views) — established for Patients; extend to remaining modules as they land.

**Milestone target:** Pilot clinic can run a full day of patient registration + scheduling on the platform (no billing yet). Patient registration is now in place; scheduling is next.

---

## Phase 4 — Clinic Configuration & Master Data ✅ complete

**Goal:** Give every future clinical/business module (Queue, Appointments, Billing, Medical Records, Reports) the configurable master data it needs to read from, without building any of those modules' business logic yet.

- [x] Clinic Settings (extended `clinics`) + Branding (logo/favicon/login-background, colors, theme) — singleton-per-clinic, GET/PUT.
- [x] Branches (extended `branches`: code, contact, manager, status) — full CRUD.
- [x] Departments — full CRUD, optional default-set seeding.
- [x] Doctors + Doctor Schedules (availability windows only, no booking) — full CRUD, clinic-scoped auto-generated `doctor_code`.
- [x] Consultation Rooms — full CRUD.
- [x] Services catalog (code/name/price/duration) — full CRUD, optional default-set seeding.
- [x] Queue Settings (prefix/cap/reset-time/walk-ins/priority-lane) + Priority Types — pure configuration, no ticket logic.
- [x] Operating Hours (weekly, per branch, with lunch break) — full CRUD.
- [x] Holiday Calendar (clinic-wide or branch-specific) — full CRUD.
- [x] Single migration `0004_clinic_configuration` covering all of the above.
- [x] Frontend: `features/clinic-config/` (config-driven `MasterDataPage` shared across list modules + bespoke Queue Settings/Operating Hours/Clinic Settings pages), Sidebar "Clinic Configuration" section.

**Explicitly out of scope for this phase** (next up): Queue Management ticket-issuing/calling/serving logic, Appointments booking/slot logic, Billing invoicing/payment logic — see [`FEATURES.md`](FEATURES.md) "Planned" section.

**Milestone target:** A brand-new clinic can be fully configured (branches, departments, doctors, rooms, services, queue rules, hours, holidays, branding) before Queue/Appointments/Billing are built on top. Met.

---

## Phase 5 — Reception & Queue Management ✅ complete

**Goal:** The primary daily receptionist workflow — search-or-create a patient, raise a queue ticket, track it through status, print a slip — on top of the Phase 4 configuration (branches/departments/doctors/services/queue settings).

- [x] `queues` (ticket/execution record), `queue_status_history` (append-only transition log), `queue_counters` (concurrency-safe daily numbering) — migration `0005_reception_queue`.
- [x] `QueueNumberGenerator`: sequential, clinic+branch+prefix+date scoped, `SELECT ... FOR UPDATE` + `INSERT ... ON CONFLICT DO NOTHING` for safe concurrent creation, verified with a real concurrent-creation test.
- [x] Full validation: rejects inactive doctor/department/service, archived/soft-deleted patient, and duplicate active (Waiting/Called/Serving) tickets for the same patient+department+day (also enforced at the DB level via a partial unique index).
- [x] Status machine (Waiting → Called → Serving → Completed, plus Skipped/Cancelled/NoShow) with legal-transition checks, `queue_status_history` writes, and `audit_service` logging on every write path.
- [x] `GET/POST /queues`, `GET/PATCH /queues/{id}`, `PATCH /queues/{id}/status`, `POST /queues/{id}/cancel`, `GET /queues/{id}/slip` — role-gated (Receptionist/Owner/Administrator manage, +Doctor/Nurse transition, all clinical roles view).
- [x] WebSocket broadcast architecture: `/ws/queues/{clinic_id}` (in-process connection manager, documented Redis pub/sub TODO for multi-instance production — same pattern as the rate limiter's Redis-optional fallback). TV Display/Doctor Console consumers are out of scope; only the broadcast channel itself is built.
- [x] `queue_settings.department_id` (nullable per-department prefix override), extended `LegacyMixin` with `legacy_created_at`/`legacy_updated_at`/`migration_batch_id`/`migration_source`/`imported_at`.
- [x] Frontend `features/queue/`: Reception Dashboard (live list, search/filter, New Queue dialog with patient search + inline create escape hatch, status actions, cancel, reprint), Queue Details with history timeline, printable Queue Slip, WebSocket-subscribed live updates with a 30s poll fallback.

**Explicitly out of scope for this phase** (next up): Doctor Console, TV Display consumer, Billing, Appointments, Medical Records.

**Milestone target:** A receptionist can run a full day of walk-in queueing on the platform. Met.

---

## Phase 6 — Visit (Encounter) Management ✅ complete

**Goal:** Introduce the Visit as the central transaction every future clinical/billing module hangs off of, auto-created from the existing Reception Queue flow, with status tracking, a timeline, search/filter, a Visit Details page, and a Patient "Visit History" tab.

- [x] `visits` (the encounter record) and `visit_timeline_events` (append-only, human-readable domain timeline) — migration `0006_visit_management`. `visits` carries the full `LegacyMixin`/`TenantMixin`/soft-delete set for future legacy-migration readiness.
- [x] `VisitNumberGenerator`: sequential, clinic+branch+date scoped (`VIS-YYYYMMDD-000001`), same `SELECT ... FOR UPDATE` + `INSERT ... ON CONFLICT DO NOTHING` pattern as `QueueNumberGenerator`, backed by a dedicated `visit_counters` table, verified with a real concurrent-creation test.
- [x] Queue → Visit integration: `QueueService.create_queue()` now calls `VisitService.create_visit_for_queue()` internally in the same DB transaction as the queue-ticket insert, then links both FKs (`queue.visit_id` and `visit.queue_id`). `POST /queues`'s request/response contract stays backward compatible — `visit_id`/`visit_number` are additive, optional response fields.
- [x] Visit status machine (Registered → Waiting → Called → InConsultation → Completed, plus Cancelled/NoShow) with legal-transition checks, writes to both `visit_timeline_events` (domain timeline) and `audit_service` (cross-cutting audit trail) on every write path.
- [x] `GET/POST /visits`, `GET/PATCH /visits/{id}`, `PATCH /visits/{id}/status`, `GET /visits/{id}/timeline`, `GET /patients/{id}/visits` — role-gated (`VISIT_VIEW_ROLES`/`VISIT_CREATE_ROLES`/`VISIT_MODIFY_ROLES`/`VISIT_CLOSE_ROLES`, mirroring the Phase 5 Queue role matrix). `POST /visits` exists for internal/test use; the real-world creation trigger is `POST /queues`.
- [x] Frontend `features/visits/`: Visit List page (search by visit/queue number or patient, filter by date-range preset/status/visit type, paginated), Visit Details page (summary header, chronological Timeline component, clearly-labeled "coming soon" placeholders for SOAP Notes/Diagnosis/Prescription/Laboratory/Billing/Attachments/Audit Log matching the Phase 3 patient-profile pattern), Patient Details "Visit History" tab implemented for real (was a Phase 3 placeholder), Sidebar nav entry.

**Explicitly out of scope for this phase** (next up): Doctor Consultation/SOAP Notes, Medical Records, Billing, Prescription, Laboratory, Appointments, TV Display.

**Milestone target:** Every queue ticket has a linked Visit record that survives past the ticket's lifecycle, ready for future clinical modules to attach to. Met.

---

## Phase 7 — Doctor Workspace ✅ complete

**Goal:** The doctor's daily driver screen: today's assigned patients, quick visit actions (call/recall/start/complete consultation/no-show/cancel), and a read-focused visit viewer with editing-lock coordination between staff — built on top of Phase 6's Visit lifecycle rather than inventing a parallel state machine.

- [x] `users.doctor_id` (nullable FK to `doctors`) — resolves a logged-in Doctor-role user to their Doctor record for "own visits only" scoping. `consultation_sessions` (Start→Complete Consultation spans, used for real average-consultation-time stats), `visit_locks` (who currently has a Visit open for editing), `doctor_activity` (domain-specific doctor action log, mirroring how `visit_timeline_events` relates to `audit_logs`) — migration `0007_doctor_workspace`.
- [x] `DoctorWorkspaceService` layers doctor-specific side effects (consultation session tracking, doctor_activity log, visit locking, WebSocket broadcast) on top of `VisitService.change_status()` — it never duplicates the legal-transition table from `models/visit.py`.
- [x] `GET /doctor-workspace/dashboard` (real computed stat cards: Waiting/Called/Serving/Completed Today/Cancelled/No-Show/avg consultation time) and `GET /doctor-workspace/queue` (today's assigned visits; Owner/Administrator may view all or filter by `doctor_id`), plus action endpoints `call`/`recall`/`start-consultation`/`complete-consultation`/`no-show`/`cancel`/`open`/`release-lock` — role-gated (Doctor scoped to own visits, Owner/Administrator any visit, Receptionist view-only).
- [x] Visit locking: `open` acquires/refreshes a lock (same user re-opening refreshes it; a different user gets the lock-holder's identity, not edit access); a lock releases explicitly, when the Visit reaches a terminal status, or after a 15-minute heartbeat-expiry window.
- [x] WebSocket: reuses the Phase 5 `queue_connection_manager`/`/ws/queues/{clinic_id}` channel (rather than a second connection manager) to broadcast `visit.called`/`visit.consultation_started`/`visit.consultation_completed`/`visit.status_changed`/`visit.lock_acquired`/`visit.lock_released`, so a future TV Display can subscribe to the same channel.
- [x] Frontend `features/doctor-workspace/`: Doctor Dashboard page (stat cards, Today's Queue table with live-computed waiting time and contextual action buttons), Sidebar nav entry, and the existing Phase 6 Visit Details page extended (not duplicated) with a lock banner and a doctor-actions panel for Doctor/Administrator/Owner viewers.

**Explicitly out of scope for this phase** (next up): SOAP Notes, Diagnosis, Prescription, Laboratory, Billing, Medical Records, Appointments, TV Display.

**Milestone target:** A doctor can log in, see only their own assigned patients for today, and run a full call → start → complete consultation cycle with the Visit's status, timeline, and audit trail all updating correctly. Met.

---

## Phase 8 — Clinical Consultation / SOAP ✅ complete

**Goal:** Turn a Visit into a documented clinical encounter — SOAP notes, diagnosis, a tabbed consultation page, autosave, locking, and read-only history review — built on top of Phase 6's Visit and Phase 7's locking/audit patterns.

- [x] `consultations` (one clinical encounter per Visit, "latest wins" query pattern rather than a hard unique constraint), `soap_notes` (one-to-one, upserted in place on autosave), `diagnoses` (Primary/Secondary, Working/Final, ICD-10 fields architecture-only), `consultation_attachments` (real upload path for Clinical Images/PDF/Referral Letters — Lab Requests stay a placeholder), `patients.emergency_contact_name`/`emergency_contact_phone` (additive, closes the Phase 7 TODO), and new `visit_timeline_event_type` values for consultation events — migration `0008_clinical_consultation`.
- [x] Locking: reuses Phase 7's `visit_locks` (keyed by `visit_id`) rather than a parallel lock table — a Visit and its Consultation are 1:1, so a visit lock already covers "the consultation for this visit."
- [x] Consultation↔Visit status sync (Phase 7 lesson applied): `POST /consultations/{id}/complete` transitions `Consultation.status` to `Completed` and calls `VisitService.change_status()` the same way Doctor Workspace does, and **also** mirrors the transition onto the linked Queue ticket (`ConsultationService._sync_queue_status`) — verified live via curl that a Visit/Queue completed purely through the Consultation-complete path (never touching the Doctor Workspace button) does not get stuck.
- [x] Autosave-idempotent `PUT /consultations/{id}/soap`: only writes a `visit_timeline_events`/audit entry when the submitted content actually changed, so a 30-second autosave interval resubmitting identical content never spams the timeline.
- [x] Role gating (stricter than Phase 7): only the visit's assigned doctor may edit SOAP/diagnosis/attachments; Owner/Administrator may view only; Receptionist is excluded entirely — 403 on both view and edit.
- [x] Frontend `features/consultation/`: SOAP autosave hook with real dirty-tracking (not "always warn"), diagnosis add/list, attachment upload, and a tabbed Consultation page (`/visits/[id]/consultation`) with an always-visible Patient Summary header, reusing Phase 7's `LockBanner`.

**Explicitly out of scope for this phase** (next up): Prescription, Laboratory Orders (beyond the placeholder attachment type), Billing, Cashier, Appointments, TV Display.

**Milestone target:** A doctor can open a Visit's consultation, document SOAP notes with autosave, add a diagnosis, and mark the consultation complete, with the Visit and Queue both correctly reflecting the completed encounter. Met.

---

## Phase 9 — Clinical Orders & Prescriptions ✅ complete

**Goal:** Let a doctor record Laboratory/Radiology/Vaccination/Custom orders, Procedures, Referrals, and Prescriptions during an in-progress consultation — creation + status field + read-only display only (no lab/radiology *processing* workflow, that is a later phase).

- [x] `orders`/`order_items` (shared `order_status` enum across categories — Requested/Collected/Processing/Completed/Cancelled — accepted simplification since a future processing phase builds on one uniform shape; `order_items` uses nullable typed columns `exam_type`/`body_part`/`clinical_indication` for Imaging rather than a JSON blob, since the spec names those fields explicitly), `procedures` and `referrals` as their **own tables** (not `orders` rows) matching the spec's DATABASE section listing them as standalone top-level tables, `prescriptions`/`prescription_items` (Draft/Finalized/Cancelled header + unlimited line items) — migration `0009_clinical_orders`, plus new `visit_timeline_event_type` values (OrderCreated/ProcedureCreated/ReferralCreated/PrescriptionCreated).
- [x] Migration slot coordination: this phase and the concurrently-developed Billing & Cashier phase both targeted the `0009` slot; per explicit priority, Clinical Orders kept `0009` (revision id `0009_clinical_orders`, file `0009_clinical_orders_prescriptions.py`) and Billing was renumbered to `0010_billing_cashier`, both descending from `0008_clinical_consultation`.
- [x] Order/Prescription numbering: `OrderNumberGenerator`/`PrescriptionNumberGenerator` (`services/clinical_number_generator.py`) reuse `PatientNumberGenerator`'s `system_settings`-backed, `SELECT ... FOR UPDATE`-locked counter pattern, date-scoped like `VisitNumberGenerator` (`ORD-YYYYMMDD-000001`, `RX-YYYYMMDD-000001`).
- [x] Prescription validation is **non-blocking**: `ClinicalOrdersService._validate_prescription_items()` returns a `warnings` array (duplicate medicine, missing dosage, missing duration) alongside a successful save — verified live that a prescription with a deliberately-missing-dosage item still saves. Allergy-conflict checking is architecture-only (`check_allergy_conflicts()` always returns `[]` today — no drug/allergy database yet).
- [x] Consultation/Visit-state lesson applied again: creating an order/procedure/referral/prescription does **not** change `Consultation.status`/`Visit.status` (per the spec's workflow, these are recorded *during* an in-progress consultation), but every creation writes a `visit_timeline_events` row and an audit-log entry exactly like Phase 8's diagnosis-add pattern, so it appears correctly in the Visit's Orders/Prescription tabs and Timeline — verified live via curl (`GET /visits/{id}/orders`, `/prescriptions`, `/timeline`).
- [x] Role gating: only the visit's assigned doctor may create/update; Owner/Administrator view-only (same shape as Phase 8); **Receptionist read-only** (view allowed, edit 403 — distinct from Phase 8's Receptionist-excluded-entirely SOAP rule, matching this phase's spec wording); new **Laboratory role** endpoint (`GET /laboratory/orders?visit_id=`) scoped to Laboratory-category orders only, no access to Prescriptions/Procedures/Referrals.
- [x] Frontend `features/clinical-orders/`: Orders/Procedures/Referrals creation forms and lists, Prescription repeatable line-item form with inline (non-blocking) validation warnings and a static common-medicines autocomplete list, wired into the Consultation page's Orders/Prescription tabs, the Visit Details page's read-only Orders/Prescription tabs, and the Patient Profile's Prescriptions view.

**Explicitly out of scope for this phase**: Billing, Cashier, Laboratory/Radiology *processing* (specimen tracking, result entry), Appointments, TV Display.

**Milestone target:** A doctor can create a Laboratory order, an Imaging order, a Procedure, a Referral, and a multi-item Prescription during an in-progress consultation, with validation warnings surfacing without blocking save, and all of it correctly visible in the Visit's tabs, Timeline, and Patient Profile — demonstrated live via curl against the real database. Met.

---

## Phase 10 — Laboratory Management ✅ complete

**Goal:** The laboratory department's own workflow layered on top of Phase 9's doctor-facing Laboratory-category orders — specimen collection → processing → result entry → release, a configurable test/pricing/reference-range template catalog, and full visibility across the Consultation Orders tab, Visit Laboratory tab, Visit Timeline, and Patient Laboratory history.

- [x] `laboratory_orders` (1:1 with a Phase 9 `Order` via `order_id` FK, own `Requested/Collected/Processing/Completed/Released/Cancelled` status enum), `laboratory_results` (one row per result parameter, numeric or text), `laboratory_attachments` (reuses Phase 8's presigned-URL-stub pattern), `laboratory_templates`/`laboratory_template_parameters` (Administrator-configurable test catalog) — migration `0011_laboratory_management`.
- [x] `ClinicalOrdersService.create_order` auto-attaches a `laboratory_orders` row whenever a Laboratory-category order is created (idempotent, best-effort matched to an active template by test name).
- [x] Full status lifecycle with timeline events at each step (no duplicate "Ordered" event — Phase 9's `OrderCreated` already covers it), plus — the Phase 7/8/9 lesson applied a fourth time — the underlying Phase 9 `Order.status` is mirrored on every transition so the Consultation page's Orders tab reflects lab progress instead of staying stuck on `Requested`.
- [x] Billing integration: completing a template-priced lab order automatically adds/updates an invoice line item, idempotently (a real cross-order id-collision bug was found and fixed live during development — see `docs/DATABASE.md`).
- [x] Role gating: Laboratory role (+ Owner/Administrator) collects/processes/enters-results/releases/cancels; Doctor still only creates orders; Receptionist read-only; Administrator/Owner-only template mutation.
- [x] Frontend `features/laboratory/`: Laboratory Dashboard (stat cards + status-contextual worklist), multi-parameter Result Entry dialog, a real Visit Details "Laboratory" card, a real Patient Profile "Laboratory" tab, an Administrator-only Laboratory Test Templates admin page, Sidebar nav entries.

**Explicitly out of scope for this phase**: Pharmacy, Appointments, TV Display, Patient Portal, Reports.

**Milestone target:** A doctor's Laboratory order can be collected, processed, have multi-parameter results entered, and released by Laboratory personnel, with billing auto-synced idempotently and the status/results correctly visible in all five places a doctor, patient, or lab tech would look — demonstrated live in the browser, not just curl. Met.

---

## Phase 11 — Appointment Management ✅ complete

**Goal:** Full appointment booking lifecycle (Booked → Confirmed → Checked-in → Queue Generated → Visit Created → Doctor Consultation → Billing) built on top of Phase 4's `doctor_schedules` architecture and reusing Phase 5/6's `QueueService.create_queue()` for check-in rather than a parallel queue/visit creation path.

- [x] `appointments` (nine-status enum, partial unique index preventing double-booking on doctor+date+start_time excluding Cancelled/Rescheduled/NoShow), `doctor_schedules` extended in place (lunch break/slot duration/daily cap/recurring-override columns, not duplicated), `doctor_schedule_blocks` (vacation/blocked dates), `appointment_reminders` (architecture-only, no sending), `appointment_notes`, `appointment_history` (domain audit trail), `appointment_counters` (backs `APT-YYYYMMDD-000001`), `waitlist_entries` — migration `0012_appointment_management`.
- [x] Time Slot Engine (`services/time_slot_service.py`): computed on demand from `DoctorSchedule` + existing `appointments` + `Holiday` + `DoctorScheduleBlock`, never persisted (`TimeSlot` is a DTO, not a table — see `docs/DATABASE.md`).
- [x] Check-in → Queue → Visit integration (the Phase 7/8/9/10 lesson applied a fifth time, this time addressed by design instead of a live-caught bug): `AppointmentService.check_in_appointment` calls the EXISTING `QueueService.create_queue()` with an additive `visit_type` kwarg (defaulting to `WalkIn`, unchanged for all other callers) rather than reimplementing queue/visit creation — verified live via curl and in the browser (Appointments page → Check In → Reception Queue screen shows the new ticket → Visits list shows the new linked Visit tagged `Appointment`).
- [x] Reschedule creates a new Booked row and marks the old row Rescheduled (terminal), with full old/new date-time history on both; cancel offers the freed slot to the oldest matching `WaitlistEntry` (architecture-level "offer", no notification sending).
- [x] Role gating: Reception (+Owner/Administrator) create/edit/reschedule/cancel/check-in; Doctor completes/no-shows (+Owner/Administrator); doctor schedule administration is Administrator-only.
- [x] Frontend `features/appointments/`: Appointment Dashboard (search/filter/list, New Appointment dialog reusing the Queue feature's patient-search pattern, live Time Slot Engine picker), Appointment Details dialog with history timeline, real Patient Profile "Appointments" tab (replacing the placeholder), Sidebar nav entry.
- [x] Calendar (Day/Week/Month/Agenda views, dependency-free React/CSS grid, filters by Doctor/Department/Branch/Appointment Type, wired to `GET /appointments/calendar`) as a List/Calendar toggle on the Appointment Dashboard, and a Doctor Schedule admin page (`/doctor-schedules`, working days/hours/lunch/slot-duration/max-per-day form + vacation/blocked-dates list+add, Administrator-only) under Doctors in the sidebar — both verified live: setting Dr. Maria Santos's Monday hours to 08:00-13:00/20-minute slots on the admin page immediately changed the slots offered by the New Appointment dialog for a Monday date.

**Explicitly out of scope for this phase**: actual SMS/Email/Push reminder sending (architecture only), Teleconsultation video, Patient Portal, TV Display.

**Milestone target:** A doctor's schedule can be configured, available slots computed correctly (rejecting double-booking/outside-hours/lunch-break/holiday/blocked-date), an appointment booked/confirmed/rescheduled/cancelled, and checking in creates a real linked Queue ticket AND Visit that immediately appear on the Reception Queue and Visits screens — demonstrated live in the browser. Met.

---

## Phase 12 — Owner Dashboard & Reports ✅ complete

**Goal:** A read-only aggregation/reporting layer over every operational table built so far — Owner Dashboard, real-time activity feed, live alerts, and six filterable reports with exports — without duplicating any business logic already implemented for the Doctor/Cashier/Laboratory dashboards.

- [x] No new tables, no migration (`alembic heads` stays at `0012_appointment_management`) — every metric is a real SQL `COUNT`/`SUM`/`AVG`/`GROUP BY` aggregation against existing tables, reusing a repository method where one already existed (e.g. `InvoiceRepository.sum_todays_revenue` from Phase 9) and adding new aggregation methods to the *existing* repository that owns each table otherwise (see `docs/DATABASE.md`'s Phase 12 section for the full map).
- [x] `GET /analytics/dashboard`: 16 stat cards (Patients/New Patients/Appointments/Walk-ins Today, Completed Consultations/Cancelled Visits/No Shows, Laboratory Orders/Prescriptions Issued, Pending Payments, Collected Revenue Today, Outstanding Balance, Avg Waiting/Consultation Time, Doctors On Duty, Rooms In Use).
- [x] `GET /analytics/activity-feed`: merges `visit_timeline_events` + `queue_status_history` + `audit_logs`, sorted descending — a real queried feed, not a new event-logging mechanism.
- [x] `GET /analytics/alerts`: live threshold checks (High Queue Volume, Long Waiting Time, Outstanding Payments), computed on request; System Errors/Failed Backups explicitly out of scope (no infra monitoring exists yet).
- [x] Six report endpoints (Patient/Doctor/Revenue/Queue/Laboratory/Appointment), each with `date_range` preset + custom start/end + optional `doctor_id` filters, chart-ready `{label, value}` series throughout.
- [x] Export: real working CSV (`format=csv`), Excel-compatible reuse of the same CSV body (`format=excel`), explicit `501` stub for `format=pdf` per the spec's "do not implement PDF styling yet".
- [x] Role gating: **Owner and Administrator only** — the simplest, strictest gate in the project; every other role 403s on every `/analytics/*` endpoint.
- [x] Report-generation audit reuses the existing `audit_logs` table rather than adding a new `report_generation_log` table.
- [x] Frontend `features/analytics/`: Owner Dashboard page (`/analytics`, Sidebar entry shown only to Owner/Administrator), grouped stat-card grid, live Activity Feed, Alerts banner, six report sections with date-range filters and zero-dependency inline-SVG bar/line charts (no charting library added). No direct mutations of its own, so staleness is handled via a 30s `refetchInterval` + `refetchOnWindowFocus` polling policy instead of mutation-driven cache invalidation.
- [x] Cross-checked live: "Collected Revenue Today"/"Outstanding Balance"/"Pending Payments" match `GET /billing/dashboard` exactly; Patient Report's `total_visits` for a given day matches `GET /visits?date_from=...&date_to=...`'s `total` exactly.

**Explicitly out of scope for this phase**: TV Display, Patient Portal, Migration Wizard, Production Deployment, real PDF export styling (explicit `501` stub only).

**Milestone target:** An Owner can log in, see real (not placeholder) clinic-wide numbers that mathematically match the underlying Billing/Visits/Queue/Laboratory/Appointment modules, watch the activity feed and alerts update live, change a report's date range and see the numbers/charts change accordingly, and export a report to CSV — all demonstrated live against the real database and browser, not just unit tests. Met.

---

## Phase 13 — Live TV Queue Display ✅ complete

**Goal:** A fullscreen, kiosk-grade waiting-area display showing the live queue (Now Serving + Next N Waiting) plus scrolling announcements, reading the existing Phase 5/7 realtime WebSocket channel rather than building a second one, with a genuinely public (no-JWT) mode for the display itself and Owner/Administrator-only configuration.

- [x] `tv_display_configs` (scoped clinic-wide or narrowed to branch/department/doctor; theme/font-size/queue-size/animation-speed/refresh-interval/logo/colors; `is_public` + unique `public_slug`; `tts_enabled`/`tts_template` architecture-only columns) and `tv_announcements` (clinic-wide or per-display, typed, orderable, date-range-schedulable) — migration `0013_tv_queue_display`, `alembic heads` stays a single linear chain.
- [x] `GET /public/tv-display/{public_slug}` bypasses `get_current_user`/`oauth2_scheme` entirely — verified with zero `Authorization` header in both a pytest and a live curl call — resolving Now Serving/Next Waiting (patient **initials only**, server-derived) + announcements, filtered to `ACTIVE_QUEUE_STATUSES` and the config's scope; an unknown/private/inactive slug 404s, never leaking another clinic's data (dedicated cross-tenant test).
- [x] **WebSocket-auth-for-public-displays decision**: `ws_queues.py`'s `/ws/queues/{clinic_id}` handshake now accepts either a JWT (unchanged) or a TV display's `public_slug` as the `token` query param, resolving the slug to its own `clinic_id` via `TvDisplayConfigRepository.get_by_public_slug` rather than trusting the path segment — reuses the existing channel and the existing secret-token-as-credential model instead of adding a second WS endpoint or minting anonymous JWTs.
- [x] Realtime strategy: the display re-fetches its full snapshot on any `queue.*`/`visit.*` event rather than patching from the event payload, since it needs additional client-side filtering (queue_size truncation, ACTIVE_QUEUE_STATUSES, ordering) beyond what one event carries.
- [x] First reconnect-with-backoff logic in the project (`useTvDisplayRealtime`/`use-connection-backoff.ts`, unit-tested) — the existing Phase 5 `useQueueRealtime` hook has none, relying solely on its 30s poll fallback. Verified live: killing and restarting the backend with the display tab open shows a "Reconnecting..." indicator and self-heals with zero manual reload.
- [x] Text-to-speech: architecture only — `tts_enabled`/`tts_template` fields plus a real string-templating `services/tts_service.py::generate_announcement_text()`; no audio synthesis implemented, by design.
- [x] Frontend: standalone `/tv/[slug]` route outside the `(auth)`/`(dashboard)` route groups (no sidebar/topnav/session requirement), large high-contrast typography for landscape 1080p/4K/Android-TV-browser kiosks, live clock/date, scrolling announcement ticker, fullscreen toggle, unobtrusive connection-status indicator, and a Web-Audio-generated notification beep gated behind a one-time "Enable Sound" tap (autoplay-policy compliant, no external audio asset). Owner/Administrator-only admin UI (`/tv-displays`, new Sidebar entry) for config + announcement CRUD.
- [x] Role gating: config/announcement mutation is Owner/Administrator-only (`require_config_manage_role`, reused); the public endpoint has no role at all by design.
- [x] Every config/announcement create/update/delete writes an `audit_logs` entry (`tv_display.config_created`/`config_updated`/`config_deleted`/`announcement_created`/`announcement_updated`/`announcement_deleted`).

**Design gap, documented rather than guessed at**: `Queue`/`Visit` have no FK to `ConsultationRoom` yet, so "Room" is omitted from the public display payload (`room_name: null`) instead of being inferred incorrectly — see `docs/DATABASE.md`.

**Bug found while testing, not fixed here (out of scope)**: `VisitCounter` is scoped per (clinic, branch, date) but the generated `visit_number` string has no branch component and is unique only per (clinic, visit_number) — two branches' same-day counters can collide on `VIS-YYYYMMDD-000001`. A Phase 6/11 issue; flagged in `docs/TESTING.md`.

**Explicitly out of scope for this phase**: Migration Wizard, Patient Portal, Production Deployment, real text-to-speech audio synthesis.

**Milestone target:** An Owner creates a branch-scoped, public-mode TV display and gets a shareable URL; opening that URL in a fresh, logged-out browser tab renders the clinic's live queue with zero authentication; creating/calling/completing a queue ticket in a separate authenticated tab updates the display tab with no manual reload; killing and restarting the backend while the display is open shows it reconnect on its own. All demonstrated live, not just unit tests. Met.

---

## Phase 14 — Legacy Migration Wizard ✅ complete

**Goal:** The payoff for the `LegacyMixin` columns (`legacy_id`/`migration_batch_id`/`migration_source`/`legacy_created_at`/`legacy_updated_at`/`imported_at`) every entity table has carried since Phase 5 — a real, resumable, idempotent import engine for cutting a clinic over from a legacy desktop system, plus the meta-tables needed to run and audit an import.

- [x] `migration_batches`/`migration_entity_progress` (per-entity resume via `last_processed_offset`)/`migration_field_mappings`/`migration_validation_issues`/`migration_logs` — migration `0014_legacy_migration_wizard`. These meta/process tables do NOT carry `LegacyMixin` (they are the migration tracking system itself, not data migrated *from* a legacy system) but do carry `TenantMixin` + timestamps.
- [x] **Audit finding, fixed in the same migration**: `branches`/`departments`/`doctors`/`services` (`ClinicService`) were missing the `LegacyMixin` columns every other entity table already had — backfilled additively in `0014` before building the import engine, since Doctors is one of the two fully-implemented import targets.
- [x] **Source adapter scope decision**: CSV and Excel are the only fully-working `SourceAdapter` implementations (stdlib `csv` + `openpyxl`), since no specific legacy client database technology has been identified yet and CSV/Excel can represent an export from virtually any legacy desktop system. SQLite/Access/SQL Server/MySQL/PostgreSQL get a real abstract `SourceAdapter` interface (`connect`/`analyze_schema`/`read_table`/`close`) and a registry, but their adapters raise `NotImplementedError` pointing at the CSV/Excel path.
- [x] **Idempotency decision**: `legacy_id` + `migration_batch_id` (already on every entity table) are looked up before every insert — no separate `sync_hash` column was added. Proven with a real double-import test (both automated and live curl): re-running the identical import against the same batch creates zero new rows the second time, including when an entity's resume offset is manually reset to 0 (forcing a full row-by-row re-scan).
- [x] Mapping engine with real fuzzy/synonym name-matching (`suggest_mappings()` — e.g. source `FName` → suggested destination `first_name`), and three real transforms (DateFormat/PhoneFormat/Trim) plus Rename/Custom as architecture.
- [x] Validation service reuses Phase 3's Patient duplicate-detection pattern (name+DOB or mobile match) for `DuplicatePatient`, an equivalent name-match for `DuplicateDoctor`, and real required-field/date/phone/email checks (`EmailStr`, `MOBILE_NUMBER_PATTERN` reused from the Patient schema) — proven against a deliberately-broken CSV row without flagging the valid rows alongside it.
- [x] Import engine processes entities in the mandated 17-step order, batches of 500 rows per DB transaction (rollback-on-failure, no partial batches), via `BackgroundTasks` (no new job-queue dependency) — Owner/Administrator only, the same strictest role gate as Phase 12 Analytics.
- [x] **Scope decision, entities**: only Patients and Doctors are wired to a real destination create-path (`PatientService.create_patient` / a direct `Doctor` repository create with legacy fields populated) in this phase — the other 15 entity types get full schema-analysis/mapping/validation support but `import_entity()` marks them `Skipped` with an explanatory log entry rather than writing partially-modeled data. See `docs/MIGRATION.md`.
- [x] Frontend `features/migration/`: 8-step wizard (`/migration`, Owner/Administrator-only, new Sidebar entry) — Choose Source → Connect (upload) → Analyze → Map Fields → Preview → Validate/Resolve Issues → Import (live Migration Dashboard, 2s status polling) → Verify (persisted Verification Report), plus Migration History.

**Explicitly out of scope for this phase**: production deployment; fully-working SQLite/Access/SQL Server/MySQL/PostgreSQL adapters (architecture only); importing the 15 non-Patient/Doctor entity types end-to-end (mapping/validation architecture is real and ready for a future phase to extend); a dedicated frontend `sync_hash`/idempotency UI (idempotency is proven at the API/DB level).

**Milestone target:** An Owner walks a small CSV sample (a few test patients/doctors, one deliberately broken) through the full wizard end to end — connect, analyze, map, preview, validate (broken row correctly flagged and resolved), import (live dashboard), verify (report matches) — and re-running the identical import a second time creates zero new rows. Demonstrated live via curl and in the browser, against a disposable/obviously-fake sample, never the real seeded demo patient. Met.

---

## Phase 15 — SaaS Administration Portal ✅ complete

**Goal:** A second, structurally separate portal for CONNECT.PH platform staff (not clinic staff) to manage tenant clinics across the entire platform — the first phase that deliberately punches a controlled hole through the tenant-isolation boundary every prior phase was built on, without weakening it for any existing clinic-scoped role.

- [x] `platform_admin_users` (no `clinic_id` — a structurally separate user model, not an extension of `users`), `tenant_feature_flags`, `platform_audit_logs`, `platform_sessions`, `background_jobs` (real, surfaces Phase 14 migration batches — no fake job system), `platform_config`, `api_keys`/`oauth_clients`/`webhook_secrets`, `backups` — migration `0015_saas_administration`. Extended `clinics` (suspend/archive lifecycle fields) and `subscriptions` (trial/renewal/license-limit fields), both pre-existing since Phase 1/4.
- [x] **The core architecture decision**: a fully separate JWT claim shape (`app/core/platform_admin_security.py`) and a fully separate dependency chain (`get_current_platform_admin`, never layered on `get_current_user`) — see `docs/ARCHITECTURE.md` §7 for the full rationale. Proven live both directions: a Platform Administrator token gets a clean 401 on every existing clinic-scoped endpoint, and a regular clinic Owner/Doctor token gets a clean 401 on every `/platform-admin/*` endpoint.
- [x] Tenant management: list/search/create/suspend/reactivate/archive, real per-tenant stats (user count, storage usage) via aggregation, not cached columns. Suspending a tenant force-logs-out every user in it and blocks future logins (`AuthService.login` checks `clinic.status`).
- [x] Subscription/license management (plan/trial/renewal/expiration/max-users/max-branches/storage-limit/API-rate-limit), feature flags (real CRUD for 8 keys, one wired proof-of-concept — Appointments visibility), tenant-user administration (reset password/lock/unlock/force-logout, reusing Phase 2's account-lockout fields and `refresh_tokens`), System Health dashboard (real Postgres aggregation, including `pg_database_size()`), platform audit log.
- [x] Role/permission matrix for the four platform roles (PlatformAdministrator/SupportEngineer/ImplementationTeam/Auditor) — Auditor is read-only across the whole surface; documented in `app/core/dependencies.py` and `docs/ARCHITECTURE.md`.
- [x] Frontend: a genuinely separate portal (`app/platform/`, not nested under the existing `(dashboard)` group), its own login page and layout/branding, its own token-storage keys and middleware-protection logic (`frontend/src/middleware.ts`), Platform Dashboard + Tenant Management pages wired to the real API.
- [x] Backend pytest (`test_platform_admin.py`, 13 tests) proves cross-tenant visibility for the platform admin AND that isolation is preserved for clinic-scoped roles, in both directions; frontend Vitest (11 tests) proves token-storage/cookie separation and tenant-search/feature-flag-toggle logic.

**Explicitly out of scope for this phase**: real payment-gateway billing/automated subscription charging (subscription fields are manually-editable records); Patient Portal, Teleconsultation, AI Assistant, Inventory (feature-flag keys exist as togglable placeholders only); wiring API keys into real endpoint authentication; wiring `platform_config` into any real email/SMS/AI/storage provider; a real `pg_dump`-backed backup (not available in this environment — implemented as a documented, honestly-labeled stub record); real database restore (architecture-only stub, too dangerous to implement against a live multi-tenant DB); retrofitting feature-flag gating into every existing module (only Appointments got the proof-of-concept wire-up).

**Milestone target:** A seeded Platform Administrator logs in via the separate portal, creates two fake test tenant clinics, sees both via the cross-tenant tenant list, suspends one (blocking that tenant's login), and reactivates it — while the real `owner@connectph.dev`/`maria.santos@connectph.dev` clinic accounts continue to work completely normally, get a clean 401 on every `/platform-admin/*` endpoint, and never see the two test tenants' data through any existing clinic-scoped endpoint. Demonstrated live via curl and in the browser. Met.

---

## Phase 17 — Billing & Cashier ✅ complete

**Goal:** Turn a completed Consultation into a billable, payable, receiptable encounter — invoices, line items, discounts, split payments, void, receipts, and a Cashier Dashboard — built on top of Phase 6's Visit and Phase 8's Consultation rather than a parallel transaction model.

- [x] `invoices`/`invoice_items` (Draft→PendingPayment→PartiallyPaid→Paid→Cancelled, auto-created on consultation completion), `invoice_counters` (backs `INV-YYYYMMDD-000001` generation), `discounts` (invoice-level, Senior Citizen/PWD/Employee/Custom, percentage or fixed), `payments` (supports split payments as multiple rows per invoice), `refunds` (architecture-only per spec — no UI) — migration `0009_billing_cashier`.
- [x] Consultation → Invoice sync (the Phase 7/8 lesson applied again): `ConsultationService.complete_consultation()` now also calls `InvoiceService.create_draft_invoice_for_consultation()`, idempotently — a repeat/idempotent complete() call never creates a duplicate invoice. The auto-added Consultation Fee line item prices from `Doctor.consultation_fee` first, falling back to the visit's `ClinicService.default_price`.
- [x] Payment → Visit sync (the same lesson, one hop further): an invoice reaching `Paid` transitions the linked Visit to `Completed` if not already terminal, matching the spec's workflow diagram's "Visit Closed" terminal step — verified live via curl and by `test_full_payment_transitions_to_paid_and_syncs_visit`.
- [x] `PaymentService.void_payment` recomputes `amount_paid`/`balance_due`/`status` from scratch off the remaining Completed payments (not a naive decrement), so a fully-paid invoice whose only payment is voided correctly moves back to `PendingPayment`.
- [x] Role gating: Cashier + Owner/Administrator manage (items/discounts/payments); Administrator/Owner-only refund approval (stub only, no UI); Doctor view-only; **Receptionist read-only** (reads succeed, writes 403) — distinct from Phase 8's Receptionist-excluded-entirely rule for SOAP, per the spec's explicit "Reception: Read-only" wording for Billing.
- [x] `GET /billing/dashboard` (Cashier Dashboard: Pending Payments/Paid Today/Today's Revenue/Outstanding Balance/Refunds Pending/Recent Payments, all real computed values), invoice search/filter (invoice/receipt/patient/visit/doctor/payment-reference, status, date), a computed (not persisted) printable Receipt with a `window.print()` flow matching the Phase 5 Queue Slip's CSS pattern.
- [x] Frontend `features/billing/`: Cashier Dashboard page, Invoice List/Details pages, Payment Dialog (split-payment support), Discount Dialog, Receipt Dialog; real "Billing" tab on Visit Details (replacing the Phase 6-8 placeholder) and real "Billing History" tab on Patient Profile (replacing the Phase 3 placeholder); Sidebar nav entry.

**Explicitly out of scope for this phase**: Laboratory, Pharmacy, Appointments, TV Display, Patient Portal, Refund UI (architecture only), Reports (data model is billing-ready, no report pages/endpoints).

**Milestone target:** Completing a consultation auto-creates a Draft invoice; a cashier can add/edit items, apply a discount, record a (possibly split) payment, print a receipt, and see the Visit correctly reflect the closed/paid encounter — all demonstrated live against the real database, not just unit tests. Met.

---

## Phase 17 (v0.17.0) — Pilot Deployment & User Acceptance Testing ✅ complete

> **Numbering note**: this is a distinct, chronologically later phase
> from the "Phase 17 — Billing & Cashier" section directly above — see
> that section's own note and `docs/RELEASE_NOTES.md`'s v0.17.0 entry
> for why the numbers collide (a pre-existing inconsistency between
> this file's phase numbers and `RELEASE_NOTES.md`'s "(Phase N)"
> suffixes, not something introduced or fixed this phase). This phase
> followed **v0.16.0 — Production Hardening**.

**Goal:** Verify the platform is technically ready for a real pilot clinic — deployment config, a fully-configured pilot tenant, a real end-to-end legacy migration test, and a full scripted UAT walkthrough — while being explicit about what still requires real people (training, sign-off, production cutover) rather than fabricating any of that.

- [x] Deployment readiness reviewed against the running dev stack: `.env.example` completeness, migration state, file storage, background jobs, logging/monitoring, and the Phase 16 backup mechanism. No real cloud deployment performed — see `docs/PILOT_READINESS.md`.
- [x] A real pilot tenant ("Pilot Community Clinic") created and configured end-to-end via live API calls: branch, departments/services, doctor + weekly schedule, operating hours, queue settings + priority types, staff users.
- [x] Legacy Migration Wizard exercised hands-on with a realistic sample CSV dataset — surfaced and fixed a real High-severity bug (`docs/BUGS.md` BUG-001: resolving a validation issue had no effect on import); re-verified live after the fix.
- [x] Full scripted patient-journey UAT (Registration → Appointment → Check-in → Queue → Consultation → Orders → Prescription → Laboratory → Billing → Payment → Completion), 17/17 steps passing against a live backend instance.
- [x] `docs/BUGS.md` updated with 5 findings (1 High, fixed; 2 Medium/Low informational; 2 Low informational) — only the High one was fixed, per this phase's fix-only-Critical/High rule.
- [x] New docs: `docs/PILOT_READINESS.md`, `docs/USER_MANUAL.md`, `docs/ADMINISTRATOR_GUIDE.md`, `docs/SUPPORT_GUIDE.md`. Existing `docs/DEPLOYMENT.md`/`docs/MIGRATION.md`/`docs/BACKUP.md` reviewed, found accurate, `docs/MIGRATION.md` given a short Phase 17 verification addendum.

**Explicitly not done, and not claimed to be done**: real user training sessions, real human sign-off from each clinic role, a real production deployment. See `docs/PILOT_READINESS.md`'s "What remains" section for these as explicit next steps for the real clinic team.

**Milestone target:** Every technically-checkable piece of pilot readiness verified live (not just claimed); an honest, explicit list handed to the real clinic team for what only they can complete. Met.

---

## Phase 2 — Operations: Billing, Pharmacy, Lab

**Goal:** Revenue-generating and clinical-support workflows.

- Billing: invoicing, payment collection, receipts, price lists per clinic; HMO/insurance claim basics. The services/price catalog already exists from Phase 4 — this phase adds invoicing/payment logic.
- Doctor Console + TV Display consumer UI: Phase 5 built the queue ticket/status/WebSocket broadcast this will read from and subscribe to.
- Pharmacy: drug inventory, prescriptions tied to visits, dispensing, low-stock alerts.
- Notifications: SMS/email appointment reminders.

**Milestone target:** A clinic can run its full daily operations (registration → consult → lab/pharmacy → billing) without the legacy desktop app.

---

## Phase 3 — Reporting, Analytics & Legacy Migration

**Goal:** Full cutover from the legacy system (operational reporting/analytics is now covered by Phase 12 — Owner Dashboard & Reports, complete).

- Legacy data migration tooling: ETL scripts importing patients, doctors, appointments, queue history, billing, users, and settings from the legacy Windows desktop app, using the `legacy_id`/`legacy_meta` mapping strategy established in Phase 0 (see [`DATABASE.md`](DATABASE.md)).
- Multi-branch reporting and inventory transfer.
- Hardening: load testing, security review, backup/restore drills.

**Milestone target:** First clinic fully cut over from legacy desktop software, historical data migrated and verified.

---

## Beyond Phase 3 (exploratory)

- Patient-facing portal/app (self-scheduling, results viewing).
- Telemedicine / video consult integration.
- Advanced insurance/HMO claims automation.
- Multi-region/multi-currency support for expansion beyond initial market.

---

## How this roadmap is maintained

- Update this file when a phase's scope materially changes, not for every task.
- Checkbox items under "Foundation" reflect what's actually merged, not what's planned — keep them honest.
- Cross-reference [`FEATURES.md`](FEATURES.md) for the authoritative "built vs. planned" list at any point in time.
