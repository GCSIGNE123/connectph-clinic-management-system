# Administrator Guide — Clinic Setup, Users, and Configuration

For the Owner/Administrator role setting up a new clinic tenant (pilot or
otherwise) on CONNECT.PH. Every step below was actually run against a
live instance while building the Phase 17 pilot tenant (see
`docs/PILOT_READINESS.md`).

## 1. Tenant registration

`POST /api/v1/auth/register` (or the app's Sign Up page) creates a new
clinic tenant plus its first Owner user in one call: clinic name, clinic
slug (URL-safe, unique), your name/email/username/password. You get a
JWT immediately — no separate "verify then configure" gate blocks the
setup steps below (email verification exists but does not block initial
configuration in this build).

## 2. Master data setup order

Do these roughly in this order — later steps often reference earlier
ones:

1. **Branches** (`Branches` page) — at least one branch, with code,
   address, contact number.
2. **Departments** (`Departments` page) — use **Seed Defaults** for a
   standard starter set (General Medicine, Pediatrics, etc.) or add your
   own.
3. **Services** (`Services` page) — likewise has **Seed Defaults**
   (Consultation, common service codes/prices/durations).
4. **Consultation Rooms** — per branch.
5. **Doctors** — name, specialization, branch, department, consultation
   fee. Each gets an auto-generated `doctor_code` (`DOC-0001`, ...).
6. **Doctor Schedules** — per doctor, per day-of-week (`0`=Monday..
   `6`=Sunday), start/end time, slot duration. This is what the
   Appointments module's available-slots engine reads from — a doctor
   with no schedule has no bookable slots.
7. **Operating Hours** — per branch, per day-of-week.
8. **Queue Settings** — prefix, daily reset time, walk-ins/priority-lane
   toggles. **Priority Types** has its own **Seed Defaults** (Senior
   Citizen, PWD, Pregnant, Emergency, VIP).
9. **Laboratory Templates** (Administrator-only) — test name, pricing,
   reference ranges, if you want auto-priced/auto-matched lab orders
   rather than ad-hoc ones.

## 3. Staff accounts

**Users** page → create one account per staff member, assigning one of
the seeded roles (Owner, Administrator, Receptionist, Doctor, Nurse,
Cashier, Laboratory, Pharmacy, Viewer). **Important**: creating a Doctor
role user does **not** automatically link them to a `Doctors` master-data
record — a Doctor user only gets edit access to their own consultations
once their user account's `doctor_id` is linked to the matching Doctors
row. There is no self-service UI for this link in the current build; it
must be set directly in the database (`UPDATE users SET doctor_id = ...
WHERE id = ...`) until a dedicated "link user to doctor record" admin
action is added — flagged as a real gap, see `docs/BUGS.md` if you want
to track it as a feature request (it wasn't in scope to build this
phase, since Phase 17 fixes only bugs found in existing code).

## 4. Role permissions, at a glance

| Role | Can do |
|---|---|
| Owner | Everything, including all view-only clinical gates |
| Administrator | Everything except editing another doctor's SOAP note |
| Receptionist | Patients/Appointments manage; Billing/Laboratory read-only; no clinical edit |
| Doctor | Own consultations/orders/prescriptions edit; others view-only |
| Nurse | Clinical view access, no edit |
| Cashier | Billing manage; Patients view |
| Laboratory | Laboratory orders manage; no Prescriptions/Procedures/Referrals access |
| Pharmacy | Pharmacy inventory (not yet built as a module) |
| Viewer | Read-only across Patients/Appointments/Billing/Reports |

## 5. Legacy data migration

See `docs/MIGRATION.md` for the full operator guide. Short version: only
run the migration wizard **after** branches/departments/doctors/services
master data already exists in the new tenant, since migrated Patients
and Doctors reference (or are matched against) that master data.

## 6. Backups

See `docs/BACKUP.md`. `POST /api/v1/platform-admin/backups`
(PlatformAdministrator-only, i.e. a platform-level role above per-clinic
Owner) triggers a real `pg_dump`. There is no self-service per-clinic
backup trigger for an Owner/Administrator in this build — backups are a
platform-operator responsibility, not a per-tenant one.

## 7. Monitoring what's configured

`GET /api/v1/queue-settings`, `/departments`, `/services`, `/branches`,
`/doctors` all return what's currently configured for your clinic — use
these (or their respective admin pages) to audit a tenant's setup before
declaring it pilot-ready. See `docs/PILOT_READINESS.md` for the specific
checklist used to verify the Phase 17 pilot tenant.
