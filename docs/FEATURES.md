# Features

This document tracks what is actually implemented in the CONNECT.PH Clinic Platform versus what is planned. It is updated as work lands — treat the "Built" section as ground truth for what exists today, and the "Planned" section as a backlog, not a promise of scope or order (see [`ROADMAP.md`](ROADMAP.md) for sequencing).

---

## Built — Post-RC1: Short TV Display URL

**2026-08-11.** The TV Display's public URL (`/tv/<public_slug>`, a 32-character random token) is impractical to type on a Smart TV remote. Added an optional, admin-chosen short alias — e.g. `/tv/canora` — that resolves to the exact same display, without weakening the existing unauthenticated-access model.

**Backend** - `tv_display_configs` gained a nullable, unique `short_code` (migration `0028_tv_display_short_code`), settable via the existing `POST`/`PATCH /tv-displays` endpoints (2-32 chars, lowercase letters/digits/hyphens, normalized server-side, `409` on a duplicate). `GET /public/tv-display/{public_slug}` now tries a `public_slug` match first and falls back to `short_code` on a miss — same `is_public`/`is_active`/`is_deleted` filters either way, so the short code is an additional lookup key onto the same row and access-control gate, never a separate or weaker one. The long `public_slug` URL is completely unaffected; every existing display keeps working exactly as before.

**Security tradeoff, disclosed and mitigated, not silent**: a short code is inherently more guessable than the 192-bit `public_slug`. Mitigated by (a) being a deliberate per-display admin opt-in (never auto-generated), and (b) the public endpoint now being rate-limited per client IP (`rate_limit_tv_public`, 60 requests/60s default) to blunt brute-force enumeration. The WebSocket auth path (`ws_queues.py`) was **not modified at all** - it still only ever accepts the real `public_slug`, never a short code; the frontend (`use-tv-display-realtime.ts::resolveWsToken`) always uses the *resolved* `ws_auth_slug` from the snapshot response (the row's real slug) for the WS connection, never the raw string typed into the browser's URL bar - so reaching a display via `/tv/canora` results in byte-identical WS behavior to reaching it via the long slug. See `docs/DATABASE.md`'s section on this column for the full rationale, including why this tradeoff was accepted given the primary deployment target (single-clinic, LAN-only, non-sensitive data already documented as safe to expose unauthenticated).

**Admin UI** - `/tv-displays`' create/edit dialog gained an optional "Short URL code" field (shown once "Public mode" is enabled), with a live preview of the resulting short URL; the display list shows both the long and short URL (when configured) with copy/open actions for each.

**Live-verified**: set `short_code: "canora"` on a real display via the admin UI, confirmed `/tv/canora` renders the identical clinic TV display (same queue data, same rotating info panel) as the long-slug URL; confirmed a real queue ticket called via the API appeared live on the short-URL display; confirmed the API response's `ws_auth_slug` is always the real 32-character slug even when resolved via the short code; confirmed an unknown short code returns the same "Display not available" 404 page as an unknown slug, leaking nothing; confirmed the long-slug URL for the same display still works unchanged. Backend: 17/17 `test_tv_display.py` tests pass (6 new). Frontend: 39/39 `tv-display` tests pass (3 new, covering the WS-token-resolution logic). Production build succeeds.

---

## Fixed — Post-RC1: TV Display "Now Serving" cropping at 5+ simultaneous tickets

**2026-08-11.** Reported: Now Serving cards were cropped/clipped on the TV Display. Reproduced live by creating 8 real, simultaneous "Called" tickets across 8 distinct destinations at 1600x900 — the grid's actual required height (444px) exceeded the space the flex layout had available (336px), and the existing `overflow-y-auto` "safety net" silently clipped the overflow rather than visibly scrolling (there's no way to scroll a TV, so overflow there just looks like cropping).

Root cause: only the queue-number text (`numberSizeClassName`) was tier-aware in `now-serving-layout.ts`'s density tiers (5-8 tickets / 9+ tickets) — the patient-initials and doctor/department+room lines stayed a single fixed size at every density, so they kept consuming the same vertical space regardless of how many rows had to fit.

**Fix** (`frontend/src/features/tv-display/lib/now-serving-layout.ts`, `TvDisplayScreen.tsx`): extended `NowServingLayout` with tier-aware `initialsSizeClassName`, `detailSizeClassName`, and `lineSpacingClassName`, and tightened the 5-8/9+ tier number sizes, padding, and grid gaps so each tier's total content is actually budgeted to fit its available space rather than relying on scroll to hide the overflow.

**Live-verified**: re-measured the same reproduction (8 tickets, 1600x900) after the fix — zero overflow (`scrollHeight === clientHeight`, 273px content in a now-336px-available budget). Also verified at 10 tickets (9+ compact tier) and confirmed the 1-4 ticket tier renders pixel-identical to before. All 36 `tv-display` tests pass (6 new, covering the new tier-aware fields). Production build succeeds.

---

## Built — Post-RC1: Compact 80mm Thermal Queue Ticket Printing

**Complete and verified, 2026-08-11.** Fixes `QueueSlipDialog.tsx`'s (`frontend/src/features/queue/components/`) print output — previously it had no `@page` rule at all, so the browser fell back to whatever the OS/default printer reported (typically an 80mm-wide × ~210mm/11in-long thermal-roll profile), while the ticket's own content only ever grew as tall as it needed, leaving a large blank area below it on every printed ticket.

**Fix (frontend/print-CSS only — no backend, queue numbering, or business-logic change)**: a dedicated `@media print` block sets `@page { size: 80mm auto; margin: 0; }` — `auto` height so the page is exactly as tall as the ticket content (a thermal roll has no fixed page length to begin with), zero page margin so the 80mm width is fully usable and so Chrome's built-in print header/footer (URL/title/date/page-number) has no margin space to render into (there is no CSS property that force-disables that browser-chrome UI directly — this is the closest a stylesheet can get without relying on the user manually unchecking "Headers and footers" in the OS print dialog). The printable ticket element itself is set to `width: 80mm` with `padding: 3mm` (accounts for a real thermal printer's own unprintable edge margin, applied as inner padding rather than an `@page` margin, since that must stay 0). Also fixed the underlying "extra blank page" root cause: the existing hide-everything-but-the-ticket technique used `visibility: hidden` on the rest of the page (correct, since `display: none` would also hide the ticket nested inside the same DOM subtree) but that still reserves layout space — under an auto-height `@page`, the full (very tall) hidden app shell was still determining page count. Fixed by collapsing `body` to zero height with `overflow: hidden` in print mode; the ticket (positioned `fixed`, viewport-relative) is unaffected since fixed positioning isn't clipped by an ancestor's overflow.

**No UUID was ever printed** — audited the `QueueSlip` API response and the dialog's JSX: only `clinicName`, `branchName`, `queueNumber`, `priority`, `patientName`, `departmentName`, `doctorName`, `createdAt`, and `qrToken` are shown; `qrToken` is a `clinic_id:queue_id:hash` string (`backend/app/services/queue_service.py::_slip_qr_token`) with no patient id anywhere in it, and `patientId` isn't even part of the `QueueSlip` schema. No backend change was needed to satisfy this requirement — already true before this fix.

**Live-verified**: real browser session against the Reception Queue page — printed a ticket with a long patient name, a department-only ticket with no doctor assigned ("Doctor: Unassigned" renders correctly), confirmed the generated print stylesheet text contains the exact `@page { size: 80mm auto; margin: 0; }` rule, and measured the printable element's actual rendered width at `79.999mm` (296px readback verified via `getBoundingClientRect()` against the CSS `width: 80mm`) with a compact ~318-338px content height — no forced page length, no blank area. Confirmed the ordinary (non-print) Reception Queue page and dialog are visually unchanged (the entire fix is scoped inside `@media print`). `npm run build` succeeds; all pre-existing `features/queue` frontend tests (10/10) pass unmodified.

**Follow-up: exact ticket format** (same day, per explicit follow-up request with a reference mockup) — reworked `QueueSlipDialog.tsx`'s printable JSX to match a specific field order/layout: clinic name (top, centered, bold uppercase) → branch (centered) → large queue number (centered) → priority (centered) → dashed separator → `Patient:`/`Department:`/`Doctor:` (left-aligned label+value rows) → `Date:` (left-aligned) → "Thank you!" (centered, bottom). The `qrToken` field is no longer rendered at all (still present on the `QueueSlip` API type/response, just not displayed — no backend change). Long patient/department/doctor names now **truncate with an ellipsis** (`overflow: hidden; text-overflow: ellipsis; white-space: nowrap`, replacing the earlier `break-words` wrap) so the ticket's height never grows with name length — a thermal roll should always cut right after a fixed, predictable amount of content. Date/time formatting was tightened to a compact single line with no seconds/comma (`toLocaleDateString()` + `toLocaleTimeString([], {hour:"numeric",minute:"2-digit"})`, still no hardcoded locale — follows the browser/clinic's own locale setting, same convention as every other date display in this app).

**Live-verified (follow-up)**: printed a real ticket, confirmed the rendered text matches the required field order/format exactly (including the compact date format, e.g. `7/27/2026 8:48 PM`), confirmed via a UUID-pattern regex over the rendered text that no UUID is present, confirmed the truncation CSS (`overflow: hidden`, `text-overflow: ellipsis`, `white-space: nowrap`) is actually applied to the value spans via `getComputedStyle`, and reconfirmed the ordinary web queue table is pixel-unchanged. `npx tsc --noEmit` clean, `npm run build` succeeds, all pre-existing `features/queue` tests (10/10) pass unmodified.

**Follow-up: blank paper feeding before the ticket printed** (reported after real POS-80 hardware use) — the `@page { size: 80mm auto; margin: 0; }` rule was declared inside the `@media print { ... }` block. On this hardware/driver combination the printer fed a long blank sheet *before* the ticket content, then cut: the driver was negotiating its own default (fixed, much taller) paper profile with Windows before the nested `@page` rule took effect, so the job briefly padded out to that default page length first. Fix: hoisted `@page { size: 80mm auto; margin: 0; }` to the top level of the stylesheet, outside `@media print` — both are valid CSS, but `@page` is inherently print-only regardless of nesting, and declaring it at the top level is negotiated earlier/more reliably by print pipelines. No other print rule changed; on-screen rendering is unaffected.

**User-verified on real hardware**: user confirmed printing is now correct on the physical POS-80 thermal printer after this change, with no blank feed before or after the ticket.

---

## Built — Post-RC1: TV Display 50/50 Queue + Information/Advertisement Panel

**Complete and live-verified, 2026-08-11.** Splits the TV Display into two equal vertical halves: the LEFT half is the existing Queue Display (Now Serving + Next in Queue) with its multi-doctor/multi-department/one-card-per-ticket behavior completely unchanged; the RIGHT half is a new admin-configurable Information/Advertisement Panel that auto-rotates through clinic content (service pricing, doctor information, health tips, preventive reminders, announcements, promotions, motivational messages). No queue creation, numbering, prefix, calling/recall, or announcement business logic was touched.

**New content model** - `tv_info_content` (migration `0027_tv_info_content`), clinic-wide (not per-display, unlike `tv_announcements`): `title`, `body`, `content_type` (7-value enum), `duration_seconds` (admin-configurable rotation interval, 3-120s, default 10), `display_order`, `is_active`, and a nullable `image_url`. Deliberately a separate table from the existing `tv_announcements` scrolling ticker - see `app/models/tv_info_content.py`'s docstring for the full rationale (different shape, different display mechanics, that feature is untouched).

**Photo upload** (added post-ship, per explicit follow-up request) - `POST/DELETE /tv-info-content/{id}/image`, a real local-disk upload+static-serving pipeline (`backend/var/tv_info_content_images/`, served unauthenticated via a `StaticFiles` mount at `/media/tv-info-content`), not the presigned-URL stub every other "photo" field in this codebase uses - a deliberate exception since the TV Display must keep working fully offline. See `docs/DATABASE.md` for the full rationale and `docs/TESTING.md` for upload-validation test coverage. Admin UI: each item on `/tv-info-content` gets a thumbnail preview and an "Add photo"/"Replace photo" control (client-side type/size pre-check, 5 MB max, JPG/PNG/WEBP only, mirroring the server-side validation).

**Backend** - `TvInfoContentRepository`/`TvDisplayService` CRUD methods (create/list/update/delete, soft-delete) plus `list_active_for_clinic` (active-only, ordered by `display_order`), reusing the exact same `require_config_manage_role`/`require_config_view_role` gates as every other TV Display admin operation. New `/tv-info-content` router (`GET`/`POST`/`PATCH /{id}`/`DELETE /{id}`). `TvDisplayData` gained one additive field, `info_content: TvInfoContentRead[]`, resolved into both the public snapshot and the authenticated preview endpoint.

**Frontend** - a pure, unit-tested rotation function (`lib/info-panel-rotation.ts::getRotationIndex`) maps elapsed time to the current content index using each item's own `duration_seconds`, kept framework-free so timing logic is directly testable without mocking timers. `InformationPanel.tsx` renders the current item with a smooth, non-distracting opacity cross-fade (no slide/bounce) and a dot-indicator row; renders a "No information to display" empty state when there's no active content. `TvDisplayScreen.tsx` now splits into a `flex` row of two `w-1/2` columns; the left column preserves 100% of its existing Now Serving/Next in Queue rendering, but the Now Serving density-tier font sizing (`now-serving-layout.ts`) and the admin-configured `FONT_SIZE_CLASS` were converted from `vw` (viewport-width) units to `cqw` (container-query-width, via `[container-type:inline-size]` on each half-column) - `vw` sizing assumed the full screen width and overflowed once halved; `cqw` correctly scales off each column's actual (now halved) width. New admin CRUD page at `/tv-info-content` (Owner/Administrator only, sidebar entry "TV Info Panel" under Clinic Configuration), following the same Dialog-free inline-form pattern used elsewhere in this codebase.

**Live-verified** at both 1920x1080 and 1600x900 (DOM `scrollWidth`/`clientHeight` measurement confirmed zero horizontal or vertical overflow in the halved Now Serving column, not just visual screenshot inspection): 3-simultaneous-ticket multi-doctor+laboratory display with a 5-item rotating info panel, no-queue-tickets state (empty Now Serving + populated info panel), and empty-info-panel state (all content disabled, populated queue) - see `docs/TESTING.md` for the full scenario matrix. `npm run build` succeeded across all 52 routes including the new `/tv-info-content` page. Backend test suite (10 tests, including 3 new: CRUD+role-gate, active/ordering filter, empty-panel) passed against the disposable test database; frontend `info-panel-rotation.test.ts` (5 tests) passed.

---

## Built — Post-RC1: Room-Based TV Announcements

**Complete and live-verified, 2026-08-11.** Adds an optional `room_label` (e.g. "Room 101") to the doctor/department/branch override row already used for queue prefixes (`queue_settings`, migration `0026_queue_setting_room_label`). When a room is configured for a destination, both the TV Display and the spoken queue-caller announcement say the room instead of the doctor/department name ("Please proceed to Room 101" instead of "...to Dr. Aurora Canora"); without one, behavior is byte-for-byte identical to before (doctor name, else department name, else the original unadorned phrasing for non-TV callers).

**Backend** - `queue_settings.room_label` (nullable `VARCHAR(50)`), same override chain and resolution semantics as `queue_prefix` (`TvDisplayService._resolve_room_label`, in-memory "narrowest scope wins", mirroring `QueueSettingRepository.get_effective_for_doctor`). `TvDisplayNowServing.room_name` — previously always `null` (no `consultation_rooms` FK link exists) — is now populated whenever a matching override configures one.

**Frontend** - `/queue-settings`' department/doctor override form gained an optional "Room" input alongside the existing prefix field. `queue-announcer.ts::buildAnnouncementText` now checks room first, then doctor, then department, then the original unadorned phrasing — existing non-TV callers (Doctor Workspace Call/Recall, Reception) are unaffected since they never pass a `roomName`.

**Live-verified**: configured Room 101/102/103 for three destinations (Dr. Aurora Canora, Dr. Rafael Canora, Laboratory), called tickets for each, confirmed both the TV Display card and the spoken Web Speech API announcement said the room instead of the doctor/department name; a destination left without a room configured fell back to the original doctor-name phrasing unchanged.

---

## Built — Post-RC1: Multi-Department / Multi-Doctor TV Queue Display

**Complete and live-verified, 2026-08-09.** Extends the existing TV Queue Display and queue-prefix configuration (see Phase 5 and Phase 13 below) to show multiple simultaneous doctors/departments at once, each with its own independent prefix and sequencing - built for the Canora Medical Clinic go-live under the same narrow freeze exception documented at the top of `RELEASE_NOTES.md`. Purely additive: no change to queue creation, calling/recall, or numbering logic, and single-doctor-clinic display behavior is unchanged (still renders the original clean flat single-queue layout, not a forced multi-column grid).

**Per-doctor queue prefix** - `queue_settings` gained a nullable `doctor_id` column (migration `0025_queue_setting_doctor_prefix`), mirroring the pre-existing nullable `department_id` scope column. `QueueSettingRepository.get_effective_for_doctor` resolves doctor override -> department override -> branch/clinic default -> hardcoded `"A"`, exactly one level narrower than the existing department-override chain. `QueueService._resolve_prefix`/`_resolve_max_daily_queue` now accept the ticket's `doctor_id` and pass it through. Resolution requires an EXACT match on `branch_id` too (a pre-existing characteristic of the department-override chain, not new) - see BUG-033 in `docs/BUGS.md` for a related pre-existing defect this surfaced.

**Admin UI** - `/queue-settings` gained a "Department & doctor prefix overrides" card: select a branch (auto-selected when the clinic has only one), a department and/or doctor, a prefix, and a daily cap; saves via the same `PUT /queue-settings` upsert endpoint, now keyed on the full `(branch_id, department_id, doctor_id)` scope instead of just `branch_id`. The `QueueSettingRead`/`QueueSettingCreate` schemas now expose `department_id`/`doctor_id` (and read-only `department_name`/`doctor_name`) - previously only the clinic-wide row was reachable via the API at all, despite the model already supporting department scoping since Phase 5.

**TV display department context** - `TvDisplayNowServing`/`TvDisplayWaitingEntry` gained `department_id`/`department_name` fields (`_build_display_data` now eager-loads `Queue.department`), so a mixed multi-department/multi-doctor result set can be labeled by destination on the frontend - doctor name when assigned, department name otherwise (e.g. a Laboratory/Radiology department-only ticket with no doctor).

**Frontend grouping** - `frontend/src/features/tv-display/lib/grouping.ts` (new, unit-tested) groups `now_serving`/`next_waiting` by destination (doctor if assigned, else department, else "General"). `TvDisplayScreen.tsx` renders one destination card per group when 2+ groups are active (Now Serving) and one labeled sub-list per group (Next in Queue) - when only one group is active (the ordinary single-doctor-clinic case), it renders the original flat grid/list with no group heading, unchanged.

**Announcer fixes** - `frontend/src/lib/queue-announcer.ts` gained `enqueueAnnouncement()` + a small local speak-queue so multiple tickets called/recalled within the same fetch cycle are each announced in full, spoken one after another (previously the loop `break`d after the first changed entry - a real gap once multiple doctors/departments can be active simultaneously - and `announceQueueNumber`'s `.cancel()`-before-`.speak()` behavior would have clobbered overlapping announcements anyway). `buildAnnouncementText()` is now destination-aware: `"Now serving patient number {N}. Please proceed to Dr. {name}."` for a doctor-assigned ticket, `"...Please proceed to the {department}."` for a department-only ticket; existing single-announcement callers (Doctor Workspace Call/Recall, Reception) are unchanged.

**Clinic-wide TV display** - confirmed live (not just by code inspection) that a `TvDisplayConfig` with `branch_id`/`department_id`/`doctor_id` all `NULL` already returns the full multi-department feed at the query layer - no new config concept was needed. `/tv` and `/tv/[slug]` (pre-existing routes) already serve this correctly; no new route was added.

**Live-verified** (see `docs/TESTING.md`'s Post-RC1 Multi-Department/Multi-Doctor TV Queue Display section for the full evidence): real API calls against a running dev backend created independent A/B/L/R prefix sequences (A001, B001, L001, R001, then A002, B002, all correctly independently numbered), all four called simultaneously and shown together on a real browser-rendered `/tv/[slug]` page with correct per-destination labels, a recall genuinely re-stamped `called_at` and re-announced (including two simultaneous recalls both being spoken in full, not just the first), single-doctor-clinic scoping still renders the original flat layout, `npm run build` succeeded across all 50 routes, and the backend test suite (plus two new tests) passed against the disposable test database.

---

## Built (Foundation Stage)

### Multi-tenant Authentication (Phase 2)

- JWT-based auth with short-lived **access tokens** and rotating, opaque **refresh tokens**; refresh tokens are hashed at rest (`refresh_tokens`/sessions table) and rotated on every `refresh` call — reuse of a revoked/rotated token revokes the full session chain.
- Endpoints wired against the real database: `login`, `logout`, `refresh`, `register`, `forgot-password`, `reset-password`, `verify-email`, `resend-verification`.
- `login`/`refresh` set the refresh token as an `HttpOnly`, `Secure`, `SameSite=Strict` cookie; `remember_me` on `login` controls session length (short session-only vs. extended ~7-day cookie).
- **Account lockout:** after repeated failed logins, `users.failed_login_attempts`/`locked_until` trigger a temporary lockout (`403`) independent of successful-login resets.
- **Password reset / email verification:** token-based flows (`password_reset_tokens`, `email_verification_tokens`) — tokens are hashed at rest, single-use, and time-limited. **TODO:** actual SMTP email delivery of the links is not yet wired up; token issuance/consumption logic is fully implemented (see [`SECURITY.md`](SECURITY.md), [`API.md`](API.md)).
- **Rate limiting:** Redis-backed limits enforced on `login`, `forgot-password`, `resend-verification`, and `refresh`.
- Passwords hashed with `passlib` using argon2 (bcrypt fallback supported).
- Every authenticated request carries `clinic_id` (tenant context) inside the JWT claims, resolved via a FastAPI dependency and injected into the repository layer.
- Login events (success/failure) and lockout events are written to `audit_logs`.
- Roles seeded at migration time: **Owner, Administrator, Receptionist, Doctor, Nurse, Cashier, Laboratory, Pharmacy, Viewer**, joined to `permissions` via `role_permissions`.

### User Management (Phase 2)

- Tenant-scoped CRUD for staff users under `/api/v1/users` — list/search (by name/email/username/role/status/branch), fetch, create, update, disable, enable, and admin-initiated password reset.
- Extended user profile fields: `middle_name`, `mobile_number`, `username`, `status` (`active`/`disabled`/`pending`), `profile_photo`.
- Create/update/disable/enable/admin-reset-password are role-gated to Administrator/Owner; a user may self-update their own non-privileged fields.
- Disabling a user immediately revokes all of their active refresh tokens/sessions.
- `frontend/src/features/users/` provides the corresponding UI (list/search table, create/edit forms, disable/enable actions) inside the `(dashboard)` route group.

### Patient Management (Phase 3)

- Tenant-scoped, branch-aware master patient database under `/api/v1/patients` — the record every future clinical module (queue, appointments, billing, laboratory, pharmacy, medical records, reports) will reference by `patient.id`.
- **Patient number generation:** sequential, clinic-scoped numbers (`PAT-000001`, ...) generated by a configurable `PatientNumberGenerator` backed by a per-clinic counter row in `system_settings` (not a raw DB sequence), so a clinic's numbering scheme (prefix/padding) can be customized later without a migration. Counter increments are safe under concurrent creates via `SELECT ... FOR UPDATE`.
- **Duplicate detection:** on create and on edits that change name/DOB/mobile, the backend checks for existing patients with the same first+last name and birth date, or the same mobile number. Matches are returned as a structured warning (`duplicates: [...]`) instead of the created/updated record; an Owner/Administrator can resubmit with `?override=true` to save anyway. Every other manage-capable role can create/edit but cannot bypass the warning.
- **QR check-in code:** a signed, opaque `clinic_id:patient_id:signature` token (HMAC-SHA256, app secret) generated per patient and stored in `qr_code`, exposed via `GET /patients/{id}/qr`. Verifiable by a future queue/appointment scanner without a DB round trip. Actual QR *image* rendering is intentionally deferred (see [`DATABASE.md`](DATABASE.md)) — only the payload string is returned today.
- Full CRUD + search: `GET /patients` supports free-text search (patient number, legacy patient id, name, mobile, email), filters (branch, gender, status, age range, date-registered range, last-visit range), sort (newest/oldest/alphabetical/recently visited), and limit/offset pagination with a total count.
- Archive/restore (`POST /patients/{id}/archive` / `/restore`) is a business-status change (`status: Active/Archived`), fully separate from soft-delete (`is_deleted`) which is not exposed on this API.
- Presigned-URL stub for patient photo upload (`POST /patients/{id}/photo`) matching the same Supabase Storage stub pattern used for user profile photos in Phase 2 — TODO: wire to real Supabase Storage + thumbnail generation once a bucket is provisioned.
- Every create/update (with a field-level diff)/archive/restore writes an `audit_logs` entry via the shared `AuditService`.
- Role gating: all clinic roles can view patients; Owner/Administrator/Receptionist/Doctor/Nurse can add/edit; Owner/Administrator/Receptionist can archive/restore; only Owner/Administrator can override a duplicate warning.
- Import/export extension points only: `services/patient_import_export.py` defines `PatientImporter`/`PatientExporter` ABCs (CSV/Excel/legacy-import, CSV/Excel/PDF-export) — no importer/exporter is implemented yet.
- `frontend/src/features/patients/` provides the corresponding UI: searchable/filterable/sortable patient list with debounced search, add/edit form (Identity/Contact & Address/Medical Info sections) with duplicate-warning confirmation, and a patient profile page with Overview/Personal Information/Medical Notes tabs plus "coming soon" placeholder tabs for Visit History, Appointments, Billing, Laboratory, Prescriptions, Documents, and Audit Logs.

### Clinic Configuration & Master Data (Phase 4)

Configuration/master-data CRUD consumed by future Queue, Appointments, Billing, Medical Records, and Reports modules. No queue/ticket, appointment/booking, or billing logic is implemented here — see [`ROADMAP.md`](ROADMAP.md) for those.

1. **Clinic Settings** — singleton-per-clinic settings (address breakdown, TIN/license, timezone/language/currency/date-format/time-format, status) added directly onto the existing `clinics` row (no separate table). `GET`/`PUT /clinic-settings`, Owner/Administrator write, all roles read.
2. **Branches** — extended the existing `branches` table with `code` (unique per clinic), `contact_number`, `email`, `manager_id` (FK to `users.id`), `status`. Full CRUD + search/pagination under `/branches`.
3. **Departments** — `department_code` (unique per clinic), name, description, color, status. `POST /departments/seed-defaults` optionally seeds 8 standard departments (General Medicine, Pediatrics, OB-Gyne, Internal Medicine, Dental, Laboratory, Radiology, Physical Therapy) for a brand-new clinic; 409s if the clinic already has departments.
4. **Doctors** — `doctor_code` auto-generated by a clinic-scoped `DoctorCodeGenerator` (parallel to `PatientNumberGenerator`, same `system_settings`-counter + `SELECT ... FOR UPDATE` pattern, kept separate to avoid touching the shipped Phase 3 patient code path), name/license/specialization/department/branch/fee/photo fields. `doctor_schedules` is a plain weekly availability table (`day_of_week`, `start_time`, `end_time`) with full CRUD under `/doctors/{id}/schedules` — architecture only, no appointment-slot generation or booking logic.
5. **Consultation Rooms** — room name/number, department, branch, status. Full CRUD under `/consultation-rooms`.
6. **Services** — a `services` catalog table (`ClinicService` model, to avoid a Python package name clash with `app/services/`): code/name/description/price/duration/department/status. `POST /services/seed-defaults` optionally seeds 7 standard services.
7. **Queue Settings** — pure configuration: `queue_settings` (prefix, max daily queue, reset time, allow-walkins, allow-priority-lane), unique per `(clinic_id, branch_id)` so a clinic can configure clinic-wide (`branch_id=null`) or per-branch. `priority_types` is a small per-clinic reference list (Senior, PWD, Pregnant, Emergency, VIP by default via `POST /queue-settings/priority-types/seed-defaults`). No ticket-issuing/calling/serving logic.
8. **Operating Hours** — `operating_hours` keyed by `(clinic_id, branch_id, day_of_week)`, with opening/closing time and an optional lunch-break window. Upsert via `PUT /operating-hours`.
9. **Holiday Calendar** — `holidays`: name, date, recurring flag, closed/half-day flags, optional `branch_id` (null = clinic-wide). Full CRUD + year/branch filtering under `/holidays`.
10. **Clinic Branding** — kept on the `clinics` row alongside settings (logo/favicon/login-background URLs, primary/secondary color, theme) rather than a separate table, since clinics do not need branding history/versions in this phase. `PATCH /clinic-settings/branding`; presigned-upload stub at `POST /clinic-settings/branding/{asset}/upload` (`logo`/`favicon`/`login-background`), same pattern as the Phase 2/3 photo-upload stubs.

Cross-cutting: every module is tenant-scoped (`clinic_id`), soft-deletable, role-gated (Owner/Administrator for writes; broad read access for operational roles via `require_config_view_role`/`require_config_manage_role` in `core/dependencies.py`), paginated/searchable/filterable where it's a list resource, and every create/update/delete/restore writes an `audit_logs` entry via the shared `AuditService`.

Frontend: `frontend/src/features/clinic-config/` provides a config-driven, reusable `MasterDataPage`/`MasterDataFormDialog` pair (table + create/edit dialog + delete confirmation, built on the existing `components/ui` primitives) shared by Branches/Departments/Doctors/Consultation Rooms/Services/Holidays, plus bespoke pages for Queue Settings, Operating Hours (weekly grid per branch), and Clinic Settings (tabbed General/Branding). All wired into the Sidebar under a new "Clinic Configuration" section. **Shortcut:** these modules use the backend's snake_case field names directly end-to-end rather than the fuller camelCase-domain-type mapping layer `features/patients` uses — documented in `features/clinic-config/types.ts`; doctor weekly-schedule editing has a backend API but no dedicated schedule-editor UI yet (doctor profile CRUD is covered).

### Frontend Application Shell

- Next.js 15 App Router structure with `(auth)` and `(dashboard)` route groups.
- Auth feature module (`src/features/auth`) — login/register forms using React Hook Form + Zod validation.
- Shared UI primitives via shadcn/ui (`src/components/ui`) and layout scaffolding (`src/components/layout`) — shell, sidebar, topbar placeholders for the dashboard.
- TanStack Query wired for server-state fetching/caching against the backend API.
- Strict TypeScript across the app; shared types live in `src/types`.

### Database Foundation Schema

Eight foundation tables, all multi-tenant-aware where applicable, all using UUID primary keys, `created_at`/`updated_at` timestamps, and soft-delete (`is_deleted`/`deleted_at`) where sensible:

`clinics`, `branches`, `users`, `roles`, `permissions`, `role_permissions`, `audit_logs`, `system_settings`, `subscriptions`.

- Every business table carries a `clinic_id` FK to `clinics.id`, enforced and scoped through a shared `TenantMixin`.
- `clinics` and `users` carry the `legacy_id` / `legacy_meta` (JSONB) pattern in preparation for importing data from the legacy Windows desktop application. The mixin is ready to apply to future business tables (patients, appointments, etc.) as they are built.
- Managed via Alembic migrations (see [`DATABASE.md`](DATABASE.md)).

### CI/CD & Tooling Skeleton

- GitHub Actions `ci.yml`: lint/test/build for both frontend (Node/npm) and backend (Python/pytest/ruff/black).
- GitHub Actions `deploy.yml`: skeleton deploy pipeline to Vercel (frontend) and Railway (backend), gated on secrets not yet provisioned.
- Dockerfiles for both apps plus a `docker-compose.yml` for local Postgres + Redis + backend + frontend.
- Dev bootstrap scripts under `scripts/`.

---

## Built — Phase 5: Reception & Queue Management

The primary daily receptionist workflow: search-or-create a patient, pick branch/department/doctor/service/priority, generate a queue number, track status, print a slip. Builds on Phase 4's master data (branches/departments/doctors/services) and `QueueSetting` configuration.

- Queue tickets (`queues`) with clinic+branch+prefix+date-scoped sequential numbering (`A001`, `A002`, ...), concurrency-safe via `QueueNumberGenerator` (`SELECT ... FOR UPDATE` + `INSERT ... ON CONFLICT DO NOTHING` on a dedicated `queue_counters` table).
- Priority lanes (Normal/Senior Citizen/PWD/Pregnant/Emergency/VIP) and a full status machine (Waiting → Called → Serving → Completed, plus Skipped/Cancelled/NoShow) with an append-only `queue_status_history` audit trail and `audit_service` logging on every write.
- Validation: rejects inactive doctor/department/service, archived/soft-deleted patients, and duplicate active tickets for the same patient+department+day (enforced both in the service layer and via a Postgres partial unique index).
- Role-gated REST API (`/api/v1/queues`) — Receptionist/Owner/Administrator create/manage/cancel, +Doctor/Nurse transition status, all clinical roles view.
- WebSocket broadcast architecture (`/ws/queues/{clinic_id}`) pushing `queue.created`/`queue.updated`/`queue.status_changed` events to an in-process connection manager, so the Reception Dashboard updates live. TV Display/Doctor Console consumers are out of scope for this phase — only the broadcast channel itself is built.
- Frontend `features/queue/`: Reception Dashboard (live today's-queue list, search + department/doctor/status/priority filters, prominent "New Queue" button), New Queue dialog (debounced patient search with an inline "create new patient" escape hatch, branch/department/doctor/service/priority pickers reusing the Phase 4 clinic-config hooks), Queue Details with a status-history timeline and action buttons for legal transitions, printable Queue Slip (large queue number, QR token, print trigger), reprint from the list.
- `QueueSetting` (Phase 4) extended with a nullable `department_id` for per-department prefix overrides; `LegacyMixin` extended with `legacy_created_at`/`legacy_updated_at`/`migration_batch_id`/`migration_source`/`imported_at` for future bulk-import provenance.

**Explicitly out of scope for this phase:** Doctor Console, TV Display consumer, Billing, Appointments, Medical Records.

---

## Built — Phase 6: Visit (Encounter) Management

The Visit is the central transaction every future clinical/billing module (SOAP notes, diagnosis, prescriptions, laboratory, billing) will attach to. A Visit is created automatically, transactionally, as part of raising a Reception Queue ticket — receptionists never create a Visit directly in normal operation.

- `visits` (the encounter record: patient/doctor/department/service/queue links, visit type, status, priority, arrival/check-in/called/consultation/check-out timestamps, remarks) and `visit_timeline_events` (append-only, human-readable domain timeline shown on the Visit Details page).
- Visit numbers (`VIS-YYYYMMDD-000001`) via `VisitNumberGenerator`, clinic+branch+date-scoped and concurrency-safe (`SELECT ... FOR UPDATE` + `INSERT ... ON CONFLICT DO NOTHING` on a dedicated `visit_counters` table), mirroring `QueueNumberGenerator`/`PatientNumberGenerator`.
- Queue → Visit integration: `QueueService.create_queue()` calls `VisitService.create_visit_for_queue()` internally in the same DB transaction as the queue-ticket insert, then links `queue.visit_id` ↔ `visit.queue_id`. The Phase 5 `POST /queues` request/response contract stays backward compatible (`visit_id`/`visit_number` are additive, optional response fields) — existing queue list/status-transition/cancel/slip endpoints are unmodified.
- Visit status machine (Registered → Waiting → Called → InConsultation → Completed, plus Cancelled/NoShow) with legal-transition checks, writing both to `visit_timeline_events` (domain timeline) and the generic `audit_service` (compliance audit trail) on every write.
- Role-gated REST API (`/api/v1/visits`) mirroring the Phase 5 Queue role matrix (View/Create/Modify/Close), plus `GET /patients/{id}/visits` for the Patient Visit History tab. `POST /visits` exists for internal/test/completeness use — the real-world trigger is queue creation.
- Search/filter/paginate by patient, doctor, department, status, visit type, and date range; free-text search across visit number, queue number, and patient name/number.
- Frontend `features/visits/`: Visit List page (search + date-range preset/status/visit-type filters, paginated, row click → details), Visit Details page (summary card, chronological Timeline component, clearly-labeled "coming soon" placeholder cards for SOAP Notes/Diagnosis/Prescription/Laboratory/Billing/Attachments/Audit Log — same pattern as the Phase 3 patient-profile placeholders), Patient Details "Visit History" tab (was a Phase 3 stub, now a real paginated visit table), Sidebar nav entry between Queue and Users.

**Explicitly out of scope for this phase:** Doctor Consultation/SOAP Notes, Medical Records, Billing, Prescription, Laboratory, Appointments, TV Display — only clearly-labeled placeholder sections referencing them as future work.

---

## Built — Phase 7: Doctor Workspace

The doctor's daily driver screen: today's assigned patients, quick visit actions, and a read-focused visit viewer with editing-lock coordination. Built entirely on top of the Phase 6 Visit lifecycle — no parallel status machine.

- `users.doctor_id` (nullable FK to `doctors`) resolves a logged-in Doctor-role account to its Doctor record, so "Doctors may only view Visits assigned to them" can be enforced server-side. `consultation_sessions` (one row per Start→Complete Consultation span, closed with a real `duration_seconds`), `visit_locks` (who currently has a Visit open for editing, with a documented acquire/release/expiry strategy), and `doctor_activity` (a domain-specific action log mirroring how `visit_timeline_events` relates to `audit_logs`).
- `DoctorWorkspaceService`: `call_patient`/`recall_patient`/`start_consultation`/`complete_consultation`/`mark_no_show`/`cancel_visit`/`open_visit`/`release_lock`. All Visit status changes are delegated to `VisitService.change_status()` (the Phase 6 legal-transition table) — this service only layers consultation-session tracking, doctor_activity logging, lock management, and WebSocket broadcast on top.
- `GET /doctor-workspace/dashboard` (real computed Waiting/Called/Serving/Completed Today/Cancelled/No-Show counts and average consultation duration) and `GET /doctor-workspace/queue` (today's assigned visits, with live-computed waiting time); Owner/Administrator can view any doctor's workspace via an optional `doctor_id` query param or see all doctors' visits by omitting it.
- Visit locking: opening a visit acquires a lock; the same user re-opening refreshes it; a different user is told who holds it (view-only, no edit access) rather than being blocked outright; a lock releases explicitly, when the visit reaches a terminal status, or after 15 minutes without a heartbeat refresh.
- Realtime: reuses the Phase 5 `queue_connection_manager` / `/ws/queues/{clinic_id}` WebSocket channel (rather than a second connection manager) to broadcast `visit.called`/`visit.consultation_started`/`visit.consultation_completed`/`visit.status_changed`/`visit.lock_acquired`/`visit.lock_released`, so a future TV Display can subscribe to the same channel.
- Role gating (`core/dependencies.py`): Doctor is scoped to their own linked Doctor record's visits; Owner/Administrator may view/act on any doctor's visits; Receptionist gets view-only access ("Reception cannot modify doctor actions").
- Frontend `features/doctor-workspace/`: Doctor Dashboard page (stat cards, Today's Queue table with contextual Call/Recall/Start/Complete/No-Show/Cancel actions and live-computed waiting time), Sidebar nav entry, and the existing Phase 6 Visit Details page extended (not duplicated) with a lock banner ("Currently being edited by Dr. ___") and a doctor-actions panel visible to Doctor/Administrator/Owner viewers.

**Explicitly out of scope for this phase:** SOAP Notes, Diagnosis, Prescription, Laboratory, Billing, Medical Records, Appointments, TV Display — only clearly-labeled placeholder sections referencing them as future work.

---

## Built — Phase 8: Clinical Consultation / SOAP

Turns a Visit into a documented clinical encounter: SOAP notes, diagnosis, a tabbed consultation page, autosave, locking, and read-only history review — built on top of Phase 6's Visit lifecycle and reusing Phase 7's `visit_locks` rather than a second lock table.

- `consultations` (one clinical encounter per Visit, "latest wins" query pattern), `soap_notes` (one-to-one, upserted in place on autosave — never a new row per save), `diagnoses` (Primary/Secondary, Working/Final, ICD-10 fields architecture-only, no search UI), `consultation_attachments` (real upload path for Clinical Images/PDF/Referral Letters — Lab Requests stay a placeholder with no upload path), plus `patients.emergency_contact_name`/`emergency_contact_phone` closing the Phase 7 TODO.
- `ConsultationService`: `open_consultation` (creates/resumes the visit's Draft consultation, acquires the reused `visit_locks` lock), `save_soap` (autosave-safe upsert, server-computed BMI, Draft→InProgress bump, writes timeline/audit only when content actually changed — not on every 30-second poll), `add_diagnosis`/`update_diagnosis`, `complete_consultation` (Completed, and — the critical Phase-7-lesson fix — syncs **both** `Visit.status` and the linked Queue ticket's status, verified live via curl that neither is left stuck), `sign_consultation` (final lock-in step beyond Completed).
- Role gating stricter than Phase 7: only the visit's assigned doctor may edit SOAP/diagnosis/attachments; Owner/Administrator are view-only (never edit); Receptionist is excluded entirely — 403 on both view and edit.
- Frontend `features/consultation/`: a tabbed Consultation page (`/visits/[id]/consultation`) — Overview / SOAP / Diagnosis / Orders (placeholder) / Prescription (placeholder) / Attachments (real upload) / Timeline / Audit Log (placeholder) — with an always-visible Patient Summary header (photo, patient/visit/queue numbers, age, gender, blood type, allergies, emergency contact), live client-side BMI matching the server computation, a real dirty-tracking autosave hook (30s interval + `beforeunload` warning only while genuinely dirty), and Phase 7's `LockBanner` reused as-is.

**Explicitly out of scope for this phase:** Prescription, Laboratory Orders (beyond the Lab Requests placeholder attachment type), Billing, Cashier, Appointments, TV Display.

---

## Built — Phase 9: Clinical Orders & Prescriptions

Lets a doctor record Laboratory/Radiology/Vaccination/Custom orders, Procedures, Referrals, and Prescriptions during an in-progress consultation — creation + status field + read-only display only, built on top of Phase 8's Consultation the same way Diagnosis was.

- `orders`/`order_items` (shared `Requested/Collected/Processing/Completed/Cancelled` status across categories; `order_items` has nullable typed Imaging fields `exam_type`/`body_part`/`clinical_indication`), `procedures` and `referrals` as their **own tables** (not `orders` rows — the spec lists them as standalone tables and Procedures has no Order Number field), `prescriptions`/`prescription_items` (Draft/Finalized/Cancelled header + unlimited line items).
- `OrderNumberGenerator`/`PrescriptionNumberGenerator` reuse the `system_settings`-backed counter pattern (`ORD-YYYYMMDD-000001`, `RX-YYYYMMDD-000001`).
- `ClinicalOrdersService.create_prescription` returns non-blocking validation `warnings` (duplicate medicine, missing dosage, missing duration) alongside a successful save — verified live that a prescription missing a dosage still saves. Allergy-conflict checking is an explicit architecture-only placeholder (`check_allergy_conflicts()` always `[]`, no drug database yet).
- Creating an order/procedure/referral/prescription does not change Consultation/Visit status (per the workflow, these happen *during* an in-progress consultation) but every creation writes a `visit_timeline_events` row + audit entry, same pattern as Phase 8's diagnosis-add — the Phase 7/8 "reflect onto the parent" lesson applied again, verified live via curl.
- Role gating: assigned doctor edits; Owner/Administrator view-only; **Receptionist read-only** (distinct from Phase 8's Receptionist-excluded-entirely SOAP rule); new **Laboratory** role scoped to Laboratory-category orders only (`GET /laboratory/orders`), no access to anything else in this module.
- Frontend `features/clinical-orders/`: Orders/Procedures/Referrals creation forms + lists (category select, priority, scheduled date, Imaging-specific fields), a repeatable Prescription line-item form with inline non-blocking validation warnings and a static common-medicines autocomplete list, wired into the Consultation page's Orders/Prescription tabs (replacing the Phase 8 placeholders), the Visit Details page's read-only Orders/Prescription tabs, and the Patient Profile's Prescriptions view.

**Explicitly out of scope for this phase:** Billing, Cashier, Laboratory/Radiology *processing* (specimen tracking, result entry), Appointments, TV Display.

---

## Built — Phase 17: Billing & Cashier

Turns a completed Consultation into a billable, payable, receiptable encounter — invoices, line items, discounts, split payments, void, and receipts — built on top of Phase 6's Visit and Phase 8's Consultation, using the services *catalog* (code/name/default price) Phase 4 built plus `Doctor.consultation_fee`.

- `invoices`/`invoice_items` (Draft→PendingPayment→PartiallyPaid→Paid→Cancelled), `invoice_counters` (backs `INV-YYYYMMDD-000001`), `discounts` (invoice-level: Senior Citizen/PWD/Employee/Custom, percentage or fixed, with reason + approver), `payments` (split payments as multiple rows per invoice; Cash/GCash/Bank Transfer/Credit Card/Debit Card), `refunds` (architecture-only — model + stub service methods, no UI).
- `InvoiceService.create_draft_invoice_for_consultation` — called automatically from `ConsultationService.complete_consultation()` (the Phase 7/8 lesson applied again), idempotent (a repeat complete() call never duplicates the invoice), auto-adds a priced Consultation Fee line item (`Doctor.consultation_fee` first, falling back to the visit's service catalog price).
- `PaymentService.record_payment` (single or split, transitions Draft-invalid→PendingPayment→PartiallyPaid→Paid based on amounts, and on reaching Paid syncs the linked Visit to `Completed` if not already terminal — the spec's "Visit Closed" step, verified live via curl), `void_payment` (recomputes status backward from the remaining Completed payments, not a naive decrement).
- `ReceiptService` generates a computed (not persisted) printable receipt payload — clinic/branch/patient/visit/cashier/date/items/discounts/totals/payment method+reference — and records a "Receipt Printed" audit entry when actually printed.
- Role gating: Cashier + Owner/Administrator manage; Administrator/Owner-only refund approval (stub); Doctor view-only; **Receptionist read-only** (reads succeed, writes 403 — the spec's "Reception: Read-only," distinct from Phase 8's stricter Receptionist-excluded-entirely rule for SOAP).
- Frontend `features/billing/`: Cashier Dashboard (`/billing` — Pending Payments/Paid Today/Today's Revenue/Outstanding Balance/Refunds Pending/Recent Payments stat cards, search + status filter, invoice list), Invoice Details page (`/billing/[id]` — line items, discount application, split-payment dialog, printable receipt dialog reusing the Phase 5 Queue Slip's `window.print()` CSS pattern), a real "Billing" card on Visit Details (replacing the Phase 6-8 placeholder) and a real "Billing History" tab on Patient Profile (replacing the Phase 3 placeholder), Sidebar nav entry.

**Explicitly out of scope for this phase:** Laboratory, Pharmacy, Appointments, TV Display, Patient Portal, a full Refund UI/workflow (architecture only), Reports (the data model is billing-ready — invoices/payments carry everything a future revenue report would need — but no report pages/endpoints were built).

---

## Built — Phase 10: Laboratory Management

Adds the laboratory department's own workflow on top of Phase 9's doctor-facing Laboratory-category orders: a Laboratory Dashboard, specimen collection → processing → result entry → release, a configurable test/reference-range/pricing template catalog, and full visibility across the Consultation Orders tab, Visit Laboratory tab, Visit Timeline, and Patient Laboratory history.

- `laboratory_orders` (1:1 with a Phase 9 `Order`, own `Requested/Collected/Processing/Completed/Released/Cancelled` status enum — the extra terminal `Released` state Phase 9 never needed), `laboratory_results` (one row per result parameter, numeric or text valued, ~10 rows for a CBC), `laboratory_attachments` (reuses Phase 8's presigned-URL-stub pattern), `laboratory_templates`/`laboratory_template_parameters` (the Administrator-configurable "add a new test without code changes" catalog — test name/category/specimen type/price/turnaround plus per-parameter name/unit/normal range).
- `ClinicalOrdersService.create_order` automatically attaches a `laboratory_orders` row whenever a Laboratory-category order is created (idempotent, best-effort matched against an active template by test name), so the Lab Dashboard sees new orders with zero extra doctor-facing steps.
- `LaboratoryService`: `collect_specimen`/`start_processing`/`enter_results` (replace-all upsert per submission, advances to `Completed` on first entry)/`release_results`/`cancel_order`, each writing a `visit_timeline_events` row (`LabSpecimenCollected`/`LabProcessingStarted`/`LabResultsEntered`/`LabResultsReleased`/`LabOrderCancelled` — "Ordered" intentionally not re-recorded, Phase 9's `OrderCreated` already covers it) and an audit entry, plus — the Phase 7/8/9 lesson applied a fourth time — mirroring status onto the underlying Phase 9 `Order.status` so the Consultation page's Orders tab reflects lab progress instead of staying stuck on `Requested`.
- **Billing integration**: completing a template-priced lab order automatically adds/updates an `InvoiceItemType.LABORATORY` line item on the visit's invoice via the same `InvoiceService.create_draft_invoice_for_consultation` entry point Consultation-completion uses. Idempotent via a nullable `invoice_item_id` FK on `laboratory_orders` — a real cross-order id-collision bug was found and fixed live during this phase's development (see `docs/DATABASE.md`).
- Role gating: Laboratory role (plus Owner/Administrator) collects/processes/enters-results/releases/cancels; Doctor still only creates orders (unchanged); Receptionist read-only; Administrator/Owner-only template mutation.
- Frontend `features/laboratory/`: Laboratory Dashboard (`/laboratory` — Pending/Collected/Processing/Completed Today/STAT/Cancelled stat cards, a status-contextual-action worklist), a multi-parameter Result Entry dialog (numeric or text rows, normal range/units/interpretation/remarks, add/remove rows), a real Visit Details "Laboratory" card (replacing the Phase 6-9 placeholder), a real Patient Profile "Laboratory" tab (replacing the Phase 3 placeholder), and an Administrator-only Laboratory Test Templates admin page (`/laboratory-templates`) for the configurable catalog.

**Explicitly out of scope for this phase:** Pharmacy, Appointments, TV Display, Patient Portal, Reports.

---

## Built — Phase 11: Appointment Management

Full booking lifecycle (Booked → Confirmed → Checked-in → Queue Generated → Visit Created → Doctor Consultation → Billing), built on top of Phase 4's `doctor_schedules` availability configuration and reusing Phase 5/6's `QueueService.create_queue()` for check-in.

- `appointments` (nine-status enum incl. Waiting/InConsultation as post-check-in states, `APT-YYYYMMDD-000001` numbering, partial unique index rejecting exact doctor+date+start_time double-booking except for Cancelled/Rescheduled/NoShow rows), `doctor_schedules` extended in place with lunch break/slot duration/daily cap/recurring-override columns, `doctor_schedule_blocks` (vacation/blocked dates), `appointment_reminders` (architecture-only), `appointment_notes`, `appointment_history` (domain audit trail mirrored into `audit_logs`), `waitlist_entries`.
- Time Slot Engine (`services/time_slot_service.py`) computes available slots on demand from the doctor's weekly schedule minus lunch break minus existing non-cancelled appointments minus holidays (Phase 4's `holidays` table) minus doctor-specific blocked/vacation dates — never persisted as a table (see `docs/DATABASE.md`).
- Check-in (`POST /appointments/{id}/check-in`) is the single action that creates a real linked Queue ticket AND Visit, by calling the existing `QueueService.create_queue()` (an additive `visit_type` kwarg, default unchanged) rather than duplicating that logic — the resulting Visit is tagged `visit_type=Appointment` and the Timeline gets a new `AppointmentCheckedIn` event.
- Reschedule creates a fresh Booked row and marks the original Rescheduled (terminal), recording old/new date-time in `appointment_history`; cancel offers the freed slot to the oldest matching `WaitlistEntry` (a real state change, no notification sending).
- Role gating: Reception (+Owner/Administrator) create/edit/reschedule/cancel/check-in; Doctor completes/no-shows (+Owner/Administrator); doctor schedule administration Administrator-only; broad read access for Cashier/Laboratory too (appointment context is relevant across modules).
- Frontend `features/appointments/`: Appointment Dashboard (`/appointments` — search/filter, New Appointment dialog reusing the Queue feature's patient-search pattern plus a live Time Slot Engine picker, status-contextual action buttons), Appointment Details dialog with a history timeline, a real Patient Profile "Appointments" tab (Upcoming/Completed/Cancelled/No-show buckets, replacing the Phase 3 placeholder), Sidebar nav entry.
- Calendar: a List/Calendar toggle on the Appointment Dashboard renders `AppointmentCalendar` (`features/appointments/components/AppointmentCalendar.tsx`) — Day/Week/Month/Agenda views built with plain React/CSS grid (no new calendar library dependency, consistent with this project's dependency-free UI-primitive convention), filterable by Doctor/Department/Branch/Appointment Type, wired to `GET /appointments/calendar`. Month/Week render a real grid with clickable appointment chips; Day/Agenda render as sorted lists.
- Doctor Schedule admin page (`/doctor-schedules`, Sidebar entry under Doctors, Administrator/Owner-only): a doctor picker plus `DoctorScheduleForm` — a 7-day working-hours grid (enabled toggle, start/end, lunch start/end, slot duration, max-per-day) that `PUT`s the whole week at once, and a vacation/blocked-dates list with add/remove, wired to `GET/PUT /doctors/{id}/schedule` and `POST/DELETE /doctors/{id}/schedule/blocks`. Verified live: changing Dr. Maria Santos's Monday hours here immediately changed the slots the New Appointment dialog's Time Slot Engine picker offered for a Monday date.

**Explicitly out of scope for this phase:** actual SMS/Email/Push reminder sending (architecture-only schema + stub), Teleconsultation video, Patient Portal, TV Display.

---

## Built — Phase 12: Owner Dashboard & Reports

A read-only aggregation/reporting layer over every operational table built so far — no new tables, no duplicated business logic (see `docs/DATABASE.md`'s Phase 12 section for the full "which repository owns which metric" map).

- Owner Dashboard (`GET /analytics/dashboard`): 16 stat cards — Patients/New Patients/Appointments/Walk-ins Today, Completed Consultations/Cancelled Visits/No Shows Today, Laboratory Orders/Prescriptions Issued Today, Pending Payments (count+amount)/Collected Revenue Today/Outstanding Balance, Avg Waiting/Consultation Time, Doctors On Duty, and Rooms In Use (`null` — see the "TODO" note below).
- Real-time Activity Feed (`GET /analytics/activity-feed`): merges and sorts `visit_timeline_events` + `queue_status_history` + `audit_logs` — a real, queried feed, not a new event-logging mechanism.
- Owner Alerts (`GET /analytics/alerts`): live threshold checks (High Queue Volume, Long Waiting Time, Outstanding Payments) computed on request against live data, not persisted notifications. System Errors/Failed Backups are explicitly out of scope (no infra monitoring exists yet).
- Six reports (Patient/Doctor/Revenue/Queue/Laboratory/Appointment), each accepting a `date_range` preset (`today`/`yesterday`/`last_7_days`/`this_month`/`last_month`/`custom`) plus optional `doctor_id`, with chart-ready `{label, value}` series for every trend (Daily Patient Census, Monthly Revenue, Doctor Workload, Revenue by Service, Appointment Trend, Queue Volume by Hour, Laboratory Trend, Age/Gender Distribution).
- CSV export (`GET /analytics/reports/{report}/export?format=csv`) is a real, working file download via stdlib `csv`; `format=excel` reuses the same CSV body (Excel-compatible; no new dependency added for this scope); `format=pdf` is an explicit `501` stub per the spec's "do not implement PDF styling yet" exclusion.
- Role gating (`require_analytics_role`, `core/dependencies.py`): **Owner and Administrator only** — the simplest, strictest gate in the project. Every other role (Doctor/Cashier/Receptionist/Laboratory) gets `403` on every `/analytics/*` endpoint, including roles with their own scoped dashboards from earlier phases.
- Report-generation audit: reuses the existing `audit_logs` table (`action = "analytics.report_generated.<report>"`) rather than a new table.
- Frontend `features/analytics/`: Owner Dashboard page (`/analytics`, Sidebar nav entry shown only to Owner/Administrator sessions, backend still enforces `403` regardless), a grouped stat-card grid ("Today's Activity" / "Clinical" / "Financial"), the live Activity Feed, an Alerts banner, and six report sections each with its own date-range filter and zero-dependency inline-SVG bar/line charts (no charting library added, consistent with this project's convention). Since this dashboard has no direct mutations of its own to hook cache-invalidation into, staleness is handled by a 30s `refetchInterval` + `refetchOnWindowFocus` polling policy instead (documented in `features/analytics/hooks/use-analytics.ts`).
- **TODO, not a bug**: "Rooms In Use" is `null` — neither `visits` nor `consultations` currently track a `consultation_room_id` assignment (`consultation_rooms` exists as master data only). The dashboard schema field and frontend card are wired and ready to receive a real value once a future phase adds that linkage.

**Explicitly out of scope for this phase:** TV Display, Patient Portal, Migration Wizard, Production Deployment, real PDF export styling (explicit `501` stub only).

---

## Live TV Queue Display (Phase 13)

A fullscreen, kiosk-grade waiting-area display reusing the Phase 5/7 realtime WebSocket channel, with a genuinely public (no-JWT) mode:

- Display configs (`tv_display_configs`) scoped clinic-wide or narrowed to a branch/department/doctor ("Waiting Area TV" = branch-scoped, no department/doctor), each with theme/font-size/queue-size/animation-speed/refresh-interval/logo/color settings and an `is_public` + unique `public_slug` public-URL toggle.
- Announcements (`tv_announcements`), clinic-wide or per-display, typed (Welcome/HealthTip/Promotion/Emergency), orderable, and date-range-schedulable.
- `GET /public/tv-display/{public_slug}` — no `Authorization` header at all, resolving Now Serving/Next N Waiting (patient **initials only**, never a full name) + announcements, filtered to `ACTIVE_QUEUE_STATUSES` and the config's scope; unknown/private/inactive slugs 404 cleanly.
- The public display's WebSocket connection reuses the existing `/ws/queues/{clinic_id}` channel, authenticating with its `public_slug` in place of a JWT (see `docs/API.md`'s WebSocket section for the full rationale) — no second realtime channel was built.
- First reconnect-with-exponential-backoff logic in the project (`useTvDisplayRealtime`); the pre-existing Phase 5 Reception queue hook has none.
- Text-to-speech is architecture-only: a real string-templating `generate_announcement_text()` plus `tts_enabled`/`tts_template` config fields; no audio synthesis.
- Frontend: standalone `/tv/[slug]` route (no dashboard shell, no auth), fullscreen toggle, live clock, scrolling announcement ticker, real TTS announcements (`announceQueueNumber`) gated behind a one-time "Enable Sound" tap, unobtrusive connection-status indicator. Owner/Administrator-only admin UI at `/tv-displays`.
- **Known gap**: `Queue`/`Visit` have no FK to `ConsultationRoom` yet, so "Room" is omitted from the display payload rather than guessed at.
- **Bare `/tv` route (2026-07-29)**: a zero-configuration convenience route for single-clinic/single-TV on-prem deployments — no slug in the URL. Resolves which display to show via the `NEXT_PUBLIC_DEFAULT_TV_SLUG` frontend env var (`.env.example`); with no slug resolved, shows a clear "No display configured" state instead of a crash. Falls back to `/tv/<slug>` for anyone needing a specific display (multi-branch clinics unaffected — that route's behavior is unchanged). Shares all realtime/announcement/fullscreen logic with `/tv/[slug]` via the extracted `frontend/src/features/tv-display/components/TvDisplayScreen.tsx`, plus new kiosk-mode behavior applying to both routes: best-effort `?fullscreen=true` auto-fullscreen (browser Fullscreen API requires a user gesture and was confirmed blocked in live testing when triggered from a query param — the maximized CSS layout still applies unconditionally), cursor auto-hide after 3s idle, locked `overflow: hidden`, Screen Wake Lock (feature-detected, request-on-mount/release-on-unmount), and `vw`/`clamp()`-based type scaling verified at 1920x1080, 1366x768, and 4K (3840x2160). No backend/schema changes — see `docs/BUGS.md` BUG-023 for the deferred DB-level "clinic default display" design.

**Explicitly out of scope for this phase:** Migration Wizard, Patient Portal, Production Deployment, real text-to-speech audio synthesis.

---

## Legacy Migration Wizard (Phase 14)

The payoff for the `LegacyMixin` columns every entity table has carried since Phase 5 — a real, resumable, idempotent import engine, Owner/Administrator only:

- `migration_batches`/`migration_entity_progress`/`migration_field_mappings`/`migration_validation_issues`/`migration_logs` (migration `0014_legacy_migration_wizard`); an audit found `branches`/`departments`/`doctors`/`services` missing `LegacyMixin` and backfilled it in the same migration.
- CSV and Excel source adapters are fully working; SQLite/Access/SQL Server/MySQL/PostgreSQL have a real `SourceAdapter` interface + registry but raise `NotImplementedError` (no client database technology identified yet — see `docs/MIGRATION.md`).
- Idempotency via `legacy_id` + `migration_batch_id` lookup before every insert (no separate `sync_hash` column) — proven with a real double-import test creating zero new rows on re-run.
- Fuzzy/synonym field-mapping suggestions, DateFormat/PhoneFormat/Trim transforms, validation reusing Phase 3's Patient duplicate-detection pattern plus required-field/date/phone/email checks.
- 17-step entity import order, 500-row batched transactions (rollback-on-failure), background-task execution, live-polling Migration Dashboard, persisted Verification Report, Migration History.
- **Only Patients and Doctors write to a real destination table** in this phase; the other 15 entity types get full mapping/validation support but are marked `Skipped` on import (see `docs/MIGRATION.md`).
- Frontend `/migration`: 8-step wizard (Choose Source → Connect → Analyze → Map Fields → Preview → Validate/Resolve Issues → Import → Verify) plus history.

**Explicitly out of scope for this phase:** production deployment; fully-working non-CSV/Excel adapters; importing the 15 non-Patient/Doctor entity types end-to-end.

---

## SaaS Administration Portal (Phase 15)

A second, structurally separate portal for CONNECT.PH platform staff (not clinic staff) — the first phase to deliberately grant real cross-tenant access, without weakening tenant isolation for any existing clinic-scoped role. Full architecture rationale in `docs/ARCHITECTURE.md` §7.

- **Platform Administrator accounts** (`platform_admin_users` — a structurally separate table/model from `users`, no `clinic_id`), four roles: PlatformAdministrator (full access), SupportEngineer (tenant-user admin + view), ImplementationTeam (tenant/subscription/flag management + view), Auditor (read-only everywhere).
- **Separate login** (`POST /platform-admin/auth/login`) issuing a JWT with a completely different claim shape from the clinic portal's tokens — verified to be mutually rejected by both auth systems.
- **Tenant management**: list/search/create/suspend/reactivate/archive clinics platform-wide; real per-tenant stats (user count, storage usage) computed live, never cached; suspending a tenant force-logs-out its users and blocks further logins.
- **Subscription/license management**: plan/trial/renewal/expiration dates, max-users/max-branches/storage-limit/API-rate-limit fields — manually-editable records, no automated billing.
- **Feature flags**: 8 togglable keys per tenant (appointments/laboratory/tv_queue/migration_wizard/inventory/teleconsultation/ai_assistant/patient_portal); only `appointments` is wired into an actual clinic-facing check (Sidebar visibility) as a proof of concept.
- **Tenant user administration**: a platform admin can reset a tenant user's password, lock/unlock their account, and force-logout their sessions — reusing Phase 2's account-lockout fields and `refresh_tokens` table.
- **System Health dashboard**: real aggregate stats (clinics, subscriptions, online users, `pg_database_size()`, background jobs) — no fabricated numbers; unavailable metrics (API request counts) are explicitly `null` with a documented TODO rather than fake data.
- **Background jobs monitoring**: surfaces the one real background-style task in the codebase (Phase 14 migration imports) — no invented job-queue system.
- **Platform audit log**: every tenant/subscription/feature-flag/platform-admin write is recorded, separate from the per-clinic `audit_logs` table.
- **Frontend**: `app/platform/` — a genuinely separate portal (own layout/branding/login/token-storage-keys/middleware-protection), not nested under the clinic portal's `(dashboard)` group.

**Explicitly out of scope for this phase**: real payment-gateway billing/automated charging; Patient Portal/Teleconsultation/AI Assistant/Inventory (flag keys exist as placeholders only); API-key-based request authentication (CRUD + hashing exists, not wired into endpoints); real email/SMS/AI/storage provider integration behind `platform_config`; a real `pg_dump`-backed backup (documented stub — `pg_dump` unavailable in this dev sandbox) and real restore (architecture-only stub); exhaustive feature-flag retrofitting into every module (only Appointments got the proof-of-concept wire-up).

## Production Hardening (Phase 16)

A cross-cutting hardening pass across the whole codebase, evidence-first (real `EXPLAIN ANALYZE`/FK-index analysis/live endpoint timing before any change) rather than a speculative rewrite:

- **Database**: migration `0016_hardening_indexes.py` — additive indexes only, for confirmed-missing FK/composite cases (`laboratory_orders.branch_id`/`.doctor_id`, `invoices`/`laboratory_orders` composite `(clinic_id, status)` and `(clinic_id, invoice_date)`).
- **Observability**: `/live` + `/ready` probes alongside the existing `/health`; request-id tracing (`X-Request-ID` header + structured log correlation) on every request; a standardized error envelope (`detail` + `request_id`) across every error response shape.
- **Security review**: file-upload validation added where a real gap existed (consultation/laboratory attachments, migration wizard uploads); CORS/rate-limiting/SQL-injection-surface/secrets all reviewed with real findings documented in `docs/SECURITY.md` (most needed no change — already sound).
- **Caching**: a real, invalidation-backed TTL cache for the departments list and feature-flag checks — verified live that an edit is reflected immediately, not after the TTL window.
- **Backup verification**: Phase 15's bare `backups` table now has a real `pg_dump`-backed service behind it, with real output verification; restore stays a documented, human-executable, deliberately non-automated procedure (`docs/BACKUP.md`).
- **Load testing**: a real, runnable concurrent load-test script against a dedicated synthetic tenant, with real numbers reported.
- **Cross-browser/accessibility**: a real but honestly-bounded pass, with the sandboxed environment's real limitations (one browser engine, no real screen reader/mobile device) documented rather than glossed over.

**Explicitly out of scope for this phase**: business-logic changes to any of the 15 preceding feature modules; database schema restructuring beyond additive indexes; speculative frontend bundling/code-splitting changes without a measured problem; exhaustive cross-browser/accessibility/load-testing coverage this sandboxed environment cannot actually provide.

## Pilot Deployment & User Acceptance Testing (Phase 17)

Not a new feature module — a readiness/verification pass. No new business features were added; no schema change. See `docs/PILOT_READINESS.md` for the full report and `docs/ROADMAP.md`'s Phase 17 (v0.17.0) section for the checklist.

- A real pilot tenant configured end-to-end via live API calls (branch, departments/services, doctor + schedule, operating hours, queue settings, staff users).
- The Phase 14 Legacy Migration Wizard exercised hands-on with a realistic sample dataset — one real High-severity bug found and fixed (`docs/BUGS.md` BUG-001: resolving a validation issue had no effect on import).
- A full 17-step scripted UAT of the patient journey (Registration through Completion), 17/17 passing.
- New docs: `docs/PILOT_READINESS.md`, `docs/USER_MANUAL.md`, `docs/ADMINISTRATOR_GUIDE.md`, `docs/SUPPORT_GUIDE.md`.

**Explicitly out of scope for this phase**: any new business feature; real user training; real human sign-off from clinic staff; a real production deployment — see `docs/PILOT_READINESS.md`'s "What remains" section.

## Patient Portal (Phase 18)

A THIRD, structurally separate portal alongside the clinic-staff portal and Phase 15's SaaS Administration Portal — patients are a third class of principal, not a clinic `User` and not a `PlatformAdminUser`. Follows the Phase 15 precedent exactly: a dedicated auth table, a JWT with a distinct `type` claim, and a completely independent FastAPI dependency chain.

- **Patient auth** (`patient_accounts` — a new one-to-one table linked to the existing `patients` table by `patient_id`, chosen over adding password columns directly to `Patient` since login-credential data has a different write-path/threat-model than clinic-managed demographic data): login by email OR mobile number + password, a JWT with `"type": "patient_access"`/`"patient_refresh"` (never `"access"` or `"platform_admin_access"`), and a new `get_current_patient` FastAPI dependency that is the only thing that accepts it — verified mutually rejected against `get_current_user` and `get_current_platform_admin` in both directions.
- **Forgot/reset password** reusing the existing email-based reset flow's pattern (`generate_secure_token`/`hash_token`/single-use expiring row) against a new patient-scoped `patient_password_reset_tokens` table — never the staff `password_reset_tokens` table.
- **OTP and social login**: architecture note only (`PatientAccount.auth_method` is a plain string column documenting only `"password"` today; future values like `"otp_sms"`/`"google"` are named in the model docstring) — no working code.
- **Patient dashboard**: upcoming appointments, recent visits, outstanding balance, latest released lab results, recent prescriptions, and a static clinic-announcements placeholder (no clinic-announcements feature exists yet to reuse).
- **Profile**: update contact info, a photo-upload stub reusing the same presigned-URL-stub pattern as clinic-staff Patient Management (`PatientService.request_photo_upload_url`), change password, and a simple notification-preferences settings row (`patient_notification_preferences` — in-app only, no real push/email delivery wiring).
- **Appointments**: view-only, Upcoming/Completed/Cancelled/Rescheduled tabs, reusing the existing `Appointment` model/read path scoped to `patient_id` + `clinic_id`.
- **Laboratory**: view-only, Released-status results only (`LaboratoryOrderStatus.RELEASED`) — Requested/Collected/Processing/Completed orders are invisible to the patient. PDF download is a documented placeholder (no existing lab-result PDF/export mechanism exists to reuse).
- **Prescriptions**: current vs. past (by `PrescriptionStatus`), dosage/instructions/issue date, read-only.
- **Medical records**: read-only, and ONLY explicitly patient-visible diagnoses/attachments — new `patient_visible` boolean columns added to `diagnoses` and `consultation_attachments` (migration `0017_patient_portal.py`), defaulting to `false` (safer default: clinic staff must opt a record in, nothing is exposed by default).
- **Billing**: invoices, line items, payment history, outstanding balance, all read-only. Online payment: architecture note only, not implemented.
- **Notifications**: a simple read-only in-app feed (`patient_notifications`) — no background job/scheduler, matching the "none existed for an equivalent feature before this phase" scoping rule.
- **Security**: every patient login and every profile change is audit-logged (reusing the existing `AuditLog` model); a real cross-patient and cross-clinic isolation test suite (`backend/app/tests/test_patient_portal.py`) proves Patient A's token cannot read Patient B's data (same clinic or a different clinic) and that a patient token is rejected by every clinic-staff/platform-admin route and vice versa.
- **Frontend**: `frontend/src/app/patient-portal/` — a genuinely separate portal (own layout/branding/token-storage-keys/middleware-protection, distinct from both the clinic portal's `(dashboard)` group and Phase 15's `app/platform/`).

**Explicitly out of scope for this phase**: online appointment booking, online payments, teleconsultation, and an AI assistant — architecture notes only, no working code, per spec.

---

## Patient Self-Service Appointment Booking (Phase 19)

Extends Phase 18's view-only Appointments tab into a full booking flow, reusing the ENTIRE Phase 11 appointment engine (`AppointmentService`, `TimeSlotService`, `AppointmentRepository`, `AppointmentNumberGenerator`) rather than rebuilding any of it — a patient-booked appointment is a plain row in the same `appointments` table, subject to the exact same slot/hours/break/holiday/blocked-date/max-daily-patient rules as a staff-booked one.

- **New patient-facing endpoints** under `/api/v1/patient-portal/appointments/...` (all behind `get_current_patient`, every write scoped to `current.id` from the verified JWT — never a request param): reference-data reads (`branches`, `departments`, `doctors`), availability (`availability` for a date range, `availability/{date}` for one day's time slots), `POST` to create, `PATCH .../{id}/reschedule`, `POST .../{id}/cancel`. Mutations 404 (never leak existence) if the appointment belongs to a different patient.
- **Race-condition safety**: two concurrent booking requests for the same doctor/date/time cannot both succeed. The DB-level guarantee is the partial unique index `uq_appointments_doctor_slot_active` (Postgres, `(clinic_id, doctor_id, appointment_date, start_time)` where not soft-deleted and status isn't terminal) — already present since Phase 11's migration 0012, now ALSO declared in the SQLAlchemy model itself (previously only in raw migration SQL — see `docs/BUGS.md` BUG-012) so `Base.metadata.create_all()`-built test databases actually have it too. The service layer catches the resulting `IntegrityError` and returns a clean `409`, covering both the appointment insert itself and the daily appointment-number counter's first-of-the-day race (BUG-013). A real concurrent-request test (`test_concurrent_patient_bookings_same_slot_only_one_succeeds`) fires two genuinely simultaneous `asyncio.gather`'d requests against independent DB sessions and asserts exactly one succeeds.
- **Reference number**: reuses the existing `AppointmentNumberGenerator` (`APT-YYYYMMDD-000001` format, same daily counter staff bookings use) — no separate numbering scheme.
- **Reception integration**: no new table. A patient-booked appointment is immediately visible via the existing staff `GET /appointments` search (by reference number, patient name/number, doctor, or date — all four already worked, since it's the same `q`/`doctor_id`/`date_from`/`date_to` search over the same table) and the existing staff check-in flow (`POST /appointments/{id}/check-in`) continues to auto-create a linked Queue ticket + Visit exactly as for a staff booking, with zero staff-side code changes — verified live via curl (see `docs/TESTING.md`).
- **`booking_source` column** (new, migration `0018_patient_appointment_booking.py`): `Staff` | `Patient`, indexed, so reception/reporting can distinguish provenance without inferring it from `created_by IS NULL`.
- **Audit**: Created/Rescheduled/Cancelled events logged via the existing `AuditLog` model with `user_id = None` and `metadata.principal = "patient"` — the same pattern Phase 18 established for `patient.password_change`.
- **Frontend**: `frontend/src/app/patient-portal/appointments/book/` — a 7-step wizard (Branch → Department → Doctor → Type → Date → Time → Confirm, this exact order), plus Reschedule/Cancel actions added to the existing Appointments list, plus a "Book Appointment" entry point on both the Appointments page and the Dashboard.
- **Explicitly out of scope for this phase** (per spec): online payment, SMS/email reminders, teleconsultation, an AI assistant.
- **Known gap** (see `docs/BUGS.md` BUG-008): the wizard's given step order has no Service-selection step, so a patient-booked appointment has no `service_id` and cannot be staff-checked-in until reception edits it to add one — confirmed the check-in→Queue/Visit flow itself works correctly once a service is present.

---

## Client Acceptance Revisions (Phase 20)

A bounded, client-approved list of RBAC/workflow changes surfaced during the v1.2.0 UAT, built entirely on existing Phase 8/9/10 infrastructure — no new modules.

- **Receptionist can apply discounts and record payments** (`docs/BUGS.md` BUG-018) — a deliberate widening of the Phase 9 Billing role matrix, not a bug fix per se: `BILLING_DISCOUNT_ROLES`/`BILLING_PAYMENT_RECORD_ROLES` now include Receptionist; voiding a payment stays on its own unchanged, stricter `BILLING_VOID_ROLES` (Cashier/Owner/Administrator only).
- **Receptionist (and Nurse) can enter Subjective/Objective/vitals** on a visit's SOAP note — a narrow, deliberate reversal of Phase 8's "Reception cannot touch SOAP" rule. New endpoints `POST /visits/{id}/consultation/open-for-reception`, `GET`/`PUT /consultations/{id}/soap/subjective-objective`, gated by a new `require_soap_subjective_objective_role` dependency (same named-role-set pattern as every other module). The write endpoint's request schema has no Assessment/Plan fields at all, so that data can never be touched from this path even if someone tries. A new "Enter Vitals" action on the Reception Queue screen opens a small dialog for this. The Doctor's existing SOAP tab automatically shows and can overwrite whatever Reception entered (verified live, no doctor-side changes needed).
- **Doctor can override the consultation fee at completion**: `POST /consultations/{id}/complete`'s optional body now accepts `consultation_fee`, which takes precedence over `Doctor.consultation_fee`/`ClinicService.default_price` on the auto-created invoice. A small input next to "Mark Consultation Complete" on the Doctor Workspace consultation page.
- **Printable Prescription / Laboratory Request / Referral views** — `window.print()` + print CSS, mirroring the existing Billing receipt/print pattern; no new PDF library.
- **RBAC verified end-to-end** with real tokens across Receptionist/Doctor/Cashier/Administrator after the above landed — no regression to any pre-existing role boundary.
- **Audible Call/Recall cue**: a single two-tone Web Audio API chime plays when the Doctor Workspace's Call/Recall action actually succeeds (not on click) - deliberately not a configurable sound system.
- **PWA installability**: a web app manifest + minimal pass-through service worker (no offline/caching support) so the app can be added to a home screen/installed.
- **Receptionist ↔ Doctor internal messaging**: a minimal direct-message list between any two staff members in a clinic (new `internal_messages` table) - pick a colleague, see the conversation (polled every 30s), send a plain-text message. No group chat, no attachments, read-tracking is a single boolean-ish timestamp.

### Client Acceptance Revisions — Round 2

A follow-up bounded list of fixes/additions from the same UAT round, built on the same existing infrastructure — no new modules, no new migration.

- **Discount authority reversed Receptionist → Doctor** (`BILLING_DISCOUNT_ROLES` now `{Owner, Administrator, Doctor}`), and a full discount-*removal* workflow was added end-to-end (`DELETE /invoices/{id}/discounts/{id}`, recalculates totals, audit-logged as `invoice.discount_removed`) — see `docs/BUGS.md` BUG-019.
- **TV Queue Display bug fixed** (`docs/BUGS.md` BUG-020): the public/authenticated TV Display snapshot (`TvDisplayService._build_display_data`) filtered on a naive, OS-local `date.today()` instead of the `datetime.now(UTC).date()` every other "today" computation in the codebase already uses, so active queue tickets could silently fail to appear whenever the server process's local timezone had already rolled to the next calendar day relative to UTC. Fixed to use `datetime.now(UTC).date()` consistently; verified live including a two-tab real-time propagation test (Doctor Workspace "Call" action reflected on the TV Display within seconds via the existing `/ws/queues/{clinic_id}` WebSocket path, no manual refresh).
- **Printer Settings**: a new `/printer-settings` page (per-browser `localStorage` preference, no backend model) for paper size (A4/Letter/Thermal 80mm — applied via a real print-CSS `@page` rule) and a "default printer" free-text preference. The Prescription/Laboratory Request/Referral print dialog (`PrintableDocumentDialog`) was extended, not replaced, with a print preview (an on-screen box approximating the selected paper size, shown before `window.print()` is invoked) and a "preferred printer" reminder line. Explicitly documented: a browser cannot programmatically select which physical printer the OS print dialog uses (a real security restriction) — the "default printer" setting is a reminder only, never an actual selection.
- **Queue Table sorting**: client-side sortable columns (Queue #, Patient, Department, Created) on the Reception Queue list, with asc/desc toggle and direction indicators.
- **Messaging unread-count badge**: the existing `GET /messages/unread-count` endpoint and 30s-polling hook (built in Phase 20 item 14 but never surfaced in the UI) now drive a visible badge on the top-nav message bell, linking to `/messages`.

## Phase 21: Receptionist Shift Management

A new front-desk cash-accountability feature, independent of the Round 2 items above.

- **Shift lifecycle**: a Receptionist starts a shift (`POST /shifts`, opening cash count), only one Open shift per receptionist at a time (enforced by both the service layer and a DB-level partial unique index). `GET /shifts/current` returns their own open shift with a **live-computed** summary — cash/GCash/card/other payment totals, discounts given, refunds, total collections — derived at read time from the existing `Payment`/`Discount`/`Refund` rows within the shift's open time window, never a stored running total (avoids an entire class of drift bugs from voided payments, retries, or late refunds).
- **Close**: `POST /shifts/{id}/close` takes an actual cash count, computes `expected_cash` (opening + cash collections − cash refunds) and `cash_difference` (actual − expected, positive = Over, negative = Short) at that moment, and locks the shift.
- **Reopen**: Owner/Administrator only, distinctly audit-logged from a normal open/close, for correcting a mistakenly-closed shift.
- **Permissions**: a Receptionist can start/view/close only their own shift; Owner/Administrator can view/close/reopen any shift in the clinic.
- **Frontend**: a new "Shift" nav item/page — start-of-shift opening-cash form, a live-polling summary card and close form while a shift is open, and a Shift Summary Report (Opening Cash / Cash Sales / Non-Cash Payments / Discounts / Expected Cash / Actual Cash / Variance) once closed.
- Every open/close/reopen writes a real `audit_logs` row, following the exact `AuditService.log_event` convention used throughout the codebase.

Also this phase: an independent live-verification pass over the previously-built Consultation Fee override (`Doctor`-entered fee at consultation-complete time flowing into the auto-created invoice) confirmed it works correctly end-to-end, including the audit-log attribution to the completing Doctor — no code changes were needed for that item.

---

## Client Acceptance Revisions, Round 3 (items 6-8)

- **Messaging: per-conversation unread + click-to-open.** `GET /messages/unread-by-conversation` breaks the previously-global unread count down per sender. The notification bell is a real dropdown of unread conversations; clicking one opens `/messages?with={userId}` directly (no manual staff-picker step) and marks only that conversation read, leaving other conversations' unread counts untouched.
- **Shift Enforcement.** A Receptionist with no currently-open Shift is blocked (with a clear message and a "Start Shift" shortcut) from queueing a walk-in, checking in an appointment, or recording a payment — all three routed through one shared `enforce_receptionist_open_shift` check. Owner/Administrator/Cashier/Doctor are entirely unaffected.
- **Real Text-to-Speech Queue Calling**, replacing the earlier two-tone chime — Call/Recall speak "Now serving patient number {N}" via the Web Speech API on the Doctor Workspace, Reception Queue, and TV Queue Display, with a `/queue-announcer-settings` page for voice/rate/volume/enable. Overlapping announcements cancel the prior one. Known gap: the TV Display doesn't repeat the announcement for a Recall of an already-serving ticket (BUG-022) — the calling staff member's own device still announces correctly every time.

## Client Acceptance Revisions, Round 3 (items 1, 2, 8, 9, 10, 12)

- **Sortable table headers**, extended from the existing Reception Queue table to Doctor Workspace (Queue #/Patient/Status), Visits (Patient/Date/Doctor/Status), and Appointments' List view (Patient/Doctor/Date-Time/Status) — same client-side sort pattern, filters/pagination unaffected.
- **Messaging latency reduced to 3s.** Unread badge, per-conversation dropdown, and the open conversation view all now poll every 3 seconds (down from 30s) — no WebSocket added, since the existing Queue/TV WebSocket channel is queue-event-specific and extending it was judged a bigger change than a tighter poll interval.
- **Prescription print template** now renders as a real clinic prescription pad: clinic name/logo/address header (from existing Clinic Settings/branding fields), doctor name, patient name + age, an "℞" medication list with dosage/frequency/duration/Sig instructions, and a signature line. A "Half Letter / Prescription pad" (5.5 x 8.5in) paper size was added to Printer Settings.
- **Discount permissions reversed a third time**: Receptionist, Cashier, and Administrator (re)gain the ability to apply/remove Senior Citizen/PWD/Custom invoice discounts; Doctor and Owner were kept (not asked to be removed). Final set: `{Owner, Administrator, Doctor, Cashier, Receptionist}`. Discount audit log entries now also capture the `reason` field (was previously only stored on the discount row, not copied into the audit metadata — see BUG-024).
- **Single "Mark Consultation Complete" action.** The separate "Sign Consultation" button/step was removed from the consultation page; completing a consultation now automatically transitions straight through to the `Signed` status/`signed_at` timestamp in one action, preserving everything that reads `signed_at`/`status === "Signed"` without requiring a second click.
- Investigated the reported "one print job per medication" bug (item 9) — not reproducible in the current codebase; the Prescription print path already renders all items into a single document with one `window.print()` call.

## Client Acceptance Revisions, Round 3 (items 4, 5, 6, 11, 13)

- **Vitals entry error now actionable.** Fixed a Receptionist-facing bug where entering vitals on a queue ticket with no doctor assigned showed a generic "Could not open this visit's consultation." error indistinguishable from any other failure — it now surfaces the real cause ("This visit has no doctor assigned yet...") — see BUG-024.
- **Daily queue-number ceiling enforced.** `QueueSetting.max_daily_queue` (default 200, per clinic/branch/department) previously existed as configuration but was never checked; queue-ticket creation now rejects a request past the configured ceiling with a clear 409 instead of silently continuing past it — see BUG-025.
- **Confirmed pre-existing correctness, no changes needed** for: per-prefix/per-day sequential queue numbering (already correct via `QueueCounter`, independent per prefix, resets daily by construction), Reception's ability to call any Waiting ticket out of order ("Manual Override" — already the default behavior of the per-ticket status-change action), and the TV Display's automatic realtime removal of Completed tickets (already filtered to active statuses only). All three verified live: called a ticket out of order and watched it appear on the public TV display instantly via the existing WebSocket feed, then completed a different ticket's consultation from the Doctor Workspace and watched it disappear from "Now Serving" instantly with no manual refresh.
- **Doctor Session Control.** A Doctor can press "Start Receiving Patients" on the Doctor Workspace, opening a lightweight per-day `DoctorSession` row; the same button area then shows "Next Patient", which completes/moves past whichever visit is currently active for that doctor and automatically calls the earliest Waiting visit assigned to them. Reception's existing "Manual Queue Override" (call any Waiting ticket directly) is unaffected either way — sessions are additive UI/orchestration state, not an access gate. Live-verified as `maria.santos@connectph.dev`: started a session, confirmed the "Session active — receiving patients since ..." banner, clicked "Next Patient", confirmed the previously-Called-but-not-started ticket moved to NoShow and the dashboard's Waiting/Called counts updated correctly (no doctor-assigned Waiting ticket existed at test time, so the "calls the next waiting patient" half of the flow completed correctly by returning nothing rather than erroring — a genuine positive-path call-through was not exercised this pass).

## Vitals-before-Queue (Consultation/Follow-up) completion, Save-and-Close, and queue-numbering resync

- **Vitals-before-Queue is now actually functional end-to-end.** A prior interrupted session had built the whole feature (draft-visit creation via `POST /visits/pre-queue`, the `DraftVitals` visit status, backend enforcement rejecting a Consultation/Follow-up queue ticket with missing vitals, the frontend's "Enter Vitals" step) but it was silently inert due to a `service_code` allowlist mismatch — see BUG-027 in `docs/BUGS.md`. Fixed; live-verified: selecting Consultation or Follow-up now shows "Enter Vitals", requires a doctor, opens a vitals form (BP/Temp/Pulse/RR/SpO2/Height/Weight required, BMI auto-computed, Pain Score/Notes/Head Circumference optional), and blocks queue-ticket creation — both in the UI and via a direct API bypass test — until vitals are saved. The Doctor's consultation view reads the same `soap_notes` row with no extra plumbing, confirmed live across a two-tab Receptionist/Doctor test.
- **"Save and Close"** replaces the standalone "Save" button on both the pre-queue vitals step (`PreQueueVitalsStep.tsx`) and the existing after-queueing vitals-edit dialog (`ReceptionVitalsDialog.tsx`). Validates required vitals, saves, shows a "Vitals saved successfully." toast (reusing the existing `useToast()`/`ToastProvider`), and auto-closes; a validation failure highlights and focuses the first invalid field without closing. Enter submits (except inside the Notes/Chief complaint textarea), Escape closes without saving. Closing the pre-queue step automatically flips `NewQueueDialog`'s button to "Create Queue Ticket" with no manual refresh.
- **Queue-number generation hardened against drift.** `QueueNumberGenerator.next_number()` now re-derives the true `MAX(queue_number)` issued for the exact `(clinic, branch, prefix, date)` bucket inside the same locked transaction as the counter read, and bumps the counter forward if it's ever behind — self-healing against any future bypass of the counter table, while keeping the existing atomic locking as the primary mechanism (no live `MAX()` query on the hot path). No drift was found in the current dev database when investigated; this is a defensive fix per the request, verified live with back-to-back concurrent ticket creation producing strictly increasing, non-reused numbers.

---

## Planned (Business Modules)

None of the following are implemented yet. They represent the clinical/business domain the platform exists to serve.

- **Patients — CSV/Excel/legacy import and CSV/Excel/PDF export** — the Phase 14 Migration Wizard now covers CSV/Excel *import* for Patients/Doctors specifically (see above); general-purpose Patient CSV/Excel/PDF *export* is still not built.
- **Patients — real QR image rendering** — payload/token generation is implemented; rendering an actual scannable image (or wiring a client-side QR renderer) is deferred.
- **Doctor Console** — a dedicated doctor-facing "call next" console consuming the same `/ws/queues/{clinic_id}` channel the Phase 13 TV Display now uses; the TV Display consumer itself is built (see above).
- **Pharmacy** — drug inventory, prescriptions, dispensing workflow, stock alerts.
- **Notifications** — SMS/email reminders, in-app notifications.
- **Multi-branch operations** — branch-level permissions, inventory transfer, branch-scoped reporting.

Business modules will be scoped and prioritized in future roadmap phases (see [`ROADMAP.md`](ROADMAP.md)).
