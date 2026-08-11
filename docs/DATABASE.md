# Database

This document describes the foundation database schema, relationships, indexing strategy, the legacy-migration-readiness pattern, and the Alembic migration workflow.

- **Engine:** PostgreSQL (hosted via Supabase)
- **ORM:** SQLAlchemy 2.0 (async, `asyncpg` driver)
- **Migrations:** Alembic
- **Primary keys:** `UUID`, generated via `gen_random_uuid()` (Postgres `pgcrypto`/`pgcrypto`-free `gen_random_uuid()` in Postgres 13+) or client-side `uuid4()` in the ORM default

## Mixins

Common columns are provided via shared SQLAlchemy mixins (`app/models/mixins.py`) rather than repeated per model:

| Mixin | Adds |
|---|---|
| `TimestampMixin` | `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()` (updated via ORM `onupdate`/DB trigger) |
| `SoftDeleteMixin` | `is_deleted BOOLEAN NOT NULL DEFAULT false`, `deleted_at TIMESTAMPTZ NULL` |
| `TenantMixin` | `clinic_id UUID NOT NULL REFERENCES clinics(id)` + index |
| `LegacyMixin` | `legacy_id VARCHAR(64) NULL`, `legacy_meta JSONB NULL` |

Applied today: `TenantMixin` on all business tables listed below except `clinics` itself; `LegacyMixin` on `clinics` and `users` (ready to extend to future business tables — patients, appointments, etc.).

---

## Entity-Relationship Overview

```
 clinics ──1───∞ branches
    │                │
    │                │
    1                │
    │                │
    ∞                ∞
 users ─────────────┘
    │        │
    │        ∞
    │     role_permissions ── permissions
    │        │
    ∞        1
 roles ──────┘

 clinics ──1───∞ subscriptions
 clinics ──1───∞ system_settings
 clinics ──1───∞ audit_logs  (nullable clinic_id for platform-level events)
 users   ──1───∞ audit_logs
 users   ──1───∞ password_reset_tokens       (Phase 2)
 users   ──1───∞ email_verification_tokens   (Phase 2)
 users   ──1───∞ refresh_tokens / sessions   (Phase 2)
```

---

## Tables

### 1. `clinics`

The tenant root. One row per clinic (customer) on the platform.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` |
| `name` | VARCHAR(255) NOT NULL | Clinic display name |
| `slug` | VARCHAR(100) UNIQUE NOT NULL | URL-safe identifier |
| `email` | VARCHAR(255) NOT NULL | Primary contact email |
| `phone` | VARCHAR(30) NULL | |
| `address` | TEXT NULL | |
| `timezone` | VARCHAR(50) NOT NULL DEFAULT 'Asia/Manila' | |
| `is_active` | BOOLEAN NOT NULL DEFAULT true | Suspends clinic access when false |
| `legacy_id` | VARCHAR(64) NULL | Legacy desktop-app clinic identifier, if migrated |
| `legacy_meta` | JSONB NULL | Raw legacy record snapshot for audit/reference |
| `created_at`, `updated_at` | TIMESTAMPTZ | via `TimestampMixin` |
| `is_deleted`, `deleted_at` | | via `SoftDeleteMixin` |

**Indexes:** unique on `slug`; btree on `legacy_id` (partial, `WHERE legacy_id IS NOT NULL`).

### 2. `branches`

Physical locations belonging to a clinic.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `clinic_id` | UUID FK → `clinics.id` NOT NULL | via `TenantMixin` |
| `name` | VARCHAR(255) NOT NULL | |
| `address` | TEXT NULL | |
| `phone` | VARCHAR(30) NULL | |
| `is_main` | BOOLEAN NOT NULL DEFAULT false | Marks the primary branch |
| `is_active` | BOOLEAN NOT NULL DEFAULT true | |
| `created_at`, `updated_at`, `is_deleted`, `deleted_at` | | |

**Indexes:** btree on `clinic_id`; unique on `(clinic_id, name)`.

### 3. `users`

Staff accounts (Owner, Administrator, Receptionist, Doctor, Nurse, Cashier, Laboratory, Pharmacy, Viewer). Patients are **not** users — patient records are a future business table, not part of the auth system.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `clinic_id` | UUID FK → `clinics.id` NOT NULL | via `TenantMixin` |
| `branch_id` | UUID FK → `branches.id` NULL | primary branch assignment |
| `email` | VARCHAR(255) NOT NULL | unique within clinic |
| `hashed_password` | VARCHAR(255) NOT NULL | argon2/bcrypt hash, never plaintext |
| `first_name` | VARCHAR(100) NOT NULL | |
| `last_name` | VARCHAR(100) NOT NULL | |
| `phone` | VARCHAR(30) NULL | |
| `is_active` | BOOLEAN NOT NULL DEFAULT true | |
| `is_email_verified` | BOOLEAN NOT NULL DEFAULT false | |
| `last_login_at` | TIMESTAMPTZ NULL | |
| `legacy_id` | VARCHAR(64) NULL | Legacy desktop-app user identifier, if migrated |
| `legacy_meta` | JSONB NULL | |
| `created_at`, `updated_at`, `is_deleted`, `deleted_at` | | |

**Indexes:** unique on `(clinic_id, email)`; btree on `clinic_id`; partial btree on `legacy_id`.

#### 3a. `users` — Phase 2 additions (Authentication & User Management)

Added by the Phase 2 migration (`backend/alembic/versions/`, see [`FEATURES.md`](FEATURES.md)) to support full authentication (login lockout, verified email, password reset/rotation) and richer staff profiles. These columns extend the table above; existing columns (`email`, `hashed_password`, `is_active`, `is_email_verified`, etc.) are unchanged and still authoritative where they overlap conceptually with a new column (see notes).

| Column | Type | Notes |
|---|---|---|
| `middle_name` | VARCHAR(100) NULL | |
| `mobile_number` | VARCHAR(30) NULL | distinct from legacy `phone`; used for SMS-based flows (remember-me device hints, future MFA) |
| `username` | VARCHAR(100) NULL | unique within clinic; optional alternate login identifier alongside `email` |
| `status` | VARCHAR(20) NOT NULL DEFAULT 'active' | `active`, `disabled`, `pending`; superset of the boolean `is_active` — `is_active` is kept in sync (`is_active = (status == 'active')`) for backward compatibility with existing queries, `status` is the source of truth going forward |
| `profile_photo` | VARCHAR(500) NULL | Supabase Storage object path/URL |
| `failed_login_attempts` | INTEGER NOT NULL DEFAULT 0 | incremented on each failed login, reset to `0` on success |
| `locked_until` | TIMESTAMPTZ NULL | set when `failed_login_attempts` crosses the lockout threshold; login is rejected with `403` while `now() < locked_until` (see [`SECURITY.md`](SECURITY.md#3-account-lockout-policy)) |
| `email_verified_at` | TIMESTAMPTZ NULL | timestamp of successful `verify-email`; complements the existing boolean `is_email_verified` (`is_email_verified = (email_verified_at IS NOT NULL)`) |

**Indexes:** unique on `(clinic_id, username)` where `username IS NOT NULL`; btree on `locked_until` (partial, `WHERE locked_until IS NOT NULL`) to support a periodic lockout-expiry sweep if one is added later.

### 4. `roles`

Platform-global role catalog (not tenant-scoped — shared vocabulary across all clinics).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `name` | VARCHAR(50) UNIQUE NOT NULL | Owner, Administrator, Receptionist, Doctor, Nurse, Cashier, Laboratory, Pharmacy, Viewer |
| `description` | TEXT NULL | |
| `is_system` | BOOLEAN NOT NULL DEFAULT true | System-seeded roles cannot be deleted |
| `created_at`, `updated_at` | | |

A `user_roles` join table (`user_id`, `role_id`, `clinic_id`) associates a user with one or more roles *within a clinic* — a user's role is clinic-scoped even though the role catalog itself is global (e.g., a user could theoretically be Doctor at Clinic A and Receptionist at Clinic B, though typical usage is one clinic per user).

### 5. `permissions`

Platform-global permission catalog (fine-grained action identifiers, e.g. `patients:read`, `billing:write`).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `code` | VARCHAR(100) UNIQUE NOT NULL | e.g. `users:manage`, `appointments:read` |
| `description` | TEXT NULL | |
| `created_at`, `updated_at` | | |

### 6. `role_permissions`

Join table mapping roles to permissions.

| Column | Type | Notes |
|---|---|---|
| `role_id` | UUID FK → `roles.id` | part of composite PK |
| `permission_id` | UUID FK → `permissions.id` | part of composite PK |
| `created_at` | | |

**Indexes:** composite PK `(role_id, permission_id)`; btree on `permission_id` for reverse lookup.

### 7. `audit_logs`

Append-only record of sensitive/auditable events.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `clinic_id` | UUID FK → `clinics.id` NULL | nullable for platform-level (cross-tenant) events |
| `user_id` | UUID FK → `users.id` NULL | nullable for unauthenticated events (e.g. failed login by unknown email) |
| `action` | VARCHAR(100) NOT NULL | e.g. `auth.login.success`, `auth.login.failure`, `user.created` |
| `entity_type` | VARCHAR(100) NULL | e.g. `user`, `clinic` |
| `entity_id` | UUID NULL | |
| `ip_address` | VARCHAR(45) NULL | |
| `user_agent` | TEXT NULL | |
| `metadata` | JSONB NULL | free-form structured detail |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | no `updated_at` — logs are immutable |

**Indexes:** btree on `(clinic_id, created_at)`; btree on `(user_id, created_at)`; btree on `action`.

### 8. `system_settings`

Per-clinic configurable key/value settings (feature flags, business preferences).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `clinic_id` | UUID FK → `clinics.id` NOT NULL | via `TenantMixin` |
| `key` | VARCHAR(100) NOT NULL | e.g. `appointment.default_duration_minutes` |
| `value` | JSONB NOT NULL | typed value stored as JSON |
| `created_at`, `updated_at` | | |

**Indexes:** unique on `(clinic_id, key)`.

### 9. `subscriptions`

Billing relationship between a clinic and the SaaS platform itself (i.e., what the clinic pays CONNECT.PH — distinct from the future in-app `billing` module, which is a clinic billing its own patients).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `clinic_id` | UUID FK → `clinics.id` NOT NULL UNIQUE | one active subscription record per clinic |
| `plan` | VARCHAR(50) NOT NULL | e.g. `trial`, `starter`, `pro`, `enterprise` |
| `status` | VARCHAR(30) NOT NULL | `active`, `past_due`, `canceled`, `trialing` |
| `current_period_start` | TIMESTAMPTZ NULL | |
| `current_period_end` | TIMESTAMPTZ NULL | |
| `seats` | INTEGER NULL | max user seats, if plan-limited |
| `created_at`, `updated_at` | | |

**Indexes:** unique on `clinic_id`; btree on `status`.

### 10. `password_reset_tokens` (Phase 2)

One row per issued "forgot password" request. Tokens are stored **hashed**, never in plaintext, so a database read cannot be used to reset a password directly.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `clinic_id` | UUID FK → `clinics.id` NOT NULL | via `TenantMixin` |
| `user_id` | UUID FK → `users.id` NOT NULL | |
| `token_hash` | VARCHAR(255) NOT NULL | SHA-256 (or equivalent) hash of the token emailed to the user; the raw token is never persisted |
| `expires_at` | TIMESTAMPTZ NOT NULL | short-lived, default 1 hour from issue (see [`SECURITY.md`](SECURITY.md)) |
| `used_at` | TIMESTAMPTZ NULL | set when the token is successfully consumed; a used or expired token is rejected on reuse |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | no `updated_at` — tokens are write-once |

**Indexes:** unique on `token_hash`; btree on `(user_id, created_at)`; partial btree on `expires_at` (`WHERE used_at IS NULL`) to support cleanup of expired unused tokens.

### 11. `email_verification_tokens` (Phase 2)

Same shape and lifecycle rationale as `password_reset_tokens`, issued on registration and via `resend-verification`.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `clinic_id` | UUID FK → `clinics.id` NOT NULL | via `TenantMixin` |
| `user_id` | UUID FK → `users.id` NOT NULL | |
| `token_hash` | VARCHAR(255) NOT NULL | hashed at rest, same as password reset tokens |
| `expires_at` | TIMESTAMPTZ NOT NULL | default 24 hours from issue |
| `used_at` | TIMESTAMPTZ NULL | set when `verify-email` succeeds; sets `users.email_verified_at` in the same transaction |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |

**Indexes:** unique on `token_hash`; btree on `(user_id, created_at)`.

### 12. `refresh_tokens` (a.k.a. `sessions`) (Phase 2)

Server-side record of every issued refresh token, enabling rotation, per-session revocation (logout), and "reuse of a revoked token" compromise detection described in [`SECURITY.md`](SECURITY.md#1-jwt-strategy).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | doubles as the token's `jti` claim |
| `clinic_id` | UUID FK → `clinics.id` NOT NULL | via `TenantMixin` |
| `user_id` | UUID FK → `users.id` NOT NULL | |
| `token_hash` | VARCHAR(255) NOT NULL | hash of the opaque refresh token; the raw value only ever exists client-side (httpOnly cookie) and at issuance time |
| `parent_id` | UUID FK → `refresh_tokens.id` NULL | previous token in the rotation chain, if any — lets a reuse-of-revoked-token check walk the chain to revoke all descendants |
| `remember_me` | BOOLEAN NOT NULL DEFAULT false | drives the cookie's `Max-Age`/expiry (short session-only vs. extended, see [`SECURITY.md`](SECURITY.md)) |
| `user_agent` | TEXT NULL | captured at issuance for the user-facing "active sessions" list |
| `ip_address` | VARCHAR(45) NULL | |
| `expires_at` | TIMESTAMPTZ NOT NULL | |
| `revoked_at` | TIMESTAMPTZ NULL | set on logout, rotation, or forced revocation (e.g. password change, detected reuse) |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |

**Indexes:** unique on `token_hash`; btree on `(user_id, revoked_at)` to quickly list a user's active sessions; btree on `parent_id`.

---

## Legacy Migration Readiness: `legacy_id` + `legacy_meta`

The platform's eventual purpose includes replacing a legacy Windows desktop clinic application. Rather than bolting on migration support later, the **`LegacyMixin` pattern is applied from day one** to the tables most central to identity (`clinics`, `users`), and is designed to be trivially reused on every future business table (patients, doctors, appointments, queue history, billing).

### The pattern

```python
class LegacyMixin:
    legacy_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    legacy_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

- **`legacy_id`** — the primary key (or best natural identifier) of the corresponding record in the legacy desktop app's database (commonly an MS Access/SQL Server/Firebird integer or string ID, depending on the legacy system). Stored as `VARCHAR` since legacy ID formats vary by table and by clinic's legacy install version.
- **`legacy_meta`** — a JSONB snapshot of the *original legacy row* (or the fields most likely to be needed for reconciliation/audit) captured verbatim at migration time. This preserves data that may not map cleanly to the new schema (custom fields, free-text notes, deprecated flags) without forcing a lossy one-shot transformation.

### Why this approach

1. **Idempotent, resumable migration** — an ETL job can `UPSERT ... ON CONFLICT (legacy_id) WHERE legacy_id IS NOT NULL` to safely re-run imports without creating duplicates.
2. **Traceability** — every migrated record can always be traced back to its legacy source (support/debugging: "why does this patient have this value?" → check `legacy_meta`).
3. **Decoupled timing** — migration doesn't need to happen atomically with schema design; the mixin can be added to a new business table (e.g., `patients`) in the same migration that creates the table, before any data import tooling exists.
4. **Partial migration support** — clinics can be onboarded fresh (no `legacy_id`, `legacy_meta` stays `NULL`) or migrated from the legacy system (both populated), using the same schema and application code path — no separate "migrated tenant" code branch.
5. **Reconciliation queries** — `WHERE legacy_id IS NOT NULL` isolates migrated rows for spot-checking against the source system during a migration project; partial indexes on `legacy_id` keep this cheap even at scale (most rows, long-term, won't have one).

### Migration workflow (planned, Phase 3)

1. Export legacy data per clinic (per-table CSV/SQL dump from the desktop app's local database).
2. Run a clinic-specific ETL script (`scripts/migrate-legacy/<table>.py`, planned) that maps legacy columns → new schema columns, sets `legacy_id` to the legacy PK, and stores the full original row in `legacy_meta`.
3. Upsert into the new schema scoped to the target `clinic_id`.
4. Run reconciliation reports comparing row counts / key aggregates between legacy source and migrated data.
5. Cut the clinic over; keep `legacy_meta` indefinitely for audit/support purposes (not deleted post-migration).

---

## Alembic Workflow

Migrations live in `backend/alembic/versions/`.

### Common commands

```bash
cd backend

# Generate a new migration from model changes (autogenerate)
alembic revision --autogenerate -m "add patients table"

# Review the generated migration file before applying — autogenerate is a
# starting point, not a guarantee (it misses some constraint/index changes).

# Apply all pending migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1

# Show current DB revision
alembic current

# Show migration history
alembic history --verbose
```

### Conventions

- One logical schema change per migration (don't bundle unrelated table changes).
- Every migration that adds a business table must also add `clinic_id` (via `TenantMixin`) unless there is a documented reason it's platform-global (as with `roles`/`permissions`).
- Data migrations (backfills) are written as separate migration files from schema migrations, using `op.execute()` / SQLAlchemy Core, not ORM models (ORM models change over time; migrations must remain valid at the revision they were written for).
- Downgrade paths are implemented, not left as `pass`, wherever feasible — required for safe rollback in staging.
- The seed data for `roles`, `permissions`, and `role_permissions` is applied via a dedicated data migration (or a `python -m app.db.seed` script run post-migration), not hardcoded into application startup.

### 13. `patients` (Phase 3)

The master patient database, tenant- and branch-scoped, that every future clinical module (queue, appointments, billing, laboratory, pharmacy, medical records, reports) references by `id`. Uses the same `UUIDPrimaryKeyMixin` + `TimestampMixin` + `SoftDeleteMixin` (`is_deleted`/`deleted_at`) + `TenantMixin` + `LegacyMixin` combination as `users`.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `clinic_id` | UUID FK → `clinics.id` NOT NULL | via `TenantMixin` |
| `branch_id` | UUID FK → `branches.id` NULL | patient's registering/home branch |
| `legacy_id`, `legacy_meta` | | via `LegacyMixin` (generic provenance) |
| `legacy_patient_id` | VARCHAR(64) NULL | the patient's own identifier in the legacy desktop app, kept separate from `legacy_id` since it is directly searchable (`q=` matches against it) and may have a different shape per legacy install |
| `patient_number` | VARCHAR(30) NOT NULL | clinic-scoped, auto-generated (see below); unique per clinic |
| `first_name`, `middle_name`, `last_name`, `suffix` | VARCHAR | `middle_name`/`suffix` nullable |
| `birth_date` | DATE NOT NULL | validated not-in-the-future at the schema layer |
| `gender` | ENUM(`Male`,`Female`,`Other`) | |
| `civil_status` | ENUM(`Single`,`Married`,`Widowed`,`Separated`,`Divorced`) | |
| `nationality` | VARCHAR(100) NOT NULL DEFAULT `'Filipino'` | |
| `address_line`, `barangay`, `city`, `province`, `zip_code` | VARCHAR NULL | |
| `mobile_number` | VARCHAR(20) NOT NULL | |
| `telephone_number`, `email` | NULL | |
| `occupation`, `employer` | VARCHAR(150) NULL | |
| `blood_type` | ENUM(`A+`,`A-`,`B+`,`B-`,`AB+`,`AB-`,`O+`,`O-`,`Unknown`) NULL | |
| `allergies`, `medical_notes`, `remarks` | TEXT NULL | |
| `photo_url` | VARCHAR(500) NULL | Supabase Storage object URL (presigned-upload stub today, see [`FEATURES.md`](FEATURES.md)) |
| `qr_code` | VARCHAR(255) NULL UNIQUE | signed opaque check-in payload (see below) |
| `status` | ENUM(`Active`,`Archived`) NOT NULL DEFAULT `'Active'` | business status; **separate from** `is_deleted` |
| `date_registered` | DATE NOT NULL | defaults to the creation date |
| `last_visit` | TIMESTAMPTZ NULL | column reserved for future visit/appointment modules to update; not written by anything yet |
| `created_by`, `updated_by` | UUID FK → `users.id` NULL | actor attribution, `ON DELETE SET NULL` |

**Indexes:** `clinic_id`; `branch_id`; unique `(clinic_id, patient_number)`; `(clinic_id, last_name, first_name)`; `(clinic_id, mobile_number)`; `(clinic_id, birth_date)`; `legacy_id`; `legacy_patient_id`; `status`; `birth_date`. This set is chosen to keep the common query shapes (exact-clinic table scan, name search, mobile lookup, age-range filter, sort-by-recency) index-covered at 100k+ rows per clinic without over-indexing every column.

#### Patient number generation

Patient numbers (`PAT-000001`, `PAT-000002`, ...) are **not** a raw Postgres `SEQUENCE`. Instead, `services/patient_number_generator.py::PatientNumberGenerator` keeps a per-clinic counter as a row in `system_settings` (`key = "patient_number_counter"`, `value = {"prefix": "PAT-", "padding": 6, "next": <int>}`). Rationale:

- **Clinic-scoped and configurable** — a future admin UI can let a clinic customize its own prefix/padding (e.g. per-branch prefixes) by editing that JSON row, with no DDL/migration required.
- **Concurrency-safe** — the counter row is read with `SELECT ... FOR UPDATE` inside the same transaction as the patient insert, so concurrent create requests for the same clinic serialize on that row instead of racing; the counter increment and the patient row commit or roll back together.
- **Trade-off** — this is intentionally simpler than a dedicated multi-column counter table; if per-branch or per-year-reset numbering schemes are needed later, extend the JSON shape (e.g. `{"scope": "branch", "counters": {...}}`) rather than switching to raw sequences.

#### QR code approach

`qr_code` stores an opaque, signed payload string: `f"{clinic_id}:{patient_id}:{hmac_sha256(clinic_id:patient_id)[:16]}"`, keyed with the app's `JWT_SECRET_KEY`. This lets a future queue/appointment check-in scanner verify a scanned code was issued by this system (recompute and compare the signature) without embedding any PII or requiring a DB round trip to validate authenticity.

**Rendering an actual QR image is deferred in this phase** — no QR-image dependency has been vetted/added to the backend yet, and adding one wasn't in scope. `GET /patients/{id}/qr` returns the payload string only; a future iteration can either render a PNG server-side (e.g. via the `qrcode` package once approved) or render the code client-side from the payload string using a small frontend QR library.

#### Legacy migration readiness

`legacy_patient_id` (alongside the generic `legacy_id`/`legacy_meta` from `LegacyMixin`) is populated by a future importer (see `services/patient_import_export.py`) so records migrated from the legacy desktop app can be reconciled/deduplicated against their original source records, following the same `UPSERT ... ON CONFLICT` pattern described above for other tables. No importer is implemented yet — only the column and the `PatientImporter`/`PatientExporter` ABC interfaces exist today.

---

## Phase 4: Clinic Configuration & Master Data

Migration `0004_clinic_configuration`. Extends `clinics`/`branches` and adds 9 new tables. Every new table uses `UUIDPrimaryKeyMixin` + `TimestampMixin` + `SoftDeleteMixin` + `TenantMixin` (i.e. `id`, `created_at`, `updated_at`, `is_deleted`, `deleted_at`, `clinic_id`) unless noted.

### `clinics` — Phase 4 additions

Settings + branding fields added directly to the existing tenant-root row (one row per clinic already existed; no new "settings" table):

| Column | Type | Notes |
|---|---|---|
| `short_name`, `province`, `city`, `barangay`, `zip_code`, `telephone`, `mobile`, `website`, `tin`, `license_number` | VARCHAR NULL | Settings/legal fields |
| `timezone`, `language`, `currency`, `date_format`, `time_format` | VARCHAR NOT NULL, defaulted (`Asia/Manila`/`en`/`PHP`/`MM/DD/YYYY`/`12h`) | Locale preferences |
| `status` | VARCHAR(20) NOT NULL DEFAULT 'Active' | |
| `logo_url`, `favicon_url`, `login_background_url` | VARCHAR(500) NULL | Branding assets (presigned-upload stub) |
| `primary_color`, `secondary_color` | VARCHAR(20) NULL | Hex colors |
| `theme` | VARCHAR(20) NOT NULL DEFAULT 'system' | `light`/`dark`/`system` |

### `branches` — Phase 4 additions

| Column | Type | Notes |
|---|---|---|
| `code` | VARCHAR(30) NULL | Unique per clinic (`uq_branch_clinic_code`) |
| `contact_number`, `email` | VARCHAR NULL | |
| `manager_id` | UUID FK → `users.id` ON DELETE SET NULL | Nullable |
| `status` | VARCHAR(20) NOT NULL DEFAULT 'Active' | |

### `departments`

| Column | Type | Notes |
|---|---|---|
| `department_code` | VARCHAR(30) NOT NULL | Unique per clinic |
| `name` | VARCHAR(150) NOT NULL | |
| `description` | TEXT NULL | |
| `color` | VARCHAR(20) NULL | Hex color |
| `status` | VARCHAR(20) NOT NULL DEFAULT 'Active' | |

**Indexes:** btree on `clinic_id`; unique on `(clinic_id, department_code)`. Optional default-set seeding (`POST /departments/seed-defaults`, 409s if the clinic already has departments) — see `models/department.py::DEFAULT_DEPARTMENTS`.

### `doctors`

| Column | Type | Notes |
|---|---|---|
| `doctor_code` | VARCHAR(30) NOT NULL | Unique per clinic, auto-generated (`DOC-0001`, ...) |
| `first_name`, `middle_name`, `last_name`, `suffix` | VARCHAR | |
| `prc_license`, `ptr_number`, `specialization` | VARCHAR NULL | |
| `department_id` | UUID FK → `departments.id` ON DELETE SET NULL | Nullable |
| `branch_id` | UUID FK → `branches.id` ON DELETE SET NULL | Nullable |
| `photo_url`, `signature_url` | VARCHAR(500) NULL | |
| `contact_number`, `email` | VARCHAR NULL | |
| `consultation_fee` | NUMERIC(12,2) NULL | |
| `status` | ENUM `doctor_status` (`Active`/`Inactive`/`On Leave`) NOT NULL DEFAULT `Active` | |

**Indexes:** btree on `clinic_id`, `department_id`, `branch_id`, `status`; unique on `(clinic_id, doctor_code)`.

#### Doctor code generation

`services/doctor_code_generator.py::DoctorCodeGenerator` mirrors `PatientNumberGenerator` exactly (per-clinic counter row in `system_settings`, key `doctor_code_counter`, `SELECT ... FOR UPDATE` for concurrency safety) rather than refactoring `PatientNumberGenerator` into a shared base, to avoid touching the already-shipped Phase 3 patient code path. Format: `DOC-0001` (prefix `DOC-`, 4-digit padding).

### `doctor_schedules`

Weekly availability windows only — **no appointment-slot generation or booking logic**.

| Column | Type | Notes |
|---|---|---|
| `doctor_id` | UUID FK → `doctors.id` ON DELETE CASCADE NOT NULL | |
| `branch_id` | UUID FK → `branches.id` ON DELETE SET NULL | Nullable |
| `day_of_week` | SMALLINT NOT NULL | `0`=Monday .. `6`=Sunday |
| `start_time`, `end_time` | TIME NOT NULL | |
| `is_active` | BOOLEAN NOT NULL DEFAULT true | |

**Indexes:** btree on `clinic_id`, `doctor_id`, `branch_id`.

### `consultation_rooms`

| Column | Type | Notes |
|---|---|---|
| `room_name` | VARCHAR(150) NOT NULL | |
| `room_number` | VARCHAR(30) NULL | |
| `department_id` | UUID FK → `departments.id` ON DELETE SET NULL | Nullable |
| `branch_id` | UUID FK → `branches.id` ON DELETE SET NULL | Nullable |
| `status` | VARCHAR(20) NOT NULL DEFAULT 'Active' | |

**Indexes:** btree on `clinic_id`, `department_id`, `branch_id`.

### `services`

The billable/consultable service catalog. Modeled as `ClinicService` (table `services`) rather than `Service` to avoid a Python import clash with the `app/services/` business-logic package.

| Column | Type | Notes |
|---|---|---|
| `service_code` | VARCHAR(30) NOT NULL | Unique per clinic |
| `service_name` | VARCHAR(150) NOT NULL | |
| `description` | TEXT NULL | |
| `default_price` | NUMERIC(12,2) NOT NULL DEFAULT 0 | |
| `duration_minutes` | SMALLINT NULL | |
| `department_id` | UUID FK → `departments.id` ON DELETE SET NULL | Nullable |
| `status` | VARCHAR(20) NOT NULL DEFAULT 'Active' | |

**Indexes:** btree on `clinic_id`, `department_id`; unique on `(clinic_id, service_code)`. Optional default-set seeding (`POST /services/seed-defaults`) — see `models/clinic_service.py::DEFAULT_SERVICES`.

### `queue_settings` + `priority_types`

Pure configuration — **no ticket-issuing/calling/serving logic**.

`queue_settings`:

| Column | Type | Notes |
|---|---|---|
| `branch_id` | UUID FK → `branches.id` ON DELETE CASCADE | Nullable — `NULL` = clinic-wide |
| `department_id` | UUID FK → `departments.id` ON DELETE CASCADE | Nullable — see "`queue_settings.department_id`" below |
| `doctor_id` | UUID FK → `doctors.id` ON DELETE CASCADE | Nullable — added Post-RC1 (Multi-Department/Multi-Doctor TV Queue Display), migration `0025_queue_setting_doctor_prefix`; see below |
| `room_label` | VARCHAR(50) | Nullable — added Post-RC1 (room-based TV announcements), migration `0026_queue_setting_room_label`; see below |
| `queue_prefix` | VARCHAR(10) NOT NULL DEFAULT 'A' | |
| `max_daily_queue` | INTEGER NOT NULL DEFAULT 200 | |
| `reset_time` | TIME NOT NULL | |
| `allow_walkins`, `allow_priority_lane` | BOOLEAN NOT NULL DEFAULT true | |

**Indexes:** btree on `clinic_id`, `department_id`, `doctor_id`; unique on `(clinic_id, branch_id, department_id, doctor_id)` (widened from `(clinic_id, branch_id, department_id)` by migration `0025_queue_setting_doctor_prefix`).

`priority_types`: `code` (unique per clinic), `label`, `enabled`. Default set (Senior Citizen, PWD, Pregnant, Emergency, VIP) optionally seeded via `POST /queue-settings/priority-types/seed-defaults`.

### `operating_hours`

| Column | Type | Notes |
|---|---|---|
| `branch_id` | UUID FK → `branches.id` ON DELETE CASCADE NOT NULL | |
| `day_of_week` | SMALLINT NOT NULL | `0`=Monday .. `6`=Sunday |
| `opening_time`, `closing_time` | TIME NULL | |
| `lunch_break_start`, `lunch_break_end` | TIME NULL | |
| `is_closed` | BOOLEAN NOT NULL DEFAULT false | |

**Indexes:** btree on `clinic_id`, `branch_id`; unique on `(clinic_id, branch_id, day_of_week)`.

### `holidays`

| Column | Type | Notes |
|---|---|---|
| `holiday_name` | VARCHAR(150) NOT NULL | |
| `date` | DATE NOT NULL | |
| `is_recurring` | BOOLEAN NOT NULL DEFAULT false | Yearly recurrence flag |
| `is_closed` | BOOLEAN NOT NULL DEFAULT true | |
| `is_half_day` | BOOLEAN NOT NULL DEFAULT false | |
| `branch_id` | UUID FK → `branches.id` ON DELETE CASCADE | Nullable — `NULL` = clinic-wide |

**Indexes:** btree on `clinic_id`, `branch_id`, `date`.

---

## Phase 5: Reception & Queue Management

### `LegacyMixin` extension

Migration `0005_reception_queue` adds five additive, nullable columns to `LegacyMixin` — applied to every table that already uses it (`clinics`, `patients`, `users`) plus the new `queues` table:

| Column | Type | Notes |
|---|---|---|
| `legacy_created_at`, `legacy_updated_at` | TIMESTAMPTZ NULL | Original timestamps from the legacy Windows desktop app, distinct from this DB's own `created_at`/`updated_at` |
| `migration_batch_id` | VARCHAR(64) NULL, indexed | Groups rows imported together in one ETL run |
| `migration_source` | VARCHAR(100) NULL | Free-text label for the source system/export |
| `imported_at` | TIMESTAMPTZ NULL | When the row was written by the migration tool |

### `queue_settings.department_id`

Rather than adding a new queue-configuration table, Phase 4's `queue_settings` (clinic + nullable branch, unique per `(clinic_id, branch_id)`) gained a nullable `department_id` FK to `departments`, with the unique constraint widened to `(clinic_id, branch_id, department_id)`. This lets a clinic configure a clinic-wide prefix, override it per branch, and further override it per department (e.g. `"GM"` for General Medicine, `"DEN"` for Dental) — reusing all of Phase 4's existing prefix/cap/reset-time/walk-in/priority-lane fields instead of duplicating them in a parallel table. `QueueService._resolve_prefix` looks up the most specific matching row (department override, else branch, else clinic default `"A"`).

### `queue_settings.doctor_id` (Post-RC1: Multi-Department/Multi-Doctor TV Queue Display)

Migration `0025_queue_setting_doctor_prefix` adds a nullable `doctor_id` FK to `doctors`, one level narrower than `department_id` above, widening the unique constraint again to `(clinic_id, branch_id, department_id, doctor_id)`. This lets two doctors who share the same department get different queue prefixes (e.g. Dr. A → `"A"`, Dr. B → `"B"`, both in General Medicine). `QueueSettingRepository.get_effective_for_doctor` resolves doctor override → department override → branch/clinic default → hardcoded `"A"`, mirroring `get_effective_for_department`'s pattern one level deeper. Resolution requires an EXACT match on every non-null scope column of the query, including `branch_id` — a row saved with `branch_id = NULL` only resolves for a lookup that itself passes `branch_id = NULL`, which never happens for a real queue ticket (`Queue.branch_id` is NOT NULL). This is a pre-existing characteristic of the department-override chain (not new to this doctor-level addition) and is the root cause of BUG-033 (`docs/BUGS.md`) — the admin UI for both the department/doctor override form (`/queue-settings`) has been built branch_id-aware (selects/auto-selects a real branch) specifically to avoid hitting that same trap for the new doctor-scoped rows.

### `queue_settings.room_label` (Post-RC1: room-based TV announcements)

Migration `0026_queue_setting_room_label` adds a nullable `room_label` (VARCHAR(50)) to `queue_settings`, purely additive — no column removed, no constraint change, `NULL` for every existing row (falls back to the pre-existing doctor/department-name announcement, no behavior change for a clinic that never configures one). Set on the same doctor/department/branch override row already used for `queue_prefix` (not a new table or a new link to `consultation_rooms`), since prefix and room are naturally configured together in the admin UI for the same destination. `TvDisplayService._resolve_room_label` resolves it with the identical "narrowest scope wins" chain as prefix resolution (doctor override → department override → branch/clinic default); a row that exists for prefix purposes but leaves `room_label` blank means "no room for this destination," not "inherit the parent's room" — deliberately not cascading further up the chain. See the "Known gap" paragraph above (Phase 13 section) for how this relates to the still-missing `consultation_rooms` FK link.

### `queues`

The actual walk-in/queue ticket record.

| Column | Type | Notes |
|---|---|---|
| `branch_id` | UUID FK → `branches.id` ON DELETE CASCADE NOT NULL | |
| `patient_id` | UUID FK → `patients.id` ON DELETE RESTRICT NOT NULL | Restrict, not cascade — a patient with queue history cannot be hard-deleted |
| `department_id` | UUID FK → `departments.id` ON DELETE RESTRICT NOT NULL | |
| `doctor_id` | UUID FK → `doctors.id` ON DELETE SET NULL | Nullable — a ticket can be unassigned |
| `service_id` | UUID FK → `services.id` (the existing Phase 4 `ClinicService` catalog) ON DELETE RESTRICT NOT NULL | No new services table — reuses Phase 4's catalog directly |
| `queue_number` | VARCHAR(20) NOT NULL | e.g. `A001`, `GM001` |
| `queue_prefix` | VARCHAR(10) NOT NULL | Snapshotted at creation time so a later prefix config change doesn't rewrite history |
| `queue_date` | DATE NOT NULL | |
| `priority` | ENUM `queue_priority` (Normal, SeniorCitizen, PWD, Pregnant, Emergency, VIP) | |
| `status` | ENUM `queue_status` (Waiting, Called, Serving, Completed, Skipped, Cancelled, NoShow) | |
| `notes` | TEXT NULL | |
| `called_at`, `serving_started_at`, `completed_at` | TIMESTAMPTZ NULL | Set by the corresponding status transition |
| `created_by`, `updated_by` | UUID FK → `users.id` ON DELETE SET NULL | |

**Indexes:** btree on `clinic_id`, `branch_id`, `patient_id`, `department_id`, `doctor_id`, `service_id`, `status`, `queue_date`, `legacy_id`, `migration_batch_id`; composite `(clinic_id, branch_id, queue_date, status)` for the "today's queue" list query; composite `(clinic_id, queue_date, patient_id)`. Unique on `(clinic_id, branch_id, queue_date, queue_prefix, queue_number)`.

**Duplicate-active-ticket prevention:** a raw partial unique index (not expressible via SQLAlchemy's `UniqueConstraint`) enforces the rule at the database level, in addition to the application-level check in `QueueService.create_queue`:

```sql
CREATE UNIQUE INDEX uq_queues_active_patient_department_day
ON queues (clinic_id, patient_id, department_id, queue_date)
WHERE is_deleted = false AND status IN ('Waiting', 'Called', 'Serving')
```

### `queue_status_history`

Append-only log of every status transition, separate from the generic `audit_logs` table (both are written on every transition) because the queue-specific timeline is rendered directly in the Queue Details UI and benefits from a narrow, purpose-built shape.

| Column | Type | Notes |
|---|---|---|
| `queue_id` | UUID FK → `queues.id` ON DELETE CASCADE NOT NULL | |
| `from_status` | ENUM `queue_status` NULL | `NULL` on the initial "created" entry |
| `to_status` | ENUM `queue_status` NOT NULL | |
| `changed_by` | UUID FK → `users.id` ON DELETE SET NULL | |
| `changed_at` | TIMESTAMPTZ NOT NULL | |
| `note` | TEXT NULL | |

### `queue_counters` — queue-number generation strategy

Backs `QueueNumberGenerator`. Unlike `PatientNumberGenerator`/`DoctorCodeGenerator` (which store their counter as a JSONB value on a `system_settings` row, keyed by a single string), queue numbering has a genuinely composite, daily-resetting natural key — `(clinic_id, branch_id, queue_prefix, counter_date)` — which maps far more naturally onto real columns with a unique constraint than onto a nested JSONB blob. One row per bucket:

| Column | Type | Notes |
|---|---|---|
| `branch_id` | UUID FK → `branches.id` ON DELETE CASCADE NOT NULL | |
| `queue_prefix` | VARCHAR(10) NOT NULL | |
| `counter_date` | DATE NOT NULL | |
| `next_number` | INTEGER NOT NULL DEFAULT 1 | |

Unique on `(clinic_id, branch_id, queue_prefix, counter_date)`. `QueueNumberGenerator.next_number` selects the row `FOR UPDATE` (via `INSERT ... ON CONFLICT DO NOTHING` then re-select, to avoid poisoning the transaction on a concurrent first-insert race), increments `next_number`, and formats `f"{prefix}{str(n).zfill(padding)}"` — verified correct and gap-free under 20 concurrent `asyncio.gather`-issued requests in `test_queues.py::test_queue_number_generation_concurrency_safe`.

---

## Phase 6: Visit (Encounter) Management

### `visits`

The central encounter record every future clinical/billing module (SOAP notes, diagnosis, prescriptions, laboratory, billing) will attach to. Carries the full `LegacyMixin`/`TenantMixin`/`SoftDeleteMixin` set (migration `0006_visit_management`) for legacy-migration readiness.

| Column | Type | Notes |
|---|---|---|
| `branch_id` | UUID FK → `branches.id` ON DELETE CASCADE NOT NULL | |
| `patient_id` | UUID FK → `patients.id` ON DELETE RESTRICT NOT NULL | Restrict, not cascade |
| `queue_id` | UUID FK → `queues.id` ON DELETE SET NULL NULL | Set at creation time when the visit originated from a queue ticket (the normal case); see the Queue ↔ Visit link below |
| `doctor_id` | UUID FK → `doctors.id` ON DELETE SET NULL NULL | |
| `department_id` | UUID FK → `departments.id` ON DELETE SET NULL NULL | |
| `service_id` | UUID FK → `services.id` ON DELETE SET NULL NULL | |
| `visit_number` | VARCHAR(30) NOT NULL | `VIS-YYYYMMDD-000001`, unique per clinic |
| `visit_date` | DATE NOT NULL | |
| `visit_type` | ENUM `visit_type` (WalkIn, Appointment, FollowUp, Emergency, Teleconsultation, HomeService) | |
| `status` | ENUM `visit_status` (Registered, Waiting, Called, InConsultation, Completed, Cancelled, NoShow) | |
| `priority` | ENUM `visit_priority` (Normal, SeniorCitizen, PWD, Pregnant, Emergency, VIP) | Values mirror `queue_priority`; kept as a distinct enum so `Visit` stays decoupled from `Queue`'s schema |
| `arrival_time`, `check_in_time`, `called_time`, `consultation_start`, `consultation_end`, `check_out_time` | TIMESTAMPTZ NULL | Set by the corresponding status transition / creation step |
| `remarks` | TEXT NULL | |
| `created_by`, `updated_by` | UUID FK → `users.id` ON DELETE SET NULL | |

**Indexes:** btree on `clinic_id`, `branch_id`, `patient_id`, `queue_id`, `doctor_id`, `department_id`, `service_id`, `status`, `visit_date`, `legacy_id`, `migration_batch_id`; composite `(clinic_id, branch_id, visit_date, status)` for the "today's visits" query; composite `(clinic_id, visit_date, patient_id)` for patient visit history. Unique on `(clinic_id, visit_number)`.

### `visit_timeline_events`

Append-only, human-readable timeline rendered on the Visit Details page — separate from (but written alongside) the generic `audit_logs` table, same rationale as Phase 5's `queue_status_history`.

| Column | Type | Notes |
|---|---|---|
| `visit_id` | UUID FK → `visits.id` ON DELETE CASCADE NOT NULL | |
| `event_type` | ENUM `visit_timeline_event_type` (Registered, CheckedIn, Queued, Called, ConsultationStarted, ConsultationFinished, CheckedOut, StatusChanged, Cancelled, Note) | Extensible - `Note` covers ad-hoc/free-text entries |
| `occurred_at` | TIMESTAMPTZ NOT NULL | |
| `recorded_by` | UUID FK → `users.id` ON DELETE SET NULL NULL | `NULL` for system-generated events |
| `note` | TEXT NULL | |
| `event_metadata` | JSONB NULL | e.g. `{"from_status": ..., "to_status": ...}` on `StatusChanged` events |

### `visit_counters` — visit-number generation strategy

Backs `VisitNumberGenerator`, mirroring `queue_counters`/`QueueNumberGenerator` exactly (see that section above) but scoped by `(clinic_id, branch_id, counter_date)` — one row per clinic+branch+day, no prefix dimension since the format is fixed (`VIS-YYYYMMDD-######`).

| Column | Type | Notes |
|---|---|---|
| `branch_id` | UUID FK → `branches.id` ON DELETE CASCADE NOT NULL | |
| `counter_date` | DATE NOT NULL | |
| `next_number` | INTEGER NOT NULL DEFAULT 1 | |

Unique on `(clinic_id, branch_id, counter_date)`. `VisitNumberGenerator.next_number` selects the row `FOR UPDATE` (via `INSERT ... ON CONFLICT DO NOTHING` then re-select), increments `next_number`, and formats `f"VIS-{date:%Y%m%d}-{str(n).zfill(6)}"` — verified gap-free under 20 concurrent `asyncio.gather`-issued requests in `test_visits.py::test_visit_number_generation_concurrency_safe`.

### Queue ↔ Visit link and creation-order decision

`queues` gains a nullable, additive `visit_id` FK → `visits.id` ON DELETE SET NULL (both sides are nullable to avoid a chicken-and-egg constraint: `visits` is created first, referencing the pre-existing `queues` table via a nullable FK, then `queues.visit_id` is added as a second column).

**Creation order:** creating a Queue ticket (`POST /queues`) transactionally creates its linked Visit internally — `QueueService.create_queue()` calls `VisitService.create_visit_for_queue()` in the same DB transaction as the queue-ticket insert (after the queue row exists, so its `id` can be passed in as `visit.queue_id`), then the same transaction sets `queue.visit_id` back. Both writes commit or roll back together. This order (Queue → creates → Visit) was chosen because it requires zero changes to the already-verified Phase 5 queue row/number/duplicate-check logic — the hook is purely additive, appended after the existing queue-creation steps in `queue_service.py`. The Phase 5 `POST /queues` request/response contract stays backward compatible: `visit_id` and `visit_number` are new, optional fields on the response, and every other Phase 5 queue endpoint (list/status-transition/cancel/slip) is unmodified.

`POST /visits` also exists as a standalone endpoint for internal/test use (and to keep the service layer honest), but is not the real-world creation path — receptionists never call it directly.

### Legacy migration readiness

`visits` carries `LegacyMixin` (`legacy_id`/`legacy_meta`/`migration_batch_id`/`migration_source`/`imported_at`), covered by the same mapping strategy described above, so a future ETL from the legacy desktop app's encounter/visit history can populate this table directly. `visit_timeline_events` does not carry `LegacyMixin` — it is a first-class-only, append-only domain log.

---

## Phase 7: Doctor Workspace

Migration `0007_doctor_workspace`. Adds one column to an existing table and three new tables, all built on top of Phase 6's `visits`/`visit_timeline_events` rather than duplicating any of that model.

### `users.doctor_id` — resolving "which Doctor is this login?"

A nullable, additive FK column: `doctor_id UUID REFERENCES doctors(id) ON DELETE SET NULL`, indexed. Only meaningful for Doctor-role users (`NULL` for everyone else); a simple FK was chosen over a link table since the relationship is 1:1 in practice — one login belongs to exactly one Doctor record. This is what lets the API resolve "Doctors may only view Visits assigned to them" server-side (`api/v1/doctor_workspace.py::_resolve_target_doctor`/`_act_doctor`) without trusting a client-supplied doctor id.

No pre-existing linking mechanism existed before this phase (`users` had no `doctor_id`/similar column). The seeded dev doctor login (`maria.santos@connectph.dev`, see below) was created through the real `POST /users` endpoint and then linked via a direct `UPDATE users SET doctor_id = ...` — **documented follow-up TODO:** extend `UserCreate`/`POST /users` to accept `doctor_id` directly (currently the create-user schema has no such field) so this link doesn't require an out-of-band SQL step for future doctor onboarding.

### `consultation_sessions`

One row per "Start Consultation" → "Complete Consultation" span. Exists alongside `visits.consultation_start`/`consultation_end` (still the source of truth for the Visit's own timestamps) so the Doctor Dashboard's "average consultation time" stat has a precomputed, directly-queryable `duration_seconds` column instead of diffing timestamps across joined Visit rows on every dashboard read.

| Column | Type | Notes |
|---|---|---|
| `visit_id` | UUID FK → `visits.id` ON DELETE CASCADE NOT NULL | |
| `doctor_id` | UUID FK → `doctors.id` ON DELETE CASCADE NOT NULL | |
| `started_at` | TIMESTAMPTZ NOT NULL | |
| `ended_at` | TIMESTAMPTZ NULL | NULL while the session is active |
| `duration_seconds` | INTEGER NULL | computed on end |
| `status` | ENUM(`Active`, `Ended`) NOT NULL DEFAULT `Active` | |

Plus `TenantMixin`/`SoftDeleteMixin`/`TimestampMixin`/`LegacyMixin` (legacy-migration readiness for a future encounter-duration import).

### `visit_locks` — editing lock, acquisition/release/expiry design

Enforces "when one doctor opens a Visit, lock editing; others may view but not edit." One *active* lock (`released_at IS NULL`) is meaningful per visit at a time; this is enforced in the service layer (`DoctorWorkspaceService`/`DoctorWorkspaceRepository.get_active_lock`), not via a partial unique index, so history (released rows) is retained rather than deleted.

| Column | Type | Notes |
|---|---|---|
| `visit_id` | UUID FK → `visits.id` ON DELETE CASCADE NOT NULL | |
| `locked_by` | UUID FK → `users.id` ON DELETE CASCADE NOT NULL | |
| `locked_at` | TIMESTAMPTZ NOT NULL | |
| `released_at` | TIMESTAMPTZ NULL | NULL means still locked |

**Release/expiry strategy** (see `models/visit_lock.py` docstring), whichever happens first:
1. **Explicit release** — `POST /doctor-workspace/visits/{id}/release-lock`.
2. **Terminal status** — `complete_consultation`/`cancel_visit`/`mark_no_show` release any open lock on the visit as a side effect.
3. **Heartbeat expiry** — a lock older than `LOCK_TTL_MINUTES` (15, in `doctor_workspace_service.py`) since `locked_at` is treated as stale by `open_visit()` and handed to the next caller. The frontend visit viewer re-calls `open` every 5 minutes while mounted as a heartbeat (see `use-doctor-actions.ts`), well inside the TTL.

Plus `TenantMixin`/`TimestampMixin`/`LegacyMixin`; no soft-delete (locks are ephemeral, not domain records worth preserving that way).

### `doctor_activity`

Domain-specific doctor action log feeding the Doctor Dashboard's stat cards quickly, mirroring how `visit_timeline_events` relates to the generic `audit_logs` table (Phase 6) — every doctor-workspace action writes here **and** to `audit_logs` via `AuditService`, so the fast dashboard-facing log stays small while the compliance trail stays complete.

| Column | Type | Notes |
|---|---|---|
| `doctor_id` | UUID FK → `doctors.id` ON DELETE CASCADE NOT NULL | |
| `user_id` | UUID FK → `users.id` ON DELETE CASCADE NOT NULL | |
| `visit_id` | UUID FK → `visits.id` ON DELETE SET NULL NULL | |
| `activity_type` | ENUM(`PatientCalled`, `PatientRecalled`, `ConsultationStarted`, `ConsultationCompleted`, `MarkedNoShow`, `VisitCancelled`, `VisitOpened`) NOT NULL | |
| `occurred_at` | TIMESTAMPTZ NOT NULL | |
| `activity_metadata` | JSONB NULL | |

Plus `TenantMixin`/`TimestampMixin`/`LegacyMixin`.

### Legacy migration readiness

`consultation_sessions`, `visit_locks`, and `doctor_activity` all carry `LegacyMixin` (`legacy_id`/`legacy_meta`/`migration_batch_id`/`migration_source`/`imported_at`), consistent with every first-class transactional table added since Phase 5, so a future ETL from the legacy desktop app's consultation-duration/activity history can populate these directly.

---

## Phase 8: Clinical Consultation / SOAP

Migration `0008_clinical_consultation`. Adds four new tables, two additive columns on `patients`, and five new `visit_timeline_event_type` enum values, all built on top of Phase 6's `visits`/`visit_timeline_events` and Phase 7's `visit_locks` rather than duplicating either.

### `consultations` — one clinical encounter per Visit

**Design decision (documented, not enforced via a hard unique constraint):** rather than a DB-level `UNIQUE(visit_id)`, which would make it impossible to represent re-opening a *closed* consultation as a fresh row for legitimate append-only history, the repository always resolves "the" consultation for a visit via `ORDER BY created_at DESC LIMIT 1` ("latest wins" — see `ConsultationRepository.get_latest_for_visit`). `open_consultation()` resumes the existing row for a visit rather than creating a new one whenever one already exists, so in practice there is exactly one Consultation per Visit today; the "latest wins" pattern just leaves room for a future re-open-with-history flow without a migration.

| Column | Type | Notes |
|---|---|---|
| `visit_id` | UUID FK → `visits.id` ON DELETE CASCADE NOT NULL | |
| `branch_id` | UUID FK → `branches.id` ON DELETE CASCADE NOT NULL | |
| `doctor_id` | UUID FK → `doctors.id` ON DELETE RESTRICT NOT NULL | |
| `patient_id` | UUID FK → `patients.id` ON DELETE RESTRICT NOT NULL | denormalized, consistent with how `visits.patient_id` denormalizes rather than requiring a join |
| `status` | ENUM(`Draft`, `InProgress`, `Completed`, `Signed`) NOT NULL DEFAULT `Draft` | legal transitions in `CONSULTATION_STATUS_TRANSITIONS` (`models/consultation.py`) |
| `started_at` | TIMESTAMPTZ NOT NULL | |
| `completed_at` / `signed_at` | TIMESTAMPTZ NULL | |

Plus `TenantMixin`/`SoftDeleteMixin`/`TimestampMixin`/`LegacyMixin`, `created_by`/`updated_by`.

### `soap_notes` — one-to-one with `consultations`, upserted in place

**Design decision:** a consultation has exactly one SOAP note, upserted on every autosave (`PUT /consultations/{id}/soap`) rather than a new row per save — `consultation_id` carries a DB-level `UNIQUE` constraint. A full point-in-time history of every draft keystroke is not required by spec; only the final saved note plus the append-only `visit_timeline_events` record of *that* a save happened (see below).

All Subjective/Objective/Assessment/Plan fields from the spec are nullable `TEXT` (or `INTEGER`/`FLOAT` for vitals): `chief_complaint`, `history_of_present_illness`, `past_medical_history`, `family_history`, `social_history`, `review_of_systems`, `subjective_notes`; `blood_pressure`, `pulse_rate`, `respiratory_rate`, `temperature`, `height_cm`, `weight_kg`, `bmi` (server-computed from height/weight, stored — see `ConsultationService._compute_bmi`), `oxygen_saturation`, `physical_examination`, `clinical_findings`; `clinical_impression`, `differential_diagnosis`, `assessment_notes`; `treatment_plan`, `patient_instructions`, `followup_recommendation`, `referral_notes`. Plus `TenantMixin`/`TimestampMixin`/`LegacyMixin`.

### `diagnoses`

| Column | Type | Notes |
|---|---|---|
| `consultation_id` | UUID FK → `consultations.id` ON DELETE CASCADE NOT NULL | |
| `diagnosis_type` | ENUM(`Primary`, `Secondary`) NOT NULL | |
| `status` | ENUM(`Working`, `Final`) NOT NULL DEFAULT `Working` | |
| `notes` | TEXT NULL | |
| `icd10_code` / `icd10_description` | VARCHAR NULL | architecture-only — no ICD-10 search/autocomplete UI per spec |

Plus `TenantMixin`/`SoftDeleteMixin`/`TimestampMixin`/`LegacyMixin`, `created_by`.

### `consultation_attachments` — real upload path (Lab Requests excluded by design)

Uses the same presigned-URL-stub pattern as `PatientService.request_photo_upload_url` (no Supabase project provisioned in dev yet). `attachment_type` is `ENUM(ClinicalImage, PDF, ReferralLetter)` — deliberately **no** `LabRequest` member, since Lab Requests stay a placeholder with no upload path per spec, distinct from the other three which get a real (stubbed-storage) upload flow.

| Column | Type | Notes |
|---|---|---|
| `consultation_id` | UUID FK → `consultations.id` ON DELETE CASCADE NOT NULL | |
| `attachment_type` | ENUM(`ClinicalImage`, `PDF`, `ReferralLetter`) NOT NULL | |
| `file_name` | VARCHAR(255) NOT NULL | |
| `file_url` | VARCHAR(500) NOT NULL | stub URL today |
| `file_size_bytes` | BIGINT NULL | |
| `uploaded_by` | UUID FK → `users.id` ON DELETE SET NULL NULL | |

Plus `TenantMixin`/`SoftDeleteMixin`/`TimestampMixin`/`LegacyMixin`.

### `patients.emergency_contact_name` / `emergency_contact_phone`

Additive nullable columns closing the Phase 7 TODO ("no UI existed to capture emergency contact info"). Displayed in the Consultation page's always-visible Patient Summary header.

### Consultation ↔ Visit lock — reuses `visit_locks`, no new table

**Design decision:** a Visit and its Consultation are 1:1 in this phase (a consultation is the clinical detail of the visit's encounter), so `ConsultationService` acquires/checks/releases locks by calling straight into the existing `DoctorWorkspaceRepository`'s `visit_locks` methods, keyed by `visit_id` — exactly the same rows Phase 7's Doctor Workspace locking already produces. No second `consultation_locks` table was introduced; opening a consultation is functionally "opening the visit for clinical editing."

### Consultation ↔ Visit (and Queue) status sync

**Design decision (the Phase 7 lesson, applied one hop further):** `ConsultationService.complete_consultation()` transitions `Consultation.status` to `Completed` and then calls `VisitService.change_status(..., VisitStatus.COMPLETED)` — the same single source of truth Phase 7's `DoctorWorkspaceService` uses, never a duplicated transition table. If the Visit is already `Completed` (e.g. the doctor used the Doctor Workspace "Complete Consultation" button first), the call is a tolerated no-op, not a 400.

Critically, completing a Consultation is *another independent path* (besides the Doctor Workspace) that can complete a Visit — so `ConsultationService` **also** mirrors the Visit's linked Queue ticket to `Completed` (`ConsultationService._sync_queue_status`, a deliberate near-duplicate of `DoctorWorkspaceService._sync_queue_status`, same "don't force an illegal Queue transition" tolerance). This was caught live during manual verification: completing a consultation via `POST /consultations/{id}/complete` without ever hitting the Doctor Workspace button left the linked Queue ticket stuck on "Serving" — exactly the class of bug Phase 7 was bitten by once already, one hop further down the call chain. Fixed before shipping; see `docs/TESTING.md` for the regression test (`test_complete_consultation_reflects_onto_visit_status`) and the live curl verification transcript in the Phase 8 completion notes.

### Autosave idempotency

`PUT /consultations/{id}/soap` only writes a `visit_timeline_events`/`audit_logs` entry when the submitted SOAP content actually differs from what's already stored (or on the very first save that adds real content to a previously-empty note). A 30-second autosave interval resubmitting identical content therefore still updates `soap_notes.updated_at` but never spams the timeline or audit log — verified by `test_autosave_idempotent_no_timeline_spam`.

### `visit_timeline_event_type` additions

Five new enum values added via `ALTER TYPE ... ADD VALUE`: `ConsultationOpened`, `SoapSaved`, `DiagnosisAdded`, `ConsultationCompleted`, `ConsultationSigned`. Consultation events are recorded on the *existing* Visit timeline table (not a parallel one) — `GET /consultations/{id}/timeline` is a thin wrapper over the same `visit_timeline_events` rows `GET /visits/{id}` already exposes, scoped to the consultation's `visit_id`.

### Legacy migration readiness

`consultations`, `soap_notes`, `diagnoses`, and `consultation_attachments` all carry `LegacyMixin`, consistent with every first-class transactional table added since Phase 5.

## Phase 9: Clinical Orders & Prescriptions

Migration `0009_clinical_orders_prescriptions.py` (revision id `0009_clinical_orders` — see "Migration slot coordination" below). Adds `orders`/`order_items`, `procedures`, `referrals`, `prescriptions`/`prescription_items`, and four new `visit_timeline_event_type` values.

### Migration slot coordination

This phase and the concurrently-developed Billing & Cashier phase both initially targeted the `0009` migration slot. Per explicit priority, Clinical Orders kept `0009` with `down_revision = 0008_clinical_consultation` (revision id shortened to `0009_clinical_orders` — the descriptive filename `0009_clinical_orders_prescriptions.py` exceeded `alembic_version.version_num`'s `VARCHAR(32)` column limit, so the *revision id* is short while the *filename* stays descriptive). Billing was renumbered to `0010_billing_cashier`, descending from this migration, so the final chain is linear: `0008 → 0009_clinical_orders → 0010_billing_cashier`.

### `orders` / `order_items`

| Column | Type | Notes |
|---|---|---|
| `consultation_id` / `visit_id` | UUID FK, NOT NULL | `visit_id` denormalized for query convenience, same convention as `consultations`/`invoices` |
| `branch_id` / `patient_id` | UUID FK, NOT NULL | denormalized |
| `doctor_id` | UUID FK → `doctors.id` ON DELETE SET NULL | |
| `order_number` | VARCHAR(40) NOT NULL, UNIQUE per `clinic_id` | `ORD-YYYYMMDD-000001` via `OrderNumberGenerator` (`services/clinical_number_generator.py`), reusing `PatientNumberGenerator`'s `system_settings`-backed, `SELECT...FOR UPDATE`-locked counter pattern, date-scoped like `VisitNumberGenerator` |
| `order_category` | ENUM(`Laboratory`,`Radiology`,`Procedure`,`Referral`,`Vaccination`,`Custom`) NOT NULL | |
| `priority` | ENUM(`Routine`,`STAT`) NOT NULL DEFAULT `Routine` | |
| `scheduled_date` | DATE NULL | |
| `clinical_notes` | TEXT NULL | |
| `status` | ENUM(`Requested`,`Collected`,`Processing`,`Completed`,`Cancelled`) NOT NULL DEFAULT `Requested` | **shared across all order categories** — accepted simplification: "Collected" reads oddly for e.g. a Referral order, but one uniform status shape lets a future Laboratory/Radiology-processing phase drive any order category forward without a per-category status table |

`order_items`: `order_id` FK, `item_name` (free text, no fixed catalog enforced in the DB — the frontend offers a suggestion list only), `item_category`, plus three nullable Imaging-specific fields `exam_type`/`body_part`/`clinical_indication`. **Design decision:** a few nullable typed columns rather than a JSON `details` blob, since the spec names these Imaging fields explicitly ("Exam Type", "Body Part") while Laboratory only needs `item_name` — typed columns stay queryable/indexable and cost nothing on non-Imaging rows.

### `procedures` and `referrals` — their own tables, not `orders` rows

**Design decision:** although Procedure and Referral are also listed as `orders.order_category` values (for a unified "Clinical Orders" umbrella tab), the spec's DATABASE section separately lists "Procedures"/"Referral" as top-level table names with their own field lists — notably Procedures has **no Order Number** field, unlike every other order category. Rather than making `orders.order_number` nullable just for this one case, `procedures` (`procedure_name`, `procedure_date`, `notes`, `status` reusing `order_status`) and `referrals` (`referred_to`, `reason`, `notes`, `status` reusing `order_status`) are separate tables with the same `consultation_id`/`visit_id`/`branch_id`/`patient_id`/`doctor_id` shape as `orders`. The Consultation page's "Clinical Orders" tab UI unifies `orders` + `procedures` + `referrals` into one view for the doctor; there is deliberately no `orders` row created for a Procedure or Referral (no duplicate bookkeeping).

### `prescriptions` / `prescription_items`

`prescriptions`: `prescription_number` (`RX-YYYYMMDD-000001` via `PrescriptionNumberGenerator`, same pattern as Orders), `status` ENUM(`Draft`,`Finalized`,`Cancelled`) — the spec did not enumerate prescription status values, this is a sensible minimal set. Multiple prescriptions per consultation are allowed (e.g. a corrected/reissued prescription); callers use the same "latest wins" `ORDER BY created_at DESC` pattern Phase 8 established for Consultation-per-Visit, rather than a hard unique constraint.

`prescription_items`: `medicine`, `generic_name`, `brand_name`, `strength`, `dosage`, `frequency`, `duration`, `quantity` (VARCHAR — spec doesn't specify units, so free text like "30 tabs" is safer than an int), `route`, `instructions`, `substitution_allowed` (BOOLEAN DEFAULT true). No upper bound on items per prescription — verified live and by `test_create_prescription_with_many_items` (6 items).

### Prescription validation warnings (non-blocking) and allergy-conflict placeholder

`ClinicalOrdersService._validate_prescription_items()` checks for duplicate medicine names (case-insensitive), missing `dosage`, and missing `duration` within the submitted item list, and returns them as a `warnings: list[str]` alongside the successful save response (`POST /consultations/{id}/prescriptions` never blocks on these) — verified live: a prescription with a deliberately-missing-dosage item still saves and surfaces the warning. `ClinicalOrdersService.check_allergy_conflicts()` is an explicit architecture-only placeholder (always returns `[]`) — there is no drug/allergy database in this phase; a future phase needs a real formulary with active-ingredient mappings and a patient allergy list before this can do anything.

### Consultation/Visit-state design decision (Phase 7/8 lesson applied again)

Creating an Order/Procedure/Referral/Prescription does **not** change `Consultation.status` or `Visit.status` — per the spec's workflow (SOAP → Diagnosis → Clinical Orders → Prescription → Complete Consultation), these are records created *during* an in-progress consultation, not consultation-state transitions themselves. However, exactly like Phase 8's `add_diagnosis()`, every creation writes a `visit_timeline_events` row (new event types `OrderCreated`/`ProcedureCreated`/`ReferralCreated`/`PrescriptionCreated`) and an `audit_logs` entry, so it shows up correctly in the Visit's Orders/Prescription tabs and Timeline, and in read-only history — this was the exact class of bug Phase 7 and Phase 8 each got bitten by once (a new child entity not reflected onto the parent's visible state), deliberately avoided here from the start and verified live via curl (`GET /visits/{id}/orders`, `/prescriptions`, `/timeline`) rather than only by unit test.

### Role gating

`CLINICAL_ORDERS_EDIT_ROLES` = Owner/Administrator/Doctor, further restricted in the service/API layer to "only the visit's assigned doctor" (Owner/Administrator pass the gate but are never granted `can_edit=True` — view-only, same pattern as Phase 8). `CLINICAL_ORDERS_VIEW_ROLES` additionally includes **Receptionist**, who gets explicit read-only access (`Reception: Read-only` per this phase's spec — distinct from Phase 8, which excluded Receptionist entirely from Consultation/SOAP). A new `CLINICAL_ORDERS_LAB_VIEW_ROLES` gate (`Owner`, `Administrator`, `Laboratory`) backs `GET /laboratory/orders?visit_id=`, scoped server-side to `order_category = Laboratory` only — the Laboratory role has no access to Prescriptions, Procedures, Referrals, or non-Laboratory orders.

### Legacy migration readiness

`orders`, `order_items`, `procedures`, `referrals`, `prescriptions`, and `prescription_items` all carry `LegacyMixin`, consistent with every first-class transactional table added since Phase 5.

## Phase 17: Billing & Cashier

Migration `0009_billing_cashier`. Adds six new tables on top of Phase 6's `visits` and Phase 8's `consultations`, following the same "layer on top, sync via the existing status-transition pattern" approach as every prior phase.

### `invoices` — the core billing document, one (usually) per Visit

| Column | Type | Notes |
|---|---|---|
| `invoice_number` | VARCHAR(30) NOT NULL, UNIQUE per `clinic_id` | `INV-YYYYMMDD-000001`, clinic-wide daily sequence (not branch-scoped — billing spans the whole clinic) via `InvoiceNumberGenerator` + `invoice_counters`, same `SELECT...FOR UPDATE` concurrency pattern as `VisitNumberGenerator`/`QueueNumberGenerator` |
| `visit_id` | UUID FK → `visits.id` ON DELETE RESTRICT NOT NULL | |
| `branch_id` / `patient_id` | UUID FK, NOT NULL | denormalized, same convention as `visits`/`consultations` |
| `doctor_id` | UUID FK → `doctors.id` ON DELETE SET NULL NULL | |
| `invoice_date` | DATE NOT NULL | |
| `status` | ENUM(`Draft`, `PendingPayment`, `PartiallyPaid`, `Paid`, `Cancelled`) NOT NULL DEFAULT `Draft` | legal transitions in `INVOICE_STATUS_TRANSITIONS` (`models/invoice.py`), including the backward `Paid`/`PartiallyPaid` → `PendingPayment` moves used by void-payment |
| `subtotal` / `discount_total` / `grand_total` / `amount_paid` / `balance_due` | NUMERIC(12,2) | all recomputed server-side on every item/discount/payment change (`InvoiceService._recompute_totals`, `PaymentService._recompute_amount_paid`) — never trusted from the client |
| `tax_total` | NUMERIC(12,2) NULL | future use, no tax logic wired yet |

Plus `TenantMixin`/`SoftDeleteMixin`/`TimestampMixin`/`LegacyMixin`, `created_by`/`updated_by`.

### `invoice_items`

`description`, `item_type` (ENUM `ConsultationFee`/`FollowUpFee`/`MedicalCertificate`/`Laboratory`/`XRay`/`Procedure`/`Vaccination`/`Custom`), `quantity` NUMERIC(10,2), `unit_price`/`discount_amount`/`tax_amount`/`line_total` NUMERIC(12,2), `notes`. Plus `TenantMixin`/`TimestampMixin`/`LegacyMixin`. Editable only while the invoice is `Draft`/`PendingPayment` (`InvoiceService._require_editable`) — locked once any payment has landed.

### `discounts` — invoice-level, not line-level

**Design decision:** applied at the invoice level rather than per-item. A clinic-wide discount (Senior Citizen/PWD/Employee) in this domain applies to the whole bill, not individual line items, so a single `invoice_id` FK (not `invoice_item_id`) keeps the common case simple; `discount_type` (ENUM `SeniorCitizen`/`PWD`/`Employee`/`Custom`), `calculation_type` (ENUM `Percentage`/`FixedAmount`), `value`, computed `amount`, `reason`, `approved_by` (FK `users`, defaults to the acting cashier). Plus `TenantMixin`/`TimestampMixin`/`LegacyMixin`.

### `payments` — supports split payments as multiple rows per invoice

`payment_method` (ENUM `Cash`/`GCash`/`BankTransfer`/`CreditCard`/`DebitCard`), `amount`, `reference_number` (non-cash), `status` (ENUM `Completed`/`Voided`), `received_by` (FK `users`), `paid_at`, `voided_at`/`voided_by`. Plus `TenantMixin`/`TimestampMixin`/`LegacyMixin`.

**Design decision — no `payment_methods` lookup table:** the spec lists a closed 5-value set ("Cash, GCash, Bank Transfer, Credit Card, Debit Card") that doesn't vary per clinic, so a configurable lookup table would be over-engineering; a plain enum is simpler and sufficient. Split payments are just multiple `payments` rows against the same `invoice_id`, summed by `PaymentService._recompute_amount_paid`.

**Design decision — no persisted `receipts` table:** a receipt is a computed, printable projection of an invoice + its `Completed` payments (`ReceiptService.build_receipt_payload`), not its own entity — `receipt_number` is derived deterministically from `invoice_number` (`{invoice_number}-R1`) rather than backed by an independent counter. "Receipt Printed" is still recorded as an `audit_logs` event (`invoice.receipt_printed`) on `POST /invoices/{id}/receipt/print`, giving a real audit trail without a redundant persisted row.

### `refunds` — architecture-only per spec

`payment_id` FK, `amount`, `reason`, `status` (plain VARCHAR `Pending`/`Approved`/`Rejected`/`Completed` today, not yet a hard enum since no workflow drives it beyond `PaymentService.create_refund`/`approve_refund` stubs), `approved_by`. Plus `TenantMixin`/`TimestampMixin`/`LegacyMixin`. **No refund UI was built** — `POST /payments/{id}/refund` and `POST /refunds/{id}/approve` exist as Administrator/Owner-only stub endpoints per spec ("architecture only").

### `invoice_counters`

Backing counter for `InvoiceNumberGenerator`, `UNIQUE(clinic_id, counter_date)`, same shape/locking as `visit_counters`/`queue_counters`.

### Consultation → Invoice sync

**Design decision (the Phase 7/8 lesson, applied one hop further):** per the spec's workflow diagram ("Doctor marks Consultation Complete → Billing Draft automatically created"), `ConsultationService.complete_consultation()` now also calls `InvoiceService.create_draft_invoice_for_consultation()` in the same method, mirroring exactly how it already calls into `VisitService`/`QueueService`. This is **idempotent**: if a non-cancelled invoice already exists for the visit, it's returned as-is rather than duplicated — verified by `test_invoice_creation_idempotent_on_double_complete` (a second `complete()` call on an already-completed consultation does not create a second invoice). The auto-added Consultation Fee line item is priced from `Doctor.consultation_fee` (more specific — a per-doctor fee) if set and positive, else the visit's `ClinicService.default_price` (the service-catalog price), else `0` (cashier edits it manually). The invoice starts `Draft` and immediately flips to `PendingPayment` once it has at least one item.

### Payment → Visit sync

**Design decision (the same lesson, one hop further still):** when a payment (or the last of a split-payment set) brings `amount_paid >= grand_total`, the invoice transitions to `Paid`, and `PaymentService._sync_visit_on_paid` then calls `VisitService.change_status(..., VisitStatus.COMPLETED)` if the Visit isn't already `Completed`/terminal — the "Visit Closed" terminal step of the spec's workflow diagram ("Consultation → Billing → Payment → Receipt → Visit Closed"). In practice the Visit is normally *already* `Completed` by the time billing happens (Phase 8's Consultation→Visit sync already closes it on consultation completion, before an invoice can even reach `Paid`), so this sync is usually a no-op — it only has a real effect for the edge case where a payment completes without that earlier sync having run. Like `ConsultationService._sync_queue_status`, it never forces an illegal transition (e.g. a Visit already `Cancelled` stays `Cancelled`); it just skips silently. Verified live via curl (see `docs/TESTING.md`) and by `test_full_payment_transitions_to_paid_and_syncs_visit`.

### Void-payment recomputation

`PaymentService.void_payment` doesn't just decrement `amount_paid` — it flips the payment's `status` to `Voided` and then recomputes `amount_paid`/`balance_due`/`status` **from scratch** off the remaining `Completed` payments (`_recompute_amount_paid`), so voiding is correct even with multiple payments/voids happening out of order. A fully-paid invoice whose only payment is voided moves back to `PendingPayment` automatically.

### Role gating

Cashier + Owner/Administrator can create/edit invoice items, apply discounts, and record/void payments (`BILLING_MANAGE_ROLES`). Administrator/Owner-only for refund approval (`BILLING_REFUND_ROLES`). Doctor gets view-only. **Receptionist gets read-only** (`BILLING_VIEW_ROLES` includes Receptionist, `BILLING_MANAGE_ROLES` does not) — per the spec's explicit "Reception: Read-only" wording for Billing, which is a *softer* rule than Phase 8's Receptionist-excluded-entirely-from-SOAP (403 on both view and edit there); reads succeed for Receptionist here, only writes 403. Verified by `test_role_gating_cashier_doctor_reception`.

### Legacy migration readiness

`invoices`, `invoice_items`, `discounts`, `payments`, and `refunds` all carry `LegacyMixin`, consistent with every first-class transactional table added since Phase 5.

---

## Phase 10: Laboratory Management

Migration `0011_laboratory_management` (`down_revision = 0010_billing_cashier`). Adds four new tables layered on top of Phase 9's `orders`/`order_items`.

### Design decision: new `laboratory_orders` table, not an extended `orders` table

The Phase 9 `Order` (`order_category=Laboratory`) stays the doctor-facing "I am requesting this test" record, created via the unchanged `POST /consultations/{id}/orders` endpoint. `laboratory_orders` is a **new table with a 1:1 `order_id` FK** back to that row, carrying the laboratory department's own richer workflow state (collection/processing/result-entry/release timestamps+actors, an optional link to a configurable `laboratory_templates` row, and the billing-idempotency key). This was chosen over extending `orders` in place because:

- Six lab-specific status values (including a terminal `Released` state) would be meaningless on Radiology/Procedure/Referral/Vaccination/Custom rows if added to the shared `order_status` enum.
- `laboratory_orders.order_number` is **not** its own sequence — it's read through the `order_id` FK to the Phase 9 `orders.order_number` (`ORD-YYYYMMDD-000001`), so a receptionist/doctor never sees two different numbering schemes for what they perceive as "the same order".
- `ClinicalOrdersService.create_order()` automatically creates the matching `laboratory_orders` row whenever a Laboratory-category order is created (idempotent — a repeat call for the same `order_id` returns the existing row), so the Laboratory Dashboard picks up new orders with zero extra doctor-facing steps.

### `laboratory_templates` / `laboratory_template_parameters` — the configurable test catalog

The "add a new test without code changes" piece. `laboratory_templates`: `test_name`, `test_category`, `specimen_type`, `default_price` (Numeric 12,2), `turnaround_time_hours`, `is_active`. `laboratory_template_parameters`: `template_id` FK, `parameter_name`, `unit`, `normal_range`, `result_type` (`Numeric`/`Text`), `display_order`.

**Design decision — a single `normal_range` text field per parameter, not per-sex columns:** most PH clinic lab slips print one combined range per parameter and doctors are used to reading it that way; per-sex/age-banded ranges were judged scope creep for this phase and can be added additively later (new nullable columns, no breaking migration) if needed.

Administrator-only mutation (`LAB_TEMPLATE_MANAGE_ROLES`), broadly readable (`LAB_VIEW_ROLES`) since both the doctor-facing order-creation flow and the Lab Dashboard need to read the catalog. `ClinicalOrdersService`/`LaboratoryService.create_from_order` best-effort matches a new order's free-text item name against an active template's `test_name` (case-insensitive exact match) to auto-link pricing/parameters — if no match, the lab order still gets created with a free-text `test_type` and no template link, and results can be entered ad hoc.

### `laboratory_orders`

`order_id` (unique FK → `orders.id`), `branch_id`, `visit_id`, `patient_id`, `doctor_id`, `template_id` (nullable FK), `test_type` (denormalized from the matched template or the order's free-text item name), `status` (own enum `laboratory_order_status`: `Requested`/`Collected`/`Processing`/`Completed`/`Released`/`Cancelled` — distinct from Phase 9's shared `order_status`, which has no `Released`), `collected_at`/`collected_by`, `processing_started_at`, `completed_at`, `released_at`/`released_by`, and `invoice_item_id` (nullable FK → `invoice_items.id` — the billing idempotency key, see below).

**Status transitions**: `Requested → Collected → Processing → Completed → Released`, or `→ Cancelled` from any non-terminal state (`LABORATORY_ORDER_STATUS_TRANSITIONS` in `models/laboratory_order.py`). Entering results is allowed while `Collected`/`Processing`/`Completed` (a `Completed` order's results can be corrected before release); the first time results are entered, status advances to `Completed` and the billing sync fires.

**Order.status sync (the Phase 7/8/9 lesson, applied a fourth time):** every laboratory-workflow transition also mirrors onto the underlying Phase 9 `orders.status` via `LaboratoryService._sync_order_status`, mapped `Requested→Requested`, `Collected→Collected`, `Processing→Processing`, `Completed`/`Released→Completed`, `Cancelled→Cancelled` (Phase 9's shared enum has no `Released`, so both map to `Completed`). Without this, the Consultation page's Orders tab — which reads `OrderRead.status` from the completely separate `orders` table — would show every lab order stuck at `Requested` forever regardless of how far it progressed in the lab workflow; this was caught live while testing (see `docs/TESTING.md`), fixed, and is covered by `test_full_lifecycle_with_timeline_events`'s explicit `orders` re-fetch assertion.

### `laboratory_results`

One row per result parameter (`laboratory_order_id` FK, `parameter_name`, `result_type` Numeric/Text, `numeric_value`/`text_value`, `normal_range`, `units`, `interpretation` Normal/Low/High/Abnormal, `remarks`, `entered_by`/`entered_at`) — a CBC order produces ~10 rows. `LaboratoryRepository.upsert_results` uses replace-all semantics per submission (delete existing rows for the order, insert the new set) rather than a per-parameter merge, matching how the Result Entry UI pre-populates all rows and lets the user edit/add/remove before a single save.

### `laboratory_attachments`

Reuses the exact presigned-URL-stub pattern from Phase 8's `consultation_attachments` (`attachment_type` PDFReport/Image/ScannedResult, `file_name`, `file_url`, `file_size_bytes`, `uploaded_by`), kept as its own parallel table (per spec's explicit `LaboratoryAttachment` table listing) rather than generalizing the consultation-scoped table, since the two have different owning entities and lifecycles.

### Billing integration (idempotent)

When a laboratory order's results are first entered (status → `Completed`) and it has a template with `default_price > 0`, `LaboratoryService._sync_billing` calls `InvoiceService.create_draft_invoice_for_consultation` (the same get-or-create entry point Consultation-completion already uses) to ensure the visit has an invoice, then adds an `InvoiceItemType.LABORATORY` line item priced from the template.

**Idempotency key**: `laboratory_orders.invoice_item_id`. If already set (a prior sync already created the line), the existing item is `update`d in place instead of adding a new one — covers the "results resubmitted while still `Completed`, before `Released`" case. **Bug found and fixed during live verification**: the newly-added item was originally identified by matching `description == test_type`, which silently picked up a *different* laboratory order's item when two orders shared the same test name (e.g. two CBCs on one visit) — both orders' `invoice_item_id` ended up pointing at the first order's line, corrupting both orders' idempotency keys. Fixed by identifying the new item via an explicit "item ids before the add" diff (a fresh `session.refresh(invoice, ["items"])` immediately before calling `add_item`, not a reused/possibly-stale relationship collection) rather than matching on `description`. Covered by `test_two_orders_same_test_name_get_distinct_invoice_items` and `test_billing_sync_idempotent_on_resubmit`; verified live via curl and confirmed in the real dev database (`invoice_items` table) before and after the fix.

### Visit timeline events

`VisitTimelineEventType` gained `LabSpecimenCollected`, `LabProcessingStarted`, `LabResultsEntered`, `LabResultsReleased`, `LabOrderCancelled`. **"Ordered" is intentionally not re-recorded** when a `laboratory_orders` row attaches to a fresh `Order` — Phase 9's `OrderCreated` event already covers the doctor's initial creation, and re-emitting a near-duplicate the instant the workflow record attaches (same request) would just double the timeline for no new information. Verified via `test_full_lifecycle_with_timeline_events`'s explicit `events.count("OrderCreated") == 1` assertion.

### Role gating

`LAB_VIEW_ROLES` (Owner/Administrator/Laboratory/Doctor/Receptionist) — broad, matching every other clinical module's "Reception: view-only" pattern. `LAB_MANAGE_ROLES` (Owner/Administrator/Laboratory) — collect/process/enter-results/release/cancel/attachments; **Doctor is explicitly excluded** from this set, since per spec Doctor only creates orders (unchanged Phase 9 endpoint) and Laboratory personnel own the collection→release workflow. `LAB_TEMPLATE_MANAGE_ROLES` (Owner/Administrator only) for template mutation.

### Legacy migration readiness

`laboratory_orders`, `laboratory_results`, `laboratory_attachments`, `laboratory_templates`, and `laboratory_template_parameters` all carry the legacy-migration mixin fields, consistent with every first-class transactional table added since Phase 5.

---

## Phase 11: Appointment Management

Migration `0012_appointment_management` (`down_revision = 0011_laboratory_management`). Adds six new tables plus extends `doctor_schedules` in place.

### `doctor_schedules` extended, not duplicated

Phase 4 shipped `doctor_schedules` as architecture-only (day-of-week/start/end/is_active, explicitly documented as having "no notion of appointment slots or bookings"). Rather than creating a parallel `appointment_doctor_schedules` table, this phase adds columns **additively** to the existing table: `lunch_break_start`/`lunch_break_end` (nullable Time), `slot_duration_minutes` (Integer, default 15), `max_patients_per_day` (nullable Integer), `is_recurring` (Boolean, default true), `effective_from`/`effective_to` (nullable Date, for a non-recurring date-bounded override layered on top of the recurring weekly row), plus the legacy-migration mixin fields (the original table predates that mixin). This keeps one source of truth for "what hours does this doctor work" instead of two tables that could drift.

### `doctor_schedule_blocks`

Single-date vacation/blocked days per doctor (`block_date`, `block_type` enum `Vacation`/`Blocked`, `reason`), unique on `(clinic_id, doctor_id, block_date)`. Deliberately a separate table from `doctor_schedules` rather than a `block_type` column folded into it, because a block is a one-off exception to the recurring weekly pattern, not a schedule row itself — folding it in would require nullable day-of-week/start/end semantics that don't make sense for a single blocked date.

### `appointments`

`appointment_number` (`APT-YYYYMMDD-000001`, via `AppointmentNumberGenerator`, mirrors `OrderNumberGenerator`'s `system_settings`-backed JSONB counter pattern), `patient_id`/`doctor_id` (required), `department_id`/`service_id` (nullable — a receptionist can book against just a doctor and fill in department/service later, though **check-in requires both to be set**, since they're required inputs to `QueueService.create_queue()`), `appointment_type` enum (NewConsultation/FollowUp/AnnualPhysical/Teleconsultation/Vaccination/Procedure/Laboratory/Custom), `appointment_date`/`start_time`/`end_time` (end_time derived server-side from the doctor's `slot_duration_minutes` at booking time and stored for query convenience), `status` (nine-value enum: Booked/Confirmed/CheckedIn/Waiting/InConsultation/Completed/Cancelled/NoShow/Rescheduled), `queue_id`/`visit_id` (nullable, set on check-in).

**Double-booking prevention**: a Postgres partial unique index `uq_appointments_doctor_slot_active` on `(clinic_id, doctor_id, appointment_date, start_time)` `WHERE is_deleted = false AND status NOT IN ('Cancelled', 'Rescheduled', 'NoShow')` — created directly in the migration (not expressible as a plain `UniqueConstraint`) so a cancelled/rescheduled/no-show appointment doesn't permanently block that slot for a future booking.

### Time Slot Engine: `TimeSlot` is a computed DTO, not a table

The spec lists `TimeSlot` as a table name, but this phase implements it as `schemas/appointment.py::TimeSlotOut`, computed on demand by `services/time_slot_service.py::get_available_slots` from `DoctorSchedule` (grid-walking `start_time` → `end_time` in `slot_duration_minutes` steps) minus lunch break minus existing non-cancelled `appointments.start_time` values minus `Holiday` (Phase 4, reused) minus `DoctorScheduleBlock`, and never persisted. **Rationale**: a persisted slot table goes stale the instant any of its four source signals changes (a schedule edit, a new booking, a same-day block, a holiday added) — every write path would need to remember to invalidate/regenerate rows, which is exactly the class of cross-entity sync bug documented repeatedly in `docs/TESTING.md` across Phases 7-10. No feature in this phase (e.g. a slot-hold/reservation) requires a durable slot row; if the Waitlist feature later needs to reference a *specific* offered slot, `waitlist_entries.offered_slot_date`/`offered_slot_start_time` already cover that without a full `TimeSlot` table.

### Check-in → Queue → Visit integration (the Phase 7/8/9/10 lesson, addressed by design this time)

`AppointmentService.check_in_appointment` does **not** reimplement queue-ticket or visit creation. It builds a `QueueCreate` payload from the appointment's patient/branch/department/doctor/service and calls the existing `QueueService.create_queue()` — the exact Phase 5/6 method that already atomically creates a linked `Visit` in the same transaction. The only change to `QueueService.create_queue()` is one additive, backward-compatible keyword argument, `visit_type: VisitType = VisitType.WALK_IN`, passed through to `VisitService.create_visit_for_queue`; every existing caller (Reception's walk-in New Queue dialog) is unaffected, while `check_in_appointment` passes `visit_type=VisitType.APPOINTMENT` so the resulting Visit is correctly tagged. `appointment.queue_id`/`visit_id` are then just FKs set from whatever `create_queue()` returned. `VisitTimelineEventType` gained one new value, `AppointmentCheckedIn`, recorded onto the same visit-scoped timeline (mirrors how `Queued`/`CheckedIn` already work for walk-ins). This was verified live in the browser: Appointments page → Check In → the Reception Queue screen immediately shows the new ticket and the Visits list immediately shows the new linked Visit tagged `Appointment` (see `docs/TESTING.md`).

### `appointment_history`

Domain-specific audit trail (`action` enum Created/Confirmed/Rescheduled/Cancelled/CheckedIn/Completed/NoShow, `from_value`/`to_value` free text e.g. old/new date-time on reschedule, `changed_by`/`changed_at`/`note`), mirroring `queue_status_history`'s relationship to the generic `audit_logs` table — every meaningful action writes to both, exactly like Phase 5/6's pattern.

### Reschedule: two rows, not an in-place date update

`AppointmentService.reschedule_appointment` marks the original row `Rescheduled` (a terminal status) and creates a **new** `Booked` row for the new date/time (with a fresh `appointment_number`), rather than mutating the existing row's `appointment_date`/`start_time` in place. This keeps the audit trail unambiguous — `appointment_history` on the *old* row's id records the old→new transition, and the new row's own `Created` history entry cross-references "Rescheduled from {old_number}" — and matches how a receptionist actually thinks about it ("this slot is now free, that's a new booking").

### `appointment_reminders` (architecture-only) and `waitlist_entries`

`appointment_reminders`: `channel` (Email/SMS/Push/WhatsApp), `status` (Pending/Sent/Failed), `scheduled_for`/`sent_at` — schema only, no sending logic; a future notification-worker phase would poll `status=Pending` rows. `waitlist_entries`: `patient_id`/`doctor_id`/`branch_id`/`date_from`/`date_to`, `status` (Waiting/Offered/Booked/Expired/Cancelled), `offered_slot_date`/`offered_slot_start_time`. `WaitlistService.offer_next_slot` runs after every successful cancellation and flips the oldest matching `Waiting` entry to `Offered` with the freed slot recorded — a real, queryable state change (verified live: cancelling a booked slot immediately makes `GET /doctors/{id}/available-slots` report it available again), even though no notification is actually sent in this phase.

### Role gating

`APPOINTMENT_VIEW_ROLES` (Owner/Administrator/Receptionist/Doctor/Cashier/Laboratory) — broad, since appointment context is relevant to reception, the doctor, billing, and lab scheduling alike. `APPOINTMENT_MANAGE_ROLES` (Owner/Administrator/Receptionist) — create/edit/reschedule/cancel/check-in. `APPOINTMENT_COMPLETE_ROLES` (Owner/Administrator/Doctor) — complete/no-show. `APPOINTMENT_SCHEDULE_MANAGE_ROLES` (Owner/Administrator only) — doctor working-hours/blocks mutation, matching Phase 10's template-administration pattern.

### Legacy migration readiness

`appointments`, `doctor_schedule_blocks`, `appointment_reminders`, `appointment_notes`, `appointment_history`, and the extended `doctor_schedules` all carry the legacy-migration mixin fields.

---

### Environment

`alembic/env.py` reads `DATABASE_URL` from the backend's environment/config (`app/core/config.py`) so the same migrations run identically against local Docker Postgres, Supabase staging, and Supabase production — only the connection string changes.

---

## Phase 12: Owner Dashboard & Reports

**No new tables and no migration** — `alembic heads`/`alembic current` remain at `0012_appointment_management` after this phase. Per the spec's explicit "Do not duplicate data. Generate reports directly from operational tables" instruction, every metric is a real SQL `COUNT`/`SUM`/`AVG`/`GROUP BY` aggregation query against existing tables, executed at request time. Report-generation events reuse the existing `audit_logs` table (`action = "analytics.report_generated.<report>"`, `metadata_json` holding the applied filters) rather than a new `report_generation_log` table — the generic audit log already carries clinic/user/action/entity/metadata, which is exactly what "report type + filters + generated_by" needs.

Which existing repository owns each metric's query (reused, not duplicated):

| Metric / Report | Source table(s) | Repository method |
|---|---|---|
| Collected Revenue Today, Outstanding Balance, Pending Payments | `invoices`, `payments` | `InvoiceRepository.sum_todays_revenue`/`count_pending_payments`/`sum_outstanding_balance` (pre-existing, Phase 9) |
| Revenue by Doctor/Branch/Service/Payment Method, daily revenue series, discount summary, outstanding invoices | `invoices`, `invoice_items`, `payments`, `discounts` | `InvoiceRepository.revenue_by_*`/`daily_revenue_series`/`discount_summary_in_range`/`outstanding_invoices_in_range` (new, Phase 12) |
| Patients Today, Completed/Cancelled/No-Show Visits, Doctors On Duty, Patient Census, Returning Patients, per-doctor visit stats | `visits` | `VisitRepository.status_counts_in_range`/`visit_type_counts_in_range`/`distinct_doctors_with_activity`/`daily_census_series`/`monthly_census_series`/`returning_patient_count`/`doctor_visit_stats`/`avg_consultation_seconds_for_doctor` (new, Phase 12) |
| New Patients, Age/Gender Distribution | `patients` | `PatientRepository.count_created_in_range`/`age_distribution`/`gender_distribution` (new, Phase 12) |
| Average Waiting Time, Longest Wait, Queue Volume by Hour, Completed/Cancelled Queue Count | `queues` | `QueueRepository.waiting_time_stats`/`volume_by_hour`/`status_counts_in_range` (new, Phase 12) |
| Average Consultation Time (dashboard, all-doctors) | `consultation_sessions` | `DoctorWorkspaceRepository.avg_duration_seconds` (pre-existing, Phase 7, called with `doctor_id=None`) |
| Laboratory Orders Today/Completed/Pending, Turnaround Time, Top Tests | `laboratory_orders` | `LaboratoryRepository.count_created_in_range`/`report_counts_in_range`/`avg_turnaround_seconds`/`top_requested_tests`/`daily_volume_series` (new, Phase 12) |
| Prescriptions Issued, Orders by Category | `prescriptions`, `orders` | `ClinicalOrdersRepository.count_prescriptions_in_range`/`count_orders_by_category_in_range` (new, Phase 12) |
| Appointment Bookings/Completed/Cancelled/No-Show/Rescheduled, Doctor Utilization | `appointments`, `appointment_history` | `AppointmentRepository.status_counts_in_range`/`rescheduled_count_in_range`/`doctor_utilization_in_range`/`daily_booking_series` (new, Phase 12) |
| Real-time Activity Feed | `visit_timeline_events`, `queue_status_history`, `audit_logs` | `VisitRepository.recent_timeline_events` + `AnalyticsRepository.recent_audit_logs`/`recent_queue_status_changes` (merged and sorted in `AnalyticsService.get_activity_feed`) |
| Owner Alerts (High Queue Volume, Long Waiting Time, Outstanding Payments) | `queues`, `invoices` | `AnalyticsRepository.current_waiting_count`/`longest_current_wait_seconds` + `InvoiceRepository.outstanding_invoices_in_range` |

**Doctor Utilization simplification**: rather than resolving full per-day slot capacity from `DoctorSchedule` for every date in an arbitrary report range (heavy for a report endpoint), `AppointmentRepository.doctor_utilization_in_range` reports `completed / booked` per doctor. `TimeSlotService` (Phase 11) remains the source of truth for live per-day slot availability used at actual booking time.

**Rooms In Use**: intentionally `null` in the dashboard response — `consultation_rooms` exists as master data only; neither `visits` nor `consultations` currently carry a `consultation_room_id` assignment, so there is nothing to aggregate yet. A future phase that adds room assignment to the visit/consultation flow should wire this up; the dashboard schema field and frontend card already exist and are ready to receive a real value.

**System Errors / Failed Backups** (spec's Owner Alerts categories): explicitly out of scope — no infrastructure/monitoring layer exists yet to check against, so `AnalyticsService.get_alerts` never emits these categories rather than faking a static "OK" status.

---

## Phase 13: Live TV Queue Display

Two new tables, migration `0013_tv_queue_display` (descends linearly from `0012_appointment_management`):

- **`tv_display_configs`**: one row per configured display. `branch_id`/`department_id`/`doctor_id` are all nullable and each narrows scope further (clinic-wide → branch → department → doctor); a "Waiting Area TV" is simply a branch-scoped config with no department/doctor. `is_public` (bool) + `public_slug` (unique, nullable, a 192-bit `secrets.token_urlsafe(24)` value) control the no-auth-required public URL — see the security model below. Visual/behavioral settings (`theme`, `font_size`, `animation_speed`, `queue_size`, `refresh_interval_seconds`, `logo_url`, `primary_color`, `secondary_color`) are plain columns, no JSONB blob, so they're queryable/validatable like every other config table in this project. `tts_enabled`/`tts_template` are architecture-only (see Text-to-Speech below).
- **`tv_announcements`**: scrolling-ticker content. `tv_display_config_id` is nullable — `NULL` means "shows on every display for this clinic," a non-null value scopes it to one display. Typed (`announcement_type`: Welcome/HealthTip/Promotion/Emergency), orderable (`display_order`), and optionally date-range-scheduled (`starts_at`/`ends_at`, both nullable = always active while `is_active`).

Both tables get the full `LegacyMixin`/`TenantMixin`/`SoftDeleteMixin`/`TimestampMixin` stack per this project's standing convention, even though display-config/announcement rows are the least likely candidate yet for a legacy bulk import — kept for consistency rather than because a concrete migration use case exists; the columns are additive and nullable, so this costs nothing.

**No new/extended tables for the actual queue snapshot** — `TvDisplayService._build_display_data` queries the existing `queues` table directly (same `ACTIVE_QUEUE_STATUSES` constant `QueueService`/`QueueRepository` already use), joins `patients`/`doctors`/`branches` for display fields, and does its own privacy-safe initials derivation server-side (`_initials()` — first letter of first name + first letter of last name, uppercased, never the full name). No new queue/visit columns were needed.

**Post-RC1 (Multi-Department/Multi-Doctor TV Queue Display)**: `_build_display_data` now also `selectinload`s `Queue.department` and the `TvDisplayNowServing`/`TvDisplayWaitingEntry` response schemas gained `department_id`/`department_name` (see `docs/API.md`) — no schema/table change, `Queue.department_id` already existed. Confirmed live that a `TvDisplayConfig` with `branch_id`/`department_id`/`doctor_id` all `NULL` already returns queues across the whole clinic (every scope filter in `_build_display_data` is conditionally appended only `if config.X is not None`) — this is what a genuinely clinic-wide, multi-department TV display uses; no new config concept or table was needed.

**Known gap, documented rather than worked around silently**: neither `queues` nor `visits` has an FK to `consultation_rooms` (Phase 4's `ConsultationRoom` table is master data only, same gap noted in Phase 12's "Rooms In Use" section above), so `TvDisplayNowServing.room_name` cannot be inferred from a real room assignment on the Queue/Visit/Consultation flow. **Post-RC1 (room-based TV announcements)** partially closes this gap without that FK link: `queue_settings` gained a nullable `room_label` column (migration `0026_queue_setting_room_label`), reusing the same doctor/department/branch override row already used for queue prefixes. When an override row has a `room_label` configured, `TvDisplayService._build_display_data` resolves it in-memory (`_resolve_room_label`, same "narrowest scope wins" chain as prefix resolution) and both the TV Display and the spoken announcement (`queue-announcer.ts::buildAnnouncementText`) say the room instead of the doctor/department name. `room_name` is `null` only when no override row for that destination has a room configured — no longer *always* null as originally shipped in Phase 13.

**Public-slug security model**: `public_slug` is the *only* credential the public HTTP endpoint (`GET /public/tv-display/{public_slug}`) and the public WebSocket connection require — there is no clinic_id parameter anywhere in the public request path, so the slug itself is what resolves (and thereby scopes) the request to exactly one clinic/branch/department/doctor. `TvDisplayConfigRepository.get_by_public_slug` filters to `is_public=True, is_active=True, is_deleted=False` in the same query that looks up the slug, so a slug for a disabled/private/deleted display never resolves — no separate "is this slug allowed" check is needed after the lookup succeeds. This is safe to expose fully unauthenticated because the response never contains more than: queue number, patient initials, doctor name, room (currently always null, see above), clinic/branch name, and announcement text — never a full patient name, contact info, date of birth, or any clinical data. Revoking a display is a single soft-delete or `is_active=false` update; nothing else references the slug.

**WebSocket authentication for public displays** (the most architecturally significant decision in this phase — see `docs/API.md`'s WebSocket section for the full writeup): `ws_queues.py`'s `/ws/queues/{clinic_id}` handshake, previously JWT-only, now accepts the `token` query param as *either* a JWT (unchanged behavior, `clinic_id` claim must match the path segment) *or* a TV display's `public_slug` (new) — resolved via the same `TvDisplayConfigRepository.get_by_public_slug` the HTTP endpoint uses, and the connection is scoped to *that config's own* `clinic_id`, ignoring the path segment's value entirely for a slug-authenticated connection (trusting the resolved value, not the caller-supplied path, prevents a slug being replayed against an arbitrary `clinic_id` in the URL). This was chosen over minting short-lived anonymous JWTs for kiosk displays because it reuses the exact secret-token-as-credential model the public HTTP endpoint already has, needs no new token-issuance/rotation machinery, and "revoke a display's access" is already just deactivating its `TvDisplayConfig` row.

**Post-RC1 (short TV display URL)**: `tv_display_configs` gained a nullable, unique `short_code` (migration `0028_tv_display_short_code`, `VARCHAR(32)`) — an admin-chosen, short human-typeable alias for the same row `public_slug` already identifies, e.g. `"canora"`, so a Smart TV remote can type `/tv/canora` instead of the 32-character `public_slug`. This was requested specifically because a Smart TV's on-screen keyboard/remote makes typing a 32-character random token impractical, while the LAN deployment target (Windows desktop CMS server + Smart TV on the same clinic router, no `localhost`) has no other realistic way to shorten the URL (no DNS/reverse-proxy layer assumed to exist).

- **Not a second credential.** `TvDisplayConfigRepository.get_by_short_code` applies the identical `is_public=True, is_active=True, is_deleted=False` filters as `get_by_public_slug`, and `TvDisplayService.get_public_display_data` tries a `public_slug` match first, falling back to `short_code` only on a miss — a short code is purely an additional lookup key onto the same row and the same access-control gate, never a separate/weaker one. Disabling or privatizing a display via the existing `is_active`/`is_public` toggles stops the short code from resolving too, with zero new code paths to keep in sync.
- **The long `public_slug` URL is completely unaffected.** Every pre-existing display (no `short_code` set) keeps resolving exactly as before this migration; `short_code` is opt-in and additive only.
- **The WebSocket auth path was not touched at all.** `ws_queues.py`'s `_resolve_clinic_id_from_public_slug` still only ever accepts the real `public_slug`, never a short code. The public HTTP response's `ws_auth_slug` field always carries the row's real `public_slug` regardless of which identifier (long slug or short code) resolved it, and the frontend (`use-tv-display-realtime.ts::resolveWsToken`) uses that resolved value — not whatever string was in the browser's URL bar — to open the WebSocket connection. This means even a browser that reached the display via a guessed/enumerated short code cannot use that short code itself as a live WS credential; it would need the real slug, which it only obtains by *also* successfully calling the (now rate-limited) HTTP endpoint first.
- **Disclosed security tradeoff**: a short code is inherently far more guessable than the 192-bit `public_slug` this feature was built to keep unguessable-by-design. This is intentional and mitigated, not accidental: `short_code` is never auto-generated (an admin must deliberately choose one, the same opt-in posture as `is_public` itself), and `GET /public/tv-display/{public_slug}` is now rate-limited per client IP (`core/rate_limit.py::rate_limit_tv_public`, `RATE_LIMIT_TV_PUBLIC_MAX_ATTEMPTS`/`_WINDOW_SECONDS` settings, default 60 requests/60s — generous enough for a real TV's normal 30s-poll-plus-WS-reconnect traffic, but throttles brute-force short-code enumeration). Given the primary deployment target described for this feature is a single-clinic, LAN-only on-prem install (not public internet, not multi-tenant SaaS), and the data behind the endpoint is already documented above as safe to expose fully unauthenticated, this tradeoff was accepted rather than declined outright — but it is a real, disclosed reduction in obscurity-based protection for any display an admin opts into a short code, not a hidden one.

---

## Post-RC1: 50/50 Queue + Information/Advertisement Panel

One new table, migration `0027_tv_info_content` (descends linearly from `0026_queue_setting_room_label`):

- **`tv_info_content`**: rotating content for the new right-half Information/Advertisement Panel on the TV Display. Deliberately a **separate** table from `tv_announcements` rather than an extension of it — the two have materially different shapes (this needs a `title`+`body` split, a per-item `duration_seconds` rotation interval, and a content-type taxonomy matching real clinic content categories — pricing, doctor info, health tips, preventive reminders, announcements, promotions, motivational messages — none of which map cleanly onto `tv_announcements`'s single `message` field + Welcome/HealthTip/Promotion/Emergency types) and different display mechanics (rotating, one-at-a-time right-panel content vs. a continuously-scrolling bottom ticker). See `app/models/tv_info_content.py`'s module docstring for the full rationale.
  - **Clinic-wide only** — no `tv_display_config_id` column (unlike `tv_announcements`'s optional per-display scoping), since every TV Display Post-RC1 renders the identical 50/50 queue+info layout; there is currently no per-display variation to scope against.
  - `content_type` (`tv_info_content_type` enum: `ServicePricing`/`DoctorInfo`/`HealthTip`/`PreventiveReminder`/`Announcement`/`Promotion`/`Motivational`), `duration_seconds` (default 10, admin-configurable per item), `display_order`, `is_active` — same shape/semantics as `tv_announcements`'s equivalent columns.
  - `image_url` (nullable `String(500)`): a relative path into a real, working local-disk image upload pipeline (added after initial ship, per explicit follow-up request) — `POST /tv-info-content/{id}/image` (multipart, `Owner`/`Administrator` only) validates the actual uploaded bytes' extension (`.jpg`/`.jpeg`/`.png`/`.webp`) and size (5 MB max, reusing `app/core/upload_validation.py`'s `IMAGE_EXTENSIONS`/`MAX_IMAGE_SIZE_BYTES` constants), writes to `backend/var/tv_info_content_images/{clinic_id}/{content_id}-{random_suffix}.{ext}`, and stores the relative serving path. This is a deliberate exception to this codebase's dominant presigned-URL-stub upload pattern (see `app/core/upload_validation.py`'s docstring — every other "photo"/"attachment" field, e.g. `Clinic.logo_url`, `Doctor.photo_url`, `ConsultationAttachment.file_url`, mints a fake `stub.supabase.local` URL and never actually receives file bytes): the TV Display has a hard "works fully offline, no cloud dependency" requirement, so a Supabase-presigned-URL flow would not actually function for it. The closest precedent for *real* byte-relaying upload in this codebase is `migration.py`'s `POST /migration/batches/{id}/upload` (same `var/`-relative-to-backend-root directory convention, same pattern of validating actual bytes rather than just client-declared metadata) — followed here rather than inventing a third pattern.
  - Files are served back out via a `StaticFiles` mount at `/media/tv-info-content` (see `app/main.py`), **unauthenticated** — same security posture as the public TV display endpoint itself (these are clinic-facing marketing/informational images meant to be shown on an unauthenticated public TV, never sensitive data). Re-uploading an item's image deletes the previous file (glob-matched by `{content_id}-*` in that clinic's directory) before writing the new one, so switching file extensions on re-upload doesn't leave an orphan; `DELETE /tv-info-content/{id}/image` removes the file and clears the column back to `null`. `backend/var/` is gitignored (runtime-generated, not source).
  - Gets the full `LegacyMixin`/`TenantMixin`/`SoftDeleteMixin`/`TimestampMixin` stack, matching this project's standing convention for every other config-style table (see Phase 13 above for the same reasoning).

No queue/visit table was touched by this feature — the left-half queue display continues to read `TvDisplayService._build_display_data`'s existing `queues` query unchanged; only a new `info_content` list was added alongside it in the `TvDisplayData` response.

---

## Phase 14: Legacy Migration Wizard

Five new tables, migration `0014_legacy_migration_wizard` (descends linearly from `0013_tv_queue_display`), plus a backfill of `LegacyMixin` onto four tables an audit found missing it.

- **`migration_batches`**: one row per migration run. `source_type` (ENUM `SQLite`/`Access`/`SQLServer`/`MySQL`/`PostgreSQL`/`CSV`/`Excel`), `source_description` (free text — e.g. filename or legacy system label, **never raw credentials**), `status` (ENUM `Draft`→`Connected`→`Analyzed`→`Previewed`→`Validated`→`Importing`→`Completed`/`Failed`/`PartiallyCompleted`/`Cancelled`), `started_at`/`completed_at`, `started_by` (FK `users`), `total_records_found`/`total_records_imported`/`total_duplicates`/`total_warnings`/`total_errors` (running counters updated as entities complete), `current_entity` (which of the 17 entity types is in flight — resumability signal), `uploaded_file_path` (a JSON manifest of on-disk upload paths, never exposed via the API — see `docs/API.md`).
- **`migration_entity_progress`**: one row per (batch, entity_type). `status` (ENUM `Pending`/`InProgress`/`Completed`/`Failed`/`Skipped`), `records_found`/`records_imported`/`records_skipped`/`records_failed`, and — the key resumability field — `last_processed_offset`: a resumed or retried import re-reads from this offset instead of restarting the entity from zero. Unique on `(migration_batch_id, entity_type)`.
- **`migration_field_mappings`**: one row per (batch, entity_type, source_field). `destination_field` (nullable = ignored), `transform_type` (ENUM `None`/`Rename`/`DateFormat`/`PhoneFormat`/`Trim`/`Custom` — DateFormat/PhoneFormat/Trim are real, Rename is implicit in the mapping itself, Custom is an architecture placeholder), `transform_config` (JSONB, e.g. `{"source_format": "%Y-%m-%d"}` for DateFormat), `is_ignored`.
- **`migration_validation_issues`**: one row per flagged source row. `entity_type`, `source_row_identifier` (the source row's own ID or 1-based row number), `issue_type` (ENUM `RequiredFieldMissing`/`DuplicatePatient`/`DuplicateDoctor`/`BrokenRelationship`/`MissingForeignKey`/`InvalidDate`/`InvalidPhone`/`InvalidEmail`/`DuplicateInvoiceNumber`/`DuplicateVisitNumber`), `severity` (`Warning`/`Error`), `message`, `resolution` (ENUM `Unresolved`/`Skip`/`Merge`/`Overwrite`/`CreateNew`, set via `PATCH .../issues/{id}/resolve`), `resolved_by`/`resolved_at`.
- **`migration_logs`**: the detailed operational log, distinct from `migration_batches`' summary counters — one row per lifecycle event / entity-completion / error, `log_level` (`Info`/`Warning`/`Error`), `entity_type` (nullable — batch-level events have none), `message`, `details` (JSONB).

**Legacy-mixin-on-meta-tables decision**: none of these five tables carry `LegacyMixin`. They are the migration tracking system itself, not clinical/business data migrated *from* a legacy system, so `legacy_id`/`migration_batch_id` etc. would be meaningless on them (documented in the `0014` migration's own docstring). They do carry `TenantMixin` (clinic-scoped) and `created_at`/`updated_at` (or just `created_at` for the two append-only tables, `migration_validation_issues`/`migration_logs`), consistent with the rest of the project.

**Idempotency decision**: entity tables already have `legacy_id` (the source row's own primary key/identifier) and `migration_batch_id` from `LegacyMixin`. The import engine looks up `WHERE clinic_id = ? AND legacy_id = ? AND migration_batch_id = ?` on the destination table before every insert; a match means the row was already imported in a prior run of this same batch and is skipped rather than duplicated. **No separate `sync_hash` column was added to any entity table** — this pair is sufficient, and was proven live and in an automated test by re-running an identical import twice (and once with the resume offset manually forced back to 0, so every row is re-evaluated from scratch) and confirming zero new rows both times.

**Audit finding, fixed in this migration**: this phase's first task was to confirm every entity table already had `LegacyMixin` (as every prior phase's spec required). Four tables did not: `branches`, `departments`, `doctors`, `services` (the `ClinicService` model). `0014_legacy_migration_wizard` backfills the standard six columns (`legacy_id`, `legacy_meta`, `legacy_created_at`, `legacy_updated_at`, `migration_batch_id`, `migration_source`, `imported_at`) onto all four, additively and nullable, matching the exact pattern Phase 5's `0005_reception_queue` used for the original four tables. The corresponding ORM model classes were updated to include `LegacyMixin` in their base-class list.

**Source adapter architecture**: `services/migration/source_adapters/base.py` defines an abstract `SourceAdapter` (`connect()`/`analyze_schema()`/`read_table(name, batch_size, offset)`/`close()`); `registry.py` maps `MigrationSourceType` → adapter class. `csv_adapter.py` (stdlib `csv`) and `excel_adapter.py` (`openpyxl`) are fully implemented — one uploaded file per entity type for CSV, one sheet per entity type (by sheet name) for Excel. `sqlite_adapter.py`/`access_adapter.py`/`sqlserver_adapter.py`/`mysql_adapter.py`/`postgres_adapter.py` implement the same interface but raise `NotImplementedError` pointing at the CSV/Excel path — this is a deliberate scope decision (see `docs/MIGRATION.md`), not an oversight: no specific legacy client database technology has been identified yet, and CSV/Excel can represent an export from virtually any legacy desktop system.

**17-step entity import order** (`MIGRATION_ENTITY_ORDER` in `models/migration_batch.py`): Clinic → Branches → Departments → Doctors → Users → Patients → Services → Visits → QueueHistory → Consultations → Diagnoses → Prescriptions → Laboratory → Billing → Payments → Attachments → AuditLogs — dependents always after what they reference. **Only Patients and Doctors write to a real destination table in this phase** (via `PatientService.create_patient` and a direct `Doctor` create using the existing `DoctorCodeGenerator`, both with legacy fields populated) — the other 15 entity types get full schema-analysis/mapping/validation support identically, but `import_entity()` marks them `Skipped` with an explanatory `migration_logs` entry rather than writing partially-modeled data for entity graphs with cross-cutting FK integrity this phase didn't have room to responsibly hand-verify end to end.

---

## Phase 15: SaaS Administration Portal

Nine new tables, migration `0015_saas_administration` (descends linearly from `0014_legacy_migration_wizard`), plus additive columns on the pre-existing `clinics` and `subscriptions` tables. This phase's tables are platform-meta tables, not clinic-owned business data, so most of the usual mixins do not apply the way they do elsewhere in the schema:

- **`platform_admin_users`**: `id`, `email`/`username` (unique), `hashed_password`, `full_name`, `role` (ENUM `PlatformAdministrator`/`SupportEngineer`/`ImplementationTeam`/`Auditor`), `is_active`, `last_login_at`. **Deliberately has no `clinic_id` and does not use `TenantMixin`** — a platform admin does not belong to any single tenant; that is the entire point of this table's existence as a structurally separate model from `users`. See `docs/ARCHITECTURE.md` §7 for the full auth-architecture rationale.
- **`tenant_feature_flags`**: `clinic_id` (FK `clinics`), `feature_key` (one of 8 known keys — see `app/models/tenant_feature_flag.py`), `is_enabled`, `updated_by` (FK `platform_admin_users`). Unique on `(clinic_id, feature_key)`.
- **`platform_audit_logs`**: `actor_id` (FK `platform_admin_users`, nullable on delete), `action`, `entity_type`, `entity_id`, `clinic_id` (nullable — which tenant was affected, if any), `log_metadata` (JSONB), `created_at`. Distinct from the existing per-clinic `audit_logs` table (Phase 0) since platform actions are not scoped to any single clinic's own audit trail — a suspend action, for instance, needs to be visible platform-wide, not buried in the suspended clinic's own (now-inaccessible-to-its-users) log.
- **`platform_sessions`**: `platform_admin_user_id` (FK), `token_hash`, `ip_address`/`user_agent`/`device_label`, `last_seen_at`/`expires_at`, `terminated_at`/`terminated_by`. Tracks a platform admin's OWN login sessions (their refresh-token equivalent). **Clinic-user sessions/force-logout continue to use the existing Phase 2 `refresh_tokens` table unmodified** — `platform_sessions` is not a replacement for it, just the platform-admin-portal equivalent.
- **`background_jobs`**: `job_type`, `status` (ENUM `Scheduled`/`Running`/`Completed`/`Failed`/`Retrying`), `started_at`/`completed_at`, `error_message`, `retry_count`, `clinic_id` (nullable), `reference_id`. No real job-queue infrastructure exists in this project — this table is an architecture-level monitoring surface, and the `GET /platform-admin/background-jobs` endpoint surfaces real rows from this table alongside the one genuine existing background-style task (Phase 14's `migration_batches`, mapped into the same response shape) rather than inventing a fake job system.
- **`platform_config`**: `config_key` (unique), `config_value` (JSONB), `updated_by`. A real key/value settings store; deliberately NOT wired to any actual email/SMS/AI/storage provider integration in this phase.
- **`api_keys`** / **`oauth_clients`** / **`webhook_secrets`**: `clinic_id` (nullable — platform-level or tenant-level), `name`, hashed secret (`key_hash`/`client_secret_hash`/`secret_hash` — raw values are never persisted), `revoked_at`, plus type-specific fields (`rate_limit_per_minute` on `api_keys`). Real CRUD + real secure key generation/hashing exists, but none of these are wired into request authentication anywhere in the codebase yet — a documented scope boundary, not an oversight (retrofitting API-key auth into every existing endpoint is a separate, larger project).
- **`backups`**: `backup_type`, `status` (ENUM `Pending`/`Completed`/`Failed`), `triggered_by` (FK `platform_admin_users`), `started_at`/`completed_at`, `file_size_bytes`, `storage_location`, `error_message`. "Trigger manual backup" is implemented as a documented, honestly-labeled stub (`pg_dump` is not available in this dev sandbox — verified with `pg_dump --version` before deciding) — it records a `Backup` row rather than fabricating a fake successful dump. Restore is explicitly architecture-only (a stub method, no execution path) — restoring over a live multi-tenant database is too dangerous to implement in this phase.

**No `LegacyMixin` on any Phase 15 table, and this is a deliberate departure from the pattern, not an oversight**: `LegacyMixin` exists to track provenance for clinical/business rows imported from a legacy desktop system (Phase 14). None of these nine tables represent that kind of entity — they are the platform's own meta-tables about tenants, platform staff, and platform operations, which never existed in any legacy system to migrate from. Most also skip `TenantMixin` for the same reason `platform_admin_users` does: they are either platform-global (`platform_admin_users`, `platform_config`, `background_jobs` as a monitoring surface) or carry an explicit *nullable* `clinic_id` FK rather than the mandatory NOT NULL `TenantMixin` column, because several of them (feature flags, API keys) are meaningfully scoped to a clinic while others in the same table set (platform-level API keys) are not.

**Extended `clinics`** (Phase 1/4 table): `suspended_at`/`suspended_reason`/`archived_at` (all nullable). The pre-existing `status` column (String, Phase 4) is reused as-is to also carry `"Suspended"`/`"Archived"` values alongside its original `"Active"` default — no new status column was added.

**Extended `subscriptions`** (Phase 1 table): `trial_start`/`trial_end`/`subscription_start`/`renewal_date`/`expiration_date` (all nullable `DateTime`), `max_users`/`max_branches`/`storage_limit_mb`/`api_rate_limit` (all nullable `Integer`). **License-limit-field placement decision**: these four limit fields live directly on `subscriptions` rather than a separate `license_limits` lookup table, because there is exactly one active subscription row per clinic at any time — a lookup table keyed by plan would add a join for no normalization benefit, since the limits are effectively per-subscription overrides anyway (a lookup-by-plan-only model can't express a negotiated custom limit for one specific clinic). The `subscription_status` native Postgres enum gained one new value, `EXPIRED` (added via `ALTER TYPE ... ADD VALUE`, matching the existing enum's convention of storing Python enum *names* — `ACTIVE`/`PAST_DUE`/`CANCELED`/`TRIALING` — not `.value` strings, so the migration adds `'EXPIRED'` rather than `'expired'`).

**Storage/user-count computation**: per the Phase 12 "generate from operational tables, don't duplicate/cache" principle, a tenant's storage usage and user count are never stored columns — `TenantManagementService.get_tenant_stats()` computes them live via `COUNT` over `users` and `SUM(file_size_bytes)` over `consultation_attachments` + `laboratory_attachments`, both already-`TenantMixin`-scoped tables from Phase 8/10.

## Phase 16: Production Hardening — additive indexes only

Migration `0016_hardening_indexes.py` (`down_revision = "0015_saas_administration"`; revision id shortened from the descriptive filename for the same `alembic_version.version_num VARCHAR(32)` reason documented in Phase 9 above — only the filename stays descriptive). No schema restructuring, no new tables — purely additive `CREATE INDEX` statements, evidence-based:

**Analysis method**: `EXPLAIN ANALYZE` run live against the real dev database (`connectph_clinic`) for the patient list, queue list, visit list, and invoice list queries, cross-referenced against a grep of every `ForeignKey(` column in `app/models/*.py` for a missing `index=True`, cross-referenced against each repository's actual `WHERE`/filter predicates (`app/repositories/*.py`).

**What was already correct** (confirmed, not re-done): nearly every FK column across `visits`/`queues`/`invoices`/`payments`/`consultations`/`appointments` already carries `index=True`, and `visits`/`queues`/`appointments` already have hand-curated composite indexes matching their real list-endpoint filter patterns (e.g. `ix_visits_clinic_branch_date_status`, `ix_appointments_clinic_doctor_date`) — a genuinely well-indexed schema from earlier phases, not a blank slate.

**What was genuinely missing, added by this migration**:
- `laboratory_orders.branch_id` and `laboratory_orders.doctor_id` — every *other* FK column on this table had `index=True`, these two didn't (an inconsistency, not a deliberate omission).
- `ix_laboratory_orders_clinic_status` — composite `(clinic_id, status)`, matching the worklist-by-status filter pattern used elsewhere in the app.
- `ix_invoices_clinic_status` and `ix_invoices_clinic_invoice_date` — composites. `invoices` had single-column indexes on `clinic_id` and `status` (and `clinic_id` and `invoice_date`) *separately*, but `InvoiceRepository.list_invoices` always filters `clinic_id` AND (optionally) `status`/date-range *together* (`app/repositories/invoice_repository.py` ~lines 113-126). Confirmed live via `EXPLAIN ANALYZE`: `SELECT * FROM invoices WHERE clinic_id = :c AND status = 'PendingPayment' ORDER BY invoice_date DESC LIMIT 20` used `Index Scan using ix_invoices_status` and then applied `clinic_id` as a row-level `Filter` — a composite index removes that extra filter step at scale.

**Honest scope note on measured impact**: the real dev database has ~20 rows in `visits`/`queues`, 2 in `invoices`, 0-11 in `laboratory_orders` at the time of this analysis — small enough that Postgres's query planner correctly prefers a sequential scan over an index scan for the un-composited queries regardless of which indexes exist (confirmed live: the `visits`/`queues` list queries both chose `Seq Scan` even with indexes available, correctly, since a seq scan over ~20 rows is cheaper than an index scan). These indexes are added because they are the right call for a production-scale dataset and the storage/write-amplification cost is negligible on tables this size — not because a measurable query-time speedup was observed on this demo dataset. No fabricated before/after numbers are reported here; this is the honest finding.

## Phase 18: Patient Portal

Four new tables plus two additive columns, migration `0017_patient_portal.py` (`down_revision = "0016_hardening_indexes"`). Following the Phase 15 precedent, patients are a THIRD structurally separate class of principal (not `users`, not `platform_admin_users`):

- **`patient_accounts`**: `patient_id` (FK `patients`, unique — one-to-one), `password_hash`, `auth_method` (plain `String(30)`, default `"password"` — documents that OTP/social login are future values only, no enum with unused members), `is_email_verified`, `last_login_at`, `is_active`, plus `TenantMixin`'s `clinic_id` (denormalized from `patient_id.clinic_id` for query convenience, always kept in sync — a patient account can never point at a different clinic than its own patient record). **Chosen as a separate table rather than nullable columns on `Patient` itself**: `Patient` is written/read constantly by clinic staff (registration, demographics editing) and mixing login-credential columns into that high-churn table would blur two different write-paths/threat-models; a patient may also exist for years with zero portal usage (walk-in-only clinics), so an optional one-to-one table fits better than nullable columns on every patient row.
- **`patient_password_reset_tokens`**: `patient_account_id` (FK), `token_hash` (unique), `expires_at`, `used_at`. Same `generate_secure_token`/`hash_token`/single-use-expiring-row pattern as the existing staff `password_reset_tokens` table, but a genuinely separate table — a token minted here can never be replayed against the staff reset endpoint (which queries `password_reset_tokens`) and vice versa.
- **`patient_notification_preferences`**: `patient_id` (FK, unique), four boolean toggles (`appointment_reminders`/`lab_result_alerts`/`billing_notices`/`clinic_announcements`, all default `true`), `preferred_channel` (ENUM `InApp`/`Email`/`SMS`/`Push`, default `InApp`). A simple settings row — no real push/email/SMS delivery wiring in this phase, per spec's "architecture placeholder is acceptable" language.
- **`patient_notifications`**: `patient_id`, `notification_type` (ENUM `AppointmentReminder`/`LabResultReleased`/`BillingNotice`/`ClinicAnnouncement`), `title`, `body`, `is_read`, `read_at`. A read-only in-app feed — rows are created synchronously by the relevant service action; no background job/scheduler exists for an equivalent feature yet, so none was added here either.
- **Extended `diagnoses`** and **`consultation_attachments`** (Phase 8 tables): both gained `patient_visible` (`Boolean`, default `false`). **Safer-default decision**: clinic staff must explicitly opt a diagnosis/attachment into patient visibility; nothing is exposed to the Patient Portal's Medical Records view by default. The Patient Portal's `list_medical_records` query filters on `patient_visible = true` on both tables and hides a consultation entirely if it has zero patient-visible diagnoses/attachments (rather than showing an empty-looking record).

**JWT claim shape** (`app/core/patient_security.py`, mirrors `app/core/platform_admin_security.py`'s Phase 15 pattern exactly): `{"sub": patient_account_id, "patient_account_id": ..., "patient_id": ..., "clinic_id": ..., "type": "patient_access" | "patient_refresh", ...}` — the `type` value never overlaps with clinic-staff (`"access"`/`"refresh"`) or platform-admin (`"platform_admin_access"`/`"platform_admin_refresh"`) tokens, and only a patient payload carries both `patient_account_id` and `patient_id` claims. `get_current_patient` (`app/core/dependencies.py`) is the only dependency that accepts this token; `get_current_user` and `get_current_platform_admin` reject it (wrong `type`, missing claims), and `get_current_patient` rejects clinic-staff/platform-admin tokens for the same reason in reverse — verified in `backend/app/tests/test_patient_portal.py`.

**No `LegacyMixin` on any Phase 18 table**, same rationale as Phase 15: these are net-new patient-portal-specific rows with no legacy-system equivalent to track provenance from.

## Phase 19: Patient Self-Service Appointment Booking

Migration `0018_patient_appointment_booking.py`. No new tables — a patient-booked appointment is a plain row in the existing `appointments` table (Phase 11), created through the same `AppointmentService`/`AppointmentRepository`/`TimeSlotService` staff booking already used.

- **`appointments.booking_source`** (new column): `ENUM('Staff', 'Patient')`, `NOT NULL`, `server_default='Staff'`, indexed (`ix_appointments_booking_source`). Lets reception/reporting distinguish a patient-initiated booking from a staff one without inferring it from `created_by IS NULL` (which was already a usable-but-implicit signal, since patient-initiated writes set `created_by`/`updated_by` to `NULL` — there's no `users` row for a patient).
- **`uq_appointments_doctor_slot_active` now also declared in `Appointment.__table_args__`** (was previously created ONLY via raw SQL inside migration 0012's `upgrade()`): a partial unique index on `(clinic_id, doctor_id, appointment_date, start_time)` `WHERE is_deleted = false AND status NOT IN ('Cancelled', 'Rescheduled', 'NoShow')` — the actual DB-level guarantee preventing two concurrent bookings from double-booking the same doctor/date/time. Declaring it in SQLAlchemy too (via `Index(..., postgresql_where=...)`, same name) means `Base.metadata.create_all()` — how the test database schema is built (see `backend/app/tests/conftest.py`) — creates it as well; before this fix the test schema was silently missing it (see `docs/BUGS.md` BUG-012). This does not touch migration 0012 itself (append-only migration history rule) and is a no-op against any database that already ran that migration.
- **Race-condition handling in the service layer**: `AppointmentService._create_appointment_impl` (used by both staff and patient booking) and `reschedule_patient_appointment` wrap the appointment INSERT (and, after a bug found this phase — see `docs/BUGS.md` BUG-013 — the daily appointment-number counter's own first-of-day INSERT too) in a single `try/except IntegrityError`, translating a Postgres unique-violation on `uq_appointments_doctor_slot_active` into a clean `409 Conflict` instead of a raw `500`.
- **No new patient-side tables**: `GET .../appointments`, create/reschedule/cancel all read/write the same `appointments` row a staff user would see via `GET /appointments`, scoped by `patient_id = current.id` (from the verified patient JWT) rather than a separate table or view.

**Down-revision chain**: `0018_patient_appointment_booking` → `0017_patient_portal` (unchanged, append-only).

## Phase 20: Client Acceptance Revisions — internal messaging (item 14)

Migration `0019_internal_messaging.py` (`down_revision = "0018_patient_appointment_booking"`). One new table, no changes to any existing table (the Phase 20 consultation-fee override, item 9, is passed through in-request rather than persisted, so it needed no schema change).

- **`internal_messages`**: `sender_id`/`recipient_id` (both FK `users.id`, `ondelete="CASCADE"`, indexed), `body` (`Text`), `read_at` (nullable `DateTime`, null until the recipient views the conversation), plus `TenantMixin`'s `clinic_id` and `TimestampMixin`'s `created_at`/`updated_at`. Deliberately minimal per spec: no threads/conversations table, no attachments, no group recipients, no read-receipt granularity beyond this one boolean-ish timestamp.
- **`ix_internal_messages_recipient_sender_created`** (composite index on `recipient_id, sender_id, created_at`): supports the one query shape this feature actually needs - "every message between me and this other user, oldest first."
- **No `LegacyMixin`**: a net-new Phase 20 feature with no legacy-system equivalent, same rationale as Phase 15/18's new tables.

## Phase 21: Receptionist Shift Management

Migration `0020_shift_management.py` (`down_revision = "0019_internal_messaging"`). One new table.

- **`shifts`**: `branch_id` (nullable FK `branches.id`, `SET NULL`), `receptionist_user_id` (FK `users.id`, `CASCADE`), `opening_cash` (`Numeric(12,2)`), `opened_at`/`closed_at` (`DateTime(timezone=True)`, the latter nullable until close), `actual_cash_count` (`Numeric(12,2)`, nullable until close), `status` (`ENUM('Open','Closed')`), `notes` (`String(1000)`, nullable), plus `TenantMixin`'s `clinic_id` and `TimestampMixin`'s `created_at`/`updated_at`.
- **`ix_shifts_one_open_per_receptionist`**: a partial unique index on `receptionist_user_id` `WHERE status = 'Open'` — enforces "only one Open shift per receptionist" at the database level, closing the race-condition gap between the service layer's check and its insert.
- **Deliberately no summary/total columns**: cash/GCash/card/other collection totals, discounts, refunds, and expected cash are always computed at read time from the existing `payments`/`discounts`/`refunds` tables, scoped to the shift's `opened_at`..(`closed_at` or now) time window - there is no running total on this table to keep in sync, by design (see `backend/app/services/shift_service.py`'s module docstring).
- **No `LegacyMixin`**: a net-new feature with no legacy-system equivalent, same rationale as Phase 15/18/20's new tables.
- **Attribution note**: collection totals are scoped to `Payment.received_by` (cleanly attributable per-receptionist); `Discount.approved_by`/`Refund.approved_by` track the *approver*, not necessarily the front-desk receptionist, so discount/refund totals are scoped to clinic(+branch)+time-window instead of per-receptionist - a deliberate, documented modeling choice given what the existing `Discount`/`Refund` tables actually capture, not an oversight.

**Down-revision chain**: `0020_shift_management` → `0019_internal_messaging` (unchanged, append-only).

## Client Acceptance Revisions, Round 3 (item 14): Doctor Session Control

Migration `0021_doctor_session.py` (`down_revision = "0020_shift_management"`). One new table.

- **`doctor_sessions`**: `doctor_id` (FK `doctors.id`, `CASCADE`), `session_date` (`Date`), `started_at`/`ended_at` (`DateTime(timezone=True)`, the latter nullable while the session is open), `started_by` (nullable FK `users.id`, `SET NULL`), plus `TenantMixin`'s `clinic_id` and `TimestampMixin`'s `created_at`/`updated_at`. A row is created when a Doctor presses "Start Receiving Patients"; `ended_at` is set when the session ends (explicitly, or implicitly by the next day's fresh row via the unique constraint below).
- **`uq_doctor_session_clinic_doctor_date`**: unique on `(clinic_id, doctor_id, session_date)` - at most one session row per doctor per day.
- **`ix_doctor_sessions_one_open_per_doctor`**: a partial unique index on `doctor_id` `WHERE ended_at IS NULL` - at most one *open* session per doctor at a time, mirroring `ix_shifts_one_open_per_receptionist`'s technique from Phase 21.
- **Checked first before adding new schema** (per this round's explicit instruction): confirmed no existing `DoctorActivity`/`ConsultationSession` concept already modeled "doctor is actively receiving patients today" - `ConsultationSession` (Phase 7, `models/consultation_session.py`) tracks a per-*visit* consultation timing window, a different concept entirely, so was not reused/overloaded.
- **Deliberately not a hard gate**: no other table or service enforces "Reception can only Call a ticket for a doctor with an open session" - the spec requires Reception's existing "Manual Queue Override" to keep working "regardless of session state," so `DoctorSession` is additive UI/orchestration state (backs the Doctor Workspace's "Start Receiving Patients"/"Next Patient" buttons), not a permission gate on `POST /doctor-workspace/visits/{id}/call` or `POST /queues`.
- **No `LegacyMixin`**: a net-new feature with no legacy-system equivalent.

**Down-revision chain**: `0021_doctor_session` → `0020_shift_management` (unchanged, append-only). Verified clean end-to-end (`alembic upgrade head` from a fresh empty database through all 21 migrations) on a throwaway database before applying to the real dev database.

## Phase 2.7: YAKAP Patient Classification + Receptionist Queue Control

Migration `0029_yakap_classification.py` (`down_revision = "0028_tv_display_short_code"`). Two additive columns, no new tables, no rewrite of existing rows.

- **`patients.is_yakap_beneficiary`** (`Boolean`, `NOT NULL`, `server_default=false`): the patient's STANDING PhilHealth YAKAP beneficiary status, set on the patient profile. Every existing patient row defaults to `false` (Regular) with no backfill needed.
- **`queues.visit_classification`** (new Postgres enum `visit_classification` — `'Yakap' | 'Regular'`, `NOT NULL`, `server_default='Regular'`, indexed via `ix_queues_visit_classification`): the PER-ENCOUNTER classification of a specific queue ticket, set at ticket-creation time (pre-filled from the patient's beneficiary flag, independently editable). Deliberately NOT a queue prefix — `queue_number`/`queue_prefix` generation (`QueueCounter`, `QueueNumberGenerator`) is completely untouched by this migration.
- **Why two separate columns, not one**: `Patient.is_yakap_beneficiary` is a standing fact about the patient; `Queue.visit_classification` is a per-visit operational decision the receptionist makes (pre-filled from the patient flag, but not forced) — collapsing them into one field would have made it impossible to record a YAKAP beneficiary's walk-in visit as a Regular encounter, or vice versa, which the spec explicitly required.
- **No `LegacyMixin` interaction**: both columns are additive on existing tables; legacy-migrated rows get the same safe defaults as any other pre-existing row.

**Down-revision chain**: `0029_yakap_classification` → `0028_tv_display_short_code` (unchanged, append-only). Applied cleanly to the real dev database with `alembic upgrade head`; the disposable test database (built via `Base.metadata.create_all()`, not Alembic — see `backend/app/tests/conftest.py`) picks up both columns automatically from the updated models, no separate migration step needed there.
