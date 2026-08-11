# API Reference

Base URL (local): `http://localhost:8000/api/v1`
Base URL (production): `https://<your-railway-app>.up.railway.app/api/v1`

All request/response bodies are JSON (`Content-Type: application/json`). All timestamps are ISO 8601 UTC.

## Authentication header

Once logged in, send the access token on every subsequent request:

```
Authorization: Bearer <access_token>
```

Tokens carry `sub` (user id), `clinic_id`, and standard JWT claims (`iat`, `exp`). The backend resolves the tenant context from `clinic_id` on every authenticated request — see [`ARCHITECTURE.md`](ARCHITECTURE.md#4-dependency-injection-in-fastapi-appapidepspy).

---

## `GET /api/v1/health`, `GET /api/v1/live`, `GET /api/v1/ready`

Three probes, no auth required:

- `/health` — original combined check, unchanged shape: `{"status": "ok"}`.
- `/live` — liveness only: `{"status": "alive", "uptime_seconds": 561.87}`.
- `/ready` — readiness, performs a real `SELECT 1` against Postgres: `{"status": "ready", "database": "reachable"}`.

All three verified live against the running dev backend during v1.0.0 release verification.

---

## `POST /api/v1/auth/register`

Registers a new clinic and its first user (the Owner), or registers a new user invited into an existing clinic, depending on payload. Foundation-stage implementation covers the "new clinic + owner" path.

**Request**

```json
{
  "clinic_name": "Guadalupe Family Clinic",
  "email": "owner@guadalupeclinic.ph",
  "password": "Str0ngP@ssword!",
  "first_name": "Maria",
  "last_name": "Santos"
}
```

**Response `201 Created`**

```json
{
  "user": {
    "id": "9c1f1e2a-2b3c-4d5e-8f9a-0b1c2d3e4f5a",
    "clinic_id": "1a2b3c4d-5e6f-7081-92a3-b4c5d6e7f809",
    "email": "owner@guadalupeclinic.ph",
    "first_name": "Maria",
    "last_name": "Santos",
    "is_email_verified": false,
    "created_at": "2026-07-23T04:00:00Z"
  },
  "clinic": {
    "id": "1a2b3c4d-5e6f-7081-92a3-b4c5d6e7f809",
    "name": "Guadalupe Family Clinic",
    "slug": "guadalupe-family-clinic"
  }
}
```

**Errors**

| Status | Reason |
|---|---|
| `400` | Validation error (weak password, missing fields) |
| `409` | Email already registered |

---

## `POST /api/v1/auth/login`

**Request**

```json
{
  "email": "owner@guadalupeclinic.ph",
  "password": "Str0ngP@ssword!"
}
```

**Response `200 OK`**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": "9c1f1e2a-2b3c-4d5e-8f9a-0b1c2d3e4f5a",
    "clinic_id": "1a2b3c4d-5e6f-7081-92a3-b4c5d6e7f809",
    "email": "owner@guadalupeclinic.ph",
    "roles": ["Owner"]
  }
}
```

On both success and failure, an `audit_logs` entry is written (`auth.login.success` / `auth.login.failure`) including IP and user agent.

**Errors**

| Status | Reason |
|---|---|
| `401` | Invalid email or password |
| `403` | Account deactivated (`is_active = false`) or clinic suspended |

---

## `POST /api/v1/auth/refresh`

Exchanges a valid refresh token for a new access token (and, depending on rotation policy, a new refresh token).

**Request**

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response `200 OK`**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900
}
```

**Errors**

| Status | Reason |
|---|---|
| `401` | Refresh token invalid, expired, or revoked |

---

## `POST /api/v1/auth/logout`

Revokes the current refresh token (server-side denylist/rotation, see [`SECURITY.md`](SECURITY.md)).

**Request**

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response `204 No Content`**

---

## `POST /api/v1/auth/forgot-password`

> **Status:** Token issuance, hashing, and expiry are fully implemented (`password_reset_tokens`, see [`DATABASE.md`](DATABASE.md)). **TODO:** actual SMTP/email provider integration — the reset link is not yet delivered by email, only generated server-side.

**Request**

```json
{
  "email": "owner@guadalupeclinic.ph"
}
```

**Response `200 OK`** (always returns success, regardless of whether the email exists, to avoid user enumeration)

```json
{
  "message": "If an account with that email exists, a password reset link has been sent."
}
```

---

## `POST /api/v1/auth/reset-password`

> **Status:** Fully implemented against the database — validates the hashed token, its expiry, and single-use (`used_at`), then re-hashes and stores the new password and revokes all of the user's active refresh tokens. Only the upstream email delivery of the reset link (see `forgot-password`) remains TODO.

**Request**

```json
{
  "token": "reset-token-from-email-link",
  "new_password": "N3wStr0ngP@ss!"
}
```

**Response `200 OK`**

```json
{
  "message": "Password has been reset successfully."
}
```

**Errors**

| Status | Reason |
|---|---|
| `400` | Token invalid, expired, or password fails strength validation |

---

## `POST /api/v1/auth/verify-email`

**Request**

```json
{
  "token": "verify-token-from-email-link"
}
```

**Response `200 OK`**

```json
{
  "message": "Email verified successfully."
}
```

Sets `users.email_verified_at` (and `is_email_verified = true`) and marks the corresponding `email_verification_tokens` row `used_at`.

**Errors**

| Status | Reason |
|---|---|
| `400` | Token invalid, expired, or already used |

---

## `POST /api/v1/auth/resend-verification`

Issues a fresh `email_verification_tokens` row and (once SMTP is wired) re-sends the verification email. No auth required — rate-limited by email to prevent abuse.

**Request**

```json
{
  "email": "owner@guadalupeclinic.ph"
}
```

**Response `200 OK`** (always generic, to avoid user enumeration)

```json
{
  "message": "If an account with that email exists and is unverified, a new verification link has been sent."
}
```

> **Status:** TODO — real SMTP sending pending (see [`SECURITY.md`](SECURITY.md)); the endpoint issues/rotates the token today.

---

## Auth notes: lockout, rate limiting, cookies

- **Account lockout:** after **5** consecutive failed logins, `users.locked_until` is set (default lockout window: **15 minutes**) and further login attempts return `403` with a generic "account temporarily locked" message until it elapses. A successful login resets `failed_login_attempts` to `0`. See [`SECURITY.md`](SECURITY.md#3-account-lockout-policy).
- **Rate limiting:** `login`, `forgot-password`, `resend-verification`, and `refresh` are rate-limited (Redis-backed) per `(ip_address)` and, where applicable, `(email)`. Exceeding the limit returns `429` with a `Retry-After` header.
- **Refresh token cookie:** the refresh token is set by the backend as an `HttpOnly`, `Secure`, `SameSite=Strict` cookie (`refresh_token`) rather than returned in the JSON body in the cookie-based flow; the `refresh_token` field shown in the `login`/`refresh` examples above reflects the bearer-token fallback used by non-browser clients. `remember_me: true` on `login` extends the cookie's `Max-Age` (and the corresponding `refresh_tokens.expires_at`) from a session-only lifetime to the full **7-day** default; omitted/false issues a shorter-lived, non-`remember_me` session.

---

## User Management (`/api/v1/users`)

All endpoints require a valid access token (`Authorization: Bearer <access_token>` or the auth cookie) and are scoped to the caller's `clinic_id` — a user can never see or modify another clinic's users. Create/update/disable/enable/admin-reset-password additionally require an Administrator or Owner role.

### `GET /api/v1/users`

List/search users within the caller's clinic.

**Query params:** `q` (search across name/email/username), `role`, `status`, `branch_id`, `page`, `page_size`.

**Response `200 OK`**

```json
{
  "items": [
    {
      "id": "9c1f1e2a-2b3c-4d5e-8f9a-0b1c2d3e4f5a",
      "clinic_id": "1a2b3c4d-5e6f-7081-92a3-b4c5d6e7f809",
      "branch_id": "b1c2d3e4-f5a6-7081-92a3-b4c5d6e7f809",
      "first_name": "Maria",
      "middle_name": null,
      "last_name": "Santos",
      "email": "owner@guadalupeclinic.ph",
      "mobile_number": "+639171234567",
      "username": "msantos",
      "role": "Owner",
      "status": "active",
      "profile_photo": null,
      "email_verified_at": "2026-07-20T04:00:00Z",
      "created_at": "2026-07-23T04:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

**Errors:** `401` (missing/invalid token), `403` (not scoped to a clinic).

### `GET /api/v1/users/{user_id}`

Fetch a single user by id (must belong to the caller's clinic).

**Response `200 OK`** — same shape as a list item above. **Errors:** `401`, `403`, `404` (not found or belongs to another clinic — same `404` for both, to avoid leaking existence across tenants).

### `POST /api/v1/users`

*Requires Administrator/Owner role.*

**Request**

```json
{
  "first_name": "Juan",
  "middle_name": null,
  "last_name": "Dela Cruz",
  "email": "juan@guadalupeclinic.ph",
  "mobile_number": "+639171234568",
  "username": "jdelacruz",
  "role": "Receptionist",
  "branch_id": "b1c2d3e4-f5a6-7081-92a3-b4c5d6e7f809"
}
```

No password is supplied at creation — the endpoint issues an `email_verification_tokens` row and (pending SMTP) sends a "set your password"/invite-style email; the account is created with `status = 'pending'` until first login/verification.

**Response `201 Created`** — same shape as a list item. **Errors:** `400` (validation), `403` (insufficient role), `409` (email or username already used within the clinic).

### `PATCH /api/v1/users/{user_id}`

*Requires Administrator/Owner role, or the user updating their own non-privileged fields (name, mobile_number, profile_photo) — role/status/branch changes always require Administrator/Owner.*

**Request** (partial — any subset of updatable fields)

```json
{
  "mobile_number": "+639171234569",
  "role": "Doctor",
  "branch_id": "b1c2d3e4-f5a6-7081-92a3-b4c5d6e7f809",
  "profile_photo": "clinics/1a2b3c4d.../users/9c1f1e2a.../avatar.jpg"
}
```

**Response `200 OK`** — updated user. **Errors:** `400`, `403`, `404`, `409` (username/email collision).

### `POST /api/v1/users/{user_id}/disable`

*Requires Administrator/Owner role.* Sets `status = 'disabled'` (and `is_active = false`); revokes all of the user's active `refresh_tokens` so existing sessions are immediately invalidated.

**Response `200 OK`**

```json
{ "message": "User disabled.", "status": "disabled" }
```

**Errors:** `403`, `404`, `409` (cannot disable the clinic's last remaining Owner).

### `POST /api/v1/users/{user_id}/enable`

*Requires Administrator/Owner role.* Sets `status = 'active'`; does not reset `failed_login_attempts`/`locked_until` (a still-locked account must wait out its lockout window independently, or use `admin-reset-password`).

**Response `200 OK`**

```json
{ "message": "User enabled.", "status": "active" }
```

**Errors:** `403`, `404`.

### `POST /api/v1/users/{user_id}/admin-reset-password`

*Requires Administrator/Owner role.* Administrative override of the self-service `forgot-password` flow — generates a new `password_reset_tokens` entry and (pending SMTP) emails the target user a reset link; does not accept a password directly in the request, to avoid an admin ever knowing another user's plaintext password. Also clears `failed_login_attempts`/`locked_until`.

**Response `200 OK`**

```json
{ "message": "Password reset link issued to the user's email." }
```

**Errors:** `403`, `404`.

---

## Patient Management (`/api/v1/patients`)

All endpoints require a valid access token and are scoped to the caller's `clinic_id`. View endpoints are open to any authenticated clinic role. Add/edit (`POST`/`PUT`) require Owner, Administrator, Receptionist, Doctor, or Nurse. Archive/restore require Owner, Administrator, or Receptionist. Overriding a duplicate-warning (`?override=true`) requires Owner or Administrator regardless of which other role can otherwise create/edit.

### `GET /api/v1/patients`

List/search/filter/sort patients within the caller's clinic.

**Query params:**

| Param | Notes |
|---|---|
| `q` | free-text match against `patient_number`, `legacy_patient_id`, `first_name`, `middle_name`, `last_name`, `mobile_number`, `email` |
| `branch_id`, `gender`, `status` | exact-match filters |
| `age_min`, `age_max` | inclusive age range, translated server-side into a `birth_date` range |
| `registered_from`, `registered_to` | `date_registered` range |
| `last_visit_from`, `last_visit_to` | `last_visit` range |
| `sort` | `newest` (default) \| `oldest` \| `alphabetical` \| `recently_visited` |
| `limit`, `offset` | pagination, `limit` defaults to 20 (max 100) |

**Response `200 OK`**

```json
{
  "items": [
    {
      "id": "c2b1a3f4-...",
      "patient_number": "PAT-000001",
      "first_name": "Juan",
      "middle_name": "Santos",
      "last_name": "Dela Cruz",
      "suffix": null,
      "birth_date": "1990-05-15",
      "gender": "Male",
      "mobile_number": "+639171234567",
      "photo_url": null,
      "branch_id": null,
      "status": "Active",
      "date_registered": "2026-07-25",
      "last_visit": null
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

**Errors:** `401`, `400` (no clinic context).

### `GET /api/v1/patients/{patient_id}`

Fetch a single patient's full profile (all demographic/contact/medical fields). **Errors:** `401`, `404` (not found or belongs to another clinic — same `404` for both, to avoid leaking existence across tenants).

### `POST /api/v1/patients`

*Requires Owner/Administrator/Receptionist/Doctor/Nurse.* Optional query param `override=true` bypasses duplicate detection (Owner/Administrator only).

**Request** — all `PatientCreate` fields (see `backend/app/schemas/patient.py`); minimally: `first_name`, `last_name`, `birth_date`, `gender`, `civil_status`, `nationality`, `mobile_number`.

**Response `201 Created`**

```json
{ "patient": { "...": "PatientRead, see GET /{id}" }, "duplicates": [] }
```

If likely-duplicate patients are found (same first+last name and birth date, or same mobile number) and `override` was not passed, `patient` is `null` and `duplicates` lists the conflicting record(s):

```json
{
  "patient": null,
  "duplicates": [
    {
      "id": "...",
      "patient_number": "PAT-000002",
      "full_name": "Juan Santos Dela Cruz",
      "birth_date": "1990-05-15",
      "mobile_number": "+639171234567",
      "match_reason": "Same name and date of birth"
    }
  ]
}
```

**Errors:** `400` (validation), `403` (insufficient role, or non-admin passing `override=true`).

### `PUT /api/v1/patients/{patient_id}`

*Requires Owner/Administrator/Receptionist/Doctor/Nurse.* Partial update — only supplied fields are applied. If `first_name`, `last_name`, `birth_date`, or `mobile_number` changes and would newly match another patient, the same duplicate-warning response shape as `POST` is returned (with `?override=true` support). Every changed field is recorded as a field-level diff in the resulting `patient.updated` audit log entry.

**Response `200 OK`** — same envelope as `POST`. **Errors:** `400`, `403`, `404`.

### `POST /api/v1/patients/{patient_id}/archive`

*Requires Owner/Administrator/Receptionist.* Sets `status = "Archived"` (a business-status change, distinct from soft-delete — the row is never removed).

**Response `200 OK`** — full `PatientRead`. **Errors:** `403`, `404`.

### `POST /api/v1/patients/{patient_id}/restore`

*Requires Owner/Administrator/Receptionist.* Sets `status = "Active"`.

**Response `200 OK`** — full `PatientRead`. **Errors:** `403`, `404`.

### `GET /api/v1/patients/{patient_id}/qr`

Returns the patient's QR check-in payload (generating and persisting one on first request if missing).

**Response `200 OK`**

```json
{ "patient_id": "c2b1a3f4-...", "qr_code": "1a2b.../c2b1...:9f3a1b2c4d5e6f70", "payload": "1a2b.../c2b1...:9f3a1b2c4d5e6f70" }
```

Rendering an actual QR image is not implemented — see [`DATABASE.md`](DATABASE.md) ("QR code approach"). **Errors:** `401`, `404`.

### `POST /api/v1/patients/{patient_id}/photo`

*Requires Owner/Administrator/Receptionist/Doctor/Nurse.* Presigned-URL stub for uploading a patient photo to Supabase Storage (mirrors the Phase 2 user-profile-photo stub pattern) — no real storage integration or thumbnail generation is wired up yet.

**Response `200 OK`**

```json
{
  "upload_url": "https://stub.supabase.local/storage/v1/upload/clinics/.../patients/.../photo-<token>.jpg",
  "public_url": "https://stub.supabase.local/storage/v1/object/public/clinics/.../patients/.../photo-<token>.jpg",
  "expires_in": 600
}
```

**Errors:** `401`, `403`, `404`.

### `GET /api/v1/patients/{patient_id}/visits` (Phase 6)

Paginated visit history for the Patient Details "Visit History" tab. Same shape as `GET /visits` list items (visit number/date/doctor/department/status/queue number), scoped to this patient and ordered newest-first. Query params: `limit`, `offset`. Delegates to `VisitService.list_for_patient` rather than duplicating query logic.

**Errors:** `401`, `404` (patient not found or not in this clinic).

---

## Clinic Configuration & Master Data (Phase 4)

All endpoints below are tenant-scoped from the JWT (`clinic_id`), soft-delete-aware, and audit-logged on every create/update/delete/restore. **View** access is granted to every authenticated clinic role; **write** access (create/update/delete/restore/seed-defaults) requires Owner or Administrator, via `require_config_view_role`/`require_config_manage_role` (`core/dependencies.py`). List endpoints support `limit`/`offset` pagination (`{items, total, limit, offset}`) and, where noted, free-text search (`q`) and filters.

### Clinic Settings (`/api/v1/clinic-settings`)

Singleton-per-clinic — no list/create/delete, since the clinic already exists as the tenant root.

- `GET /clinic-settings` — full settings + branding view.
- `PUT /clinic-settings` — partial update of settings fields (name, address breakdown, contact, TIN/license, locale prefs).
- `PATCH /clinic-settings/branding` — partial update of branding-only fields (colors, theme).
- `POST /clinic-settings/branding/{asset}/upload` — presigned-URL stub (`asset` = `logo` | `favicon` | `login-background`); same shape/pattern as the patient/user photo-upload stubs. Response: `{upload_url, public_url, expires_in}`.

### Branches (`/api/v1/branches`)

Full CRUD + soft-delete/restore. `GET` supports `q` (name/code/address) and `status` filters.

- `GET /branches`, `GET /branches/{id}`, `POST /branches`, `PUT /branches/{id}`, `DELETE /branches/{id}` (soft), `POST /branches/{id}/restore`.

### Departments (`/api/v1/departments`)

Same CRUD shape as Branches, plus:

- `POST /departments/seed-defaults` — seeds the standard 8-department set for a brand-new clinic; `409` if the clinic already has any departments.

### Doctors (`/api/v1/doctors`)

Full CRUD + soft-delete/restore; `doctor_code` is server-generated (not accepted on create). `GET` supports `q`, `department_id`, `branch_id`, `status` filters.

- `GET /doctors`, `GET /doctors/{id}`, `POST /doctors`, `PUT /doctors/{id}`, `DELETE /doctors/{id}`, `POST /doctors/{id}/restore`.
- `POST /doctors/{id}/photo` — presigned-URL upload stub (same shape as patient photo upload).
- **Doctor schedules** (availability windows only — no appointment-slot/booking logic): `GET /doctors/{id}/schedules`, `POST /doctors/{id}/schedules`, `PUT /doctors/{id}/schedules/{schedule_id}`, `DELETE /doctors/{id}/schedules/{schedule_id}`.

### Consultation Rooms (`/api/v1/consultation-rooms`)

Same CRUD shape as Branches; `GET` supports `q`, `department_id`, `branch_id`, `status` filters.

### Services (`/api/v1/services`)

Same CRUD shape as Departments (`q`, `department_id`, `status` filters), plus `POST /services/seed-defaults` (seeds 7 standard services; skips codes that already exist).

### Queue Settings (`/api/v1/queue-settings`)

Pure configuration — no ticket-issuing/calling/serving endpoints exist.

- `GET /queue-settings` — all queue-setting rows for the clinic (clinic-wide + any per-branch/department/doctor overrides). Each row now also includes read-only `department_name`/`doctor_name` (resolved server-side) alongside the existing `department_id`/`doctor_id`.
- `PUT /queue-settings` — create-or-update the row for the given `(branch_id, department_id, doctor_id)` scope (all `null` = clinic-wide). Post-RC1 (Multi-Department/Multi-Doctor TV Queue Display): `department_id`/`doctor_id` were added to the request body (`QueueSettingCreate`) — previously only `branch_id` was accepted, so a department/doctor-scoped row could not be created through the API at all despite the model already supporting it. **Note**: resolution (`QueueService._resolve_prefix`) requires an exact `branch_id` match against the ticket's own `branch_id`, which is never `null` — a row saved with `branch_id: null` only ever resolves for a clinic-wide lookup that itself passes `branch_id=null`, which doesn't happen for a real queue ticket (see BUG-033 in `docs/BUGS.md`). Set a real `branch_id` on any override you want to actually take effect.
- `PATCH /queue-settings/{id}` — partial update of an existing row.
- `GET /queue-settings/priority-types`, `POST /queue-settings/priority-types`, `PUT /queue-settings/priority-types/{id}`, `DELETE /queue-settings/priority-types/{id}`.
- `POST /queue-settings/priority-types/seed-defaults` — seeds Senior/PWD/Pregnant/Emergency/VIP, skipping codes that already exist.

### Operating Hours (`/api/v1/operating-hours`)

- `GET /operating-hours/branch/{branch_id}` — the branch's full weekly schedule (up to 7 rows).
- `PUT /operating-hours` — create-or-update the row for the given `branch_id` + `day_of_week`.
- `PATCH /operating-hours/{id}`, `DELETE /operating-hours/{id}`.

### Holidays (`/api/v1/holidays`)

Full CRUD + soft-delete/restore; `GET` supports `year` and `branch_id` filters.

---

## Reception & Queue Management (`/api/v1/queues`) (Phase 5)

Role gates: Owner/Administrator/Receptionist manage (create/edit/cancel); +Doctor/Nurse may transition status; all clinic roles (including Viewer) may view.

- `GET /queues` — paginated, filterable list. Query params: `q` (queue number or patient name/number/mobile), `branch_id`, `department_id`, `doctor_id`, `status`, `priority`, `queue_date` (defaults server-side to today when omitted), `limit`, `offset`.
- `GET /queues/{queue_id}` — full detail including denormalized patient/department/doctor/service/branch names and the status-history timeline.
- `POST /queues` — create a ticket. Body: `patient_id`, `branch_id`, `department_id`, `doctor_id` (optional), `service_id`, `priority`, `notes` (optional), `visit_id` (optional, see below). Validates and rejects (400/404/409) an archived patient, an inactive doctor/department/service, or a duplicate active ticket for the same patient+department+day. Auto-generates `queue_number` via `QueueNumberGenerator` and writes the initial `queue_status_history` row + audit log entry. Broadcasts `queue.created` over the clinic's WebSocket channel. **Vitals-before-Queue:** if `service_id` resolves to a service in `QueueService.PRE_QUEUE_VITALS_SERVICE_CODES` (currently `service_code` `CONSULT`/`FOLLOW-UP`), `visit_id` is *required* and must reference an existing `DraftVitals` visit (from `POST /visits/pre-queue`) whose SoapNote already has all required vitals filled in — otherwise 400 (`"...Create a draft visit...first."` if `visit_id` is missing, or `"Cannot create a queue ticket - missing required vitals: ..."` listing exactly which fields are absent). For every other service, `visit_id` must be omitted (400 if supplied) and behavior is unchanged from before this feature existed.
- `POST /visits/pre-queue` — creates a `DraftVitals`-status Visit with `queue_id=None`, for capturing vitals before a Consultation/Follow-up queue ticket exists. Body: `patient_id`, `branch_id`, `doctor_id`, `department_id`, `service_id`. The returned visit's `id` is the `visit_id` to pass to `POST /queues` once vitals are saved via the existing `POST /visits/{id}/consultation/open-for-reception` + `PUT /consultations/{id}/soap/subjective-objective` endpoints (unchanged, shared with the after-queueing vitals-edit flow).
- `PATCH /queues/{queue_id}` — reassign routing ("Move Queue" / "Change Doctor" / "Change Department"): `department_id`, `doctor_id`, `service_id`, `priority`, `notes` (all optional, re-validated against active/inactive status). Rejected (400) once the ticket is `Completed` or `Cancelled`. Broadcasts `queue.updated`.
- `PATCH /queues/{queue_id}/status` — status transition. Body: `status`, `note` (optional). Enforces the legal-transition table (`QUEUE_STATUS_TRANSITIONS`); an illegal transition (e.g. `Completed` → anything) 400s. Stamps `called_at`/`serving_started_at`/`completed_at` as appropriate, writes `queue_status_history` + audit log. Broadcasts `queue.status_changed`.
- `POST /queues/{queue_id}/cancel` — convenience wrapper for `PATCH .../status {status: "Cancelled"}`.
- `GET /queues/{queue_id}/slip` — printable-slip payload: clinic/branch name, large queue number, patient name, doctor, department, service, priority, date/time, and a signed `qr_token` (same HMAC-signed-opaque-string approach as the patient QR payload in `PatientService`).

### WebSocket: `GET /api/v1/ws/queues/{clinic_id}?token=<access_token_or_public_slug>`

Upgrades to a WebSocket connection and streams JSON frames `{"event": "queue.created" | "queue.updated" | "queue.status_changed" | "visit.called" | "visit.consultation_started" | "visit.consultation_completed" | "visit.status_changed" | "visit.lock_acquired" | "visit.lock_released", "data": {...}}` for every write on that clinic's queue/visits. Originally architecture-only in Phase 5, extended with real events by Phase 7, and (Phase 13) now has a real public consumer — the TV Display.

**Auth (extended in Phase 13)**: browser `WebSocket` clients cannot set an `Authorization` header on the handshake, so a credential is passed as the `token` query param. Two credential types are accepted:

1. A normal JWT access token (Phase 5, unchanged) — its `clinic_id` claim must match the `{clinic_id}` path segment.
2. **(Phase 13, new)** A TV display's `public_slug` — resolved via `TvDisplayConfigRepository.get_by_public_slug` (which already enforces `is_public=True`/`is_active=True`/`is_deleted=False`). If it resolves, the connection is scoped to *that display config's own* `clinic_id`, not the `{clinic_id}` path segment — trusting the resolved value rather than the caller-supplied path prevents a slug being replayed against an arbitrary clinic in the URL.

Either way, a token that resolves to neither a valid JWT nor a valid public slug closes the connection with policy-violation (`1008`). **Why extend the existing channel instead of building a second one for the TV Display**: it's the exact same event stream a display needs (queue/visit status changes), reusing it means zero duplicated broadcast logic in `QueueService`/`DoctorWorkspaceService`, and the slug-as-credential model mirrors the public HTTP endpoint's own security model (see below) rather than introducing a second, different auth mechanism just for WebSockets.

Scaling: connections are held in an in-process `ConnectionManager` (`app/core/ws_manager.py`), so broadcasts only reach clients connected to the same API process. **TODO(production):** swap in Redis pub/sub before running more than one API worker/instance — this mirrors the same documented fallback pattern already used by the rate limiter when Redis is unavailable.

---

## Visit (Encounter) Management (`/api/v1/visits`) (Phase 6)

Role gates mirror the Phase 5 Queue matrix (`core/dependencies.py`): `VISIT_VIEW_ROLES` (all clinical roles) view; `VISIT_CREATE_ROLES`/`VISIT_MODIFY_ROLES` (Owner/Administrator/Receptionist) create/edit; `VISIT_CLOSE_ROLES` (+Doctor/Nurse) transition status. **The real-world creation trigger for a Visit is `POST /queues`** (see above) — `POST /visits` exists for internal/test/completeness use only; receptionists never call it directly in normal operation.

- `GET /visits` — paginated, filterable list. Query params: `q` (visit number, queue number, or patient name/number), `branch_id`, `patient_id`, `doctor_id`, `department_id`, `status`, `visit_type`, `date_from`, `date_to`, `limit`, `offset`.
- `GET /visits/{visit_id}` — full detail including denormalized patient/doctor/department/service/branch/queue names and the embedded chronological `timeline`.
- `GET /visits/{visit_id}/timeline` — the visit's `visit_timeline_events`, standalone (same entries embedded in the detail response above).
- `POST /visits` — direct/internal creation. Body: `patient_id`, `branch_id`, `doctor_id`/`department_id`/`service_id` (optional), `visit_type` (default `WalkIn`), `priority` (default `Normal`), `remarks` (optional). Validates and rejects (400/404) an archived patient or inactive doctor. Auto-generates `visit_number` via `VisitNumberGenerator` and writes `Registered`/`Queued` timeline events + an audit log entry.
- `PATCH /visits/{visit_id}` — update routing (`doctor_id`, `department_id`, `service_id`, `priority`, `remarks`, all optional). Rejected (400) once the visit is `Completed` or `Cancelled`.
- `PATCH /visits/{visit_id}/status` — status transition. Body: `status`, `note` (optional). Enforces the legal-transition table (`VISIT_STATUS_TRANSITIONS`); an illegal transition 400s. Stamps `called_time`/`consultation_start`/`consultation_end`+`check_out_time` as appropriate, writes a `visit_timeline_events` row (`Called`/`ConsultationStarted`/`ConsultationFinished`/`Cancelled`/`StatusChanged`) + audit log entry.

**Queue → Visit auto-creation:** `POST /queues` (Phase 5) now internally creates a linked Visit in the same DB transaction, then returns it as additive fields on the queue response — `visit_id` (UUID) and `visit_number` (string) alongside every existing Phase 5 field. Every other Phase 5 queue endpoint is unchanged.

---

## Doctor Workspace (`/api/v1/doctor-workspace`) (Phase 7)

Role gates (`core/dependencies.py`): `DOCTOR_WORKSPACE_VIEW_ROLES` (Owner/Administrator/Doctor/Receptionist) view; `DOCTOR_WORKSPACE_ACT_ROLES` (Owner/Administrator/Doctor) act. A Doctor-role caller is always scoped to their own linked Doctor record (resolved via `users.doctor_id`) regardless of any `doctor_id` query param; Owner/Administrator may view/act on any doctor via that param, or omit it to see all doctors' visits; Receptionist is view-only (403 on every action endpoint). All Visit status changes go through `VisitService.change_status()` (Phase 6's legal-transition table) — this module never invents a second state machine.

- `GET /doctor-workspace/dashboard?doctor_id=<uuid>` — today's stat cards: `waiting`, `called`, `serving`, `completed_today`, `cancelled`, `no_show` (live `COUNT ... GROUP BY status` over today's visits) and `avg_consultation_seconds` (real `AVG(duration_seconds)` over today's ended `consultation_sessions`, `null` until at least one consultation has completed). `doctor_id` is Owner/Administrator-only; ignored (and required to resolve, else 403) for Doctor-role callers.
- `GET /doctor-workspace/queue?doctor_id=<uuid>` — today's visits assigned to the target doctor (or all doctors' visits for Owner/Administrator with no `doctor_id`), each with denormalized patient name/number/age/gender, `waiting_seconds` (live `now - arrival_time` for `Waiting` visits, else `null`), and lock state (`is_locked`/`locked_by_name`/`locked_by_self`).
- `POST /doctor-workspace/visits/{visit_id}/call` — `Waiting → Called` (via `VisitService.change_status`), writes `doctor_activity` (`PatientCalled`) + audit log, broadcasts `visit.called`.
- `POST /doctor-workspace/visits/{visit_id}/recall` — re-broadcasts `visit.called` (with `"recall": true`) **without** changing status; 400 if the visit isn't currently `Called`. Intended for calling the patient again over a PA/display.
- `POST /doctor-workspace/visits/{visit_id}/start-consultation` — `Called → InConsultation`, opens a `consultation_sessions` row, writes `doctor_activity` (`ConsultationStarted`) + audit log, broadcasts `visit.consultation_started`.
- `POST /doctor-workspace/visits/{visit_id}/complete-consultation` — `InConsultation → Completed`, closes the active `consultation_sessions` row with a computed `duration_seconds`, releases any open visit lock, writes `doctor_activity` (`ConsultationCompleted`) + audit log, broadcasts `visit.consultation_completed` + `visit.lock_released`.
- `POST /doctor-workspace/visits/{visit_id}/no-show` — transitions to `NoShow` (legal from `Registered`/`Waiting`/`Called`), releases any open lock, writes `doctor_activity` (`MarkedNoShow`) + audit log, broadcasts `visit.status_changed`.
- `POST /doctor-workspace/visits/{visit_id}/cancel` — body: `reason` (optional). Transitions to `Cancelled`, releases any open lock, writes `doctor_activity` (`VisitCancelled`, with `reason` in metadata) + audit log, broadcasts `visit.status_changed`.
- `POST /doctor-workspace/visits/{visit_id}/open` — acquires/refreshes the visit's editing lock. Same user re-opening refreshes `locked_at`; a different, still-fresh lock holder is returned as `{locked: true, locked_by, locked_by_name, locked_at, is_self: false}` (no edit access granted); a stale lock (>15 min since `locked_at`) is taken over. Writes `doctor_activity` (`VisitOpened`) + audit log on a fresh acquisition, broadcasts `visit.lock_acquired`. Receptionist callers get a read-only peek at lock state and can never acquire.
- `POST /doctor-workspace/visits/{visit_id}/release-lock` — releases the caller's own active lock (no-op if they don't hold one), broadcasts `visit.lock_released`.

All action endpoints return the updated `VisitDetail` (same shape as `GET /visits/{id}`) except `open`/`release-lock`, which return `LockInfo`.

**WebSocket:** this module broadcasts over the **same** `GET /api/v1/ws/queues/{clinic_id}?token=<access_token>` channel Phase 5 built (`app/core/ws_manager.py::queue_connection_manager`) rather than a second connection manager, adding events `visit.called` / `visit.consultation_started` / `visit.consultation_completed` / `visit.status_changed` / `visit.lock_acquired` / `visit.lock_released` alongside the existing `queue.*` events. Same in-process-only limitation and Redis pub/sub TODO as documented in the Phase 5 section above — a future TV Display or multi-tab Doctor Workspace session can subscribe to this one channel for all of it.

**Known follow-up TODO:** `POST /users` (`UserCreate`) has no `doctor_id` field yet, so linking a new Doctor-role login to its Doctor record currently requires a direct DB update after user creation (see `docs/DATABASE.md` Phase 7 section) — extend the create-user schema/endpoint in a future pass.

---

## Clinical Consultation / SOAP (Phase 8)

Role gates (`core/dependencies.py`): `CONSULTATION_VIEW_ROLES`/`CONSULTATION_EDIT_ROLES` (Owner/Administrator/Doctor) pass the endpoint-level gate; the **service layer** then enforces the actual, stricter rule — only the visit's assigned doctor (`current_user.doctor_id == visit.doctor_id`) gets `can_edit=True`, Owner/Administrator are always view-only (403 on every write). Receptionist is not in either role set at all, so it 403s at the dependency level on every endpoint in this section, both view and edit. Locking reuses Phase 7's `visit_locks` (see `docs/DATABASE.md`), keyed by `visit_id`.

- `POST /visits/{visit_id}/consultation/open` — idempotent: creates the visit's Draft consultation if none exists yet, or resumes the existing one ("latest wins"). Acquires/refreshes the visit lock only if the caller can edit (view-only callers get lock *info*, not lock *acquisition*). Writes `ConsultationOpened` to the visit timeline + audit log on first creation. Returns `ConsultationDetail`.
- `GET /visits/{visit_id}/consultation` — fetch the visit's consultation (or `null` if none opened yet) without side effects.
- `GET /consultations/{id}` — full detail: SOAP note, diagnoses, attachments, lock state.
- `GET /consultations/{id}/soap` / `PUT /consultations/{id}/soap` — the autosave target. `PUT` upserts the single `soap_notes` row (never creates a second one), server-computes `bmi` from `height_cm`/`weight_kg` when both are present, bumps `Draft → InProgress` on the first save with real content, and is autosave-idempotent: identical repeat payloads update `updated_at` but do **not** write a `visit_timeline_events`/audit entry (see `docs/DATABASE.md` Phase 8 section). 400 if the consultation is already `Signed`.
- `POST /consultations/{id}/diagnoses` — add a diagnosis (`diagnosis_type: Primary|Secondary`, `status: Working|Final`, optional `icd10_code`/`icd10_description`/`notes`). Writes `DiagnosisAdded` timeline + audit. Returns the updated `ConsultationDetail`.
- `GET /consultations/{id}/diagnoses` — list diagnoses for the consultation.
- `PATCH /consultations/{id}/diagnoses/{diagnosis_id}` — partial update (type/status/notes/ICD-10 fields).
- `POST /consultations/{id}/complete` — `Draft/InProgress → Completed`. Idempotent if already `Completed`/`Signed` (no error on a repeat call). Writes `ConsultationCompleted` timeline + audit, and — the critical Phase-7-lesson interaction — calls `VisitService.change_status(..., Completed)` **and** mirrors the same transition onto the linked Queue ticket, so neither the Visit nor its Queue ticket is left stuck. Tolerant of an already-`Completed` Visit (e.g. completed independently via the Doctor Workspace first).
- `POST /consultations/{id}/sign` — `Completed → Signed` only (a distinct, final lock-in step; SOAP edits 400 after this). Writes `ConsultationSigned` timeline + audit, releases any open visit lock.
- `POST /consultations/{id}/attachments` — presigned-URL-stub upload (same pattern as patient photo upload — see `docs/DATABASE.md`). Body: `attachment_type` (`ClinicalImage`/`PDF`/`ReferralLetter` — **not** Lab Requests, which have no upload path), `file_name`, optional `file_size_bytes`. Returns `{id, upload_url, file_url, expires_in}`.
- `GET /consultations/{id}/attachments` — list attachments.
- `GET /consultations/{id}/timeline` — thin wrapper over the *same* `visit_timeline_events` rows `GET /visits/{id}` exposes (scoped to the consultation's visit), not a parallel timeline table.

All mutating endpoints return the updated `ConsultationDetail` (SOAP note + diagnoses + attachments + lock state), except `open` (also `ConsultationDetail`) and the attachment-upload endpoint (`{id, upload_url, file_url, expires_in}`).

---

## Clinical Orders & Prescriptions (Phase 9)

Role gating: only the visit's assigned doctor may create/update; Owner/Administrator view-only; **Receptionist read-only** (view allowed, edit 403 — distinct from Phase 8's Receptionist-excluded-entirely rule); a new **Laboratory** role may view Laboratory-category orders only (`GET /laboratory/orders`), no access to anything else in this module.

- `POST /consultations/{id}/orders` — create an order. Body: `order_category` (`Laboratory`/`Radiology`/`Procedure`/`Referral`/`Vaccination`/`Custom`), `priority` (`Routine`/`STAT`, default `Routine`), optional `scheduled_date`/`clinical_notes`, `items: [{item_name, item_category?, exam_type?, body_part?, clinical_indication?}]` (at least 1). Server-generates `order_number` (`ORD-YYYYMMDD-000001`). Writes `OrderCreated` timeline + audit.
- `GET /consultations/{id}/orders` — list orders for a consultation.
- `PATCH /orders/{id}/status` — update `status` (`Requested`/`Collected`/`Processing`/`Completed`/`Cancelled`), validated against `ORDER_STATUS_TRANSITIONS`.
- `POST /consultations/{id}/procedures` — create a procedure (`procedure_name`, optional `procedure_date`/`notes`). **No order number** — Procedures are their own table, not an `orders` row (see `docs/DATABASE.md`). Writes `ProcedureCreated` timeline + audit.
- `GET /consultations/{id}/procedures` — list procedures for a consultation.
- `POST /consultations/{id}/referrals` — create a referral (`referred_to`, optional `reason`/`notes`). Writes `ReferralCreated` timeline + audit.
- `GET /consultations/{id}/referrals` — list referrals for a consultation.
- `POST /consultations/{id}/prescriptions` — create a prescription. Body: `items: [{medicine, generic_name?, brand_name?, strength?, dosage?, frequency?, duration?, quantity?, route?, instructions?, substitution_allowed}]` (at least 1, no upper bound), optional `status` (default `Draft`). Server-generates `prescription_number` (`RX-YYYYMMDD-000001`). Returns `{prescription, warnings}` — `warnings` is a non-blocking array (duplicate medicine, missing dosage, missing duration); the save always succeeds regardless of warnings. Writes `PrescriptionCreated` timeline + audit.
- `GET /consultations/{id}/prescriptions` — list prescriptions for a consultation.
- `GET /visits/{id}/orders` / `GET /visits/{id}/procedures` / `GET /visits/{id}/referrals` / `GET /visits/{id}/prescriptions` — read-only lists for the Visit Details page's tabs.
- `GET /patients/{id}/prescriptions` — read-only list for the Patient Profile's Prescriptions view.
- `GET /laboratory/orders?visit_id=` — Laboratory role endpoint, server-side filtered to `order_category=Laboratory` only; `visit_id` is required in this phase (a clinic-wide Laboratory worklist is out of scope until a future Laboratory-processing phase).

Not implemented in this phase (explicitly out of scope): lab/radiology *result entry*, specimen tracking, prescription printing/dispensing, real allergy-conflict checking (`check_allergy_conflicts()` is an architecture-only placeholder returning `[]`).

---

## Error Response Shape

All error responses (from any endpoint) share a consistent shape:

```json
{
  "error": {
    "code": "invalid_credentials",
    "message": "Email or password is incorrect.",
    "details": null
  }
}
```

Validation errors (`422`) include field-level detail:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": [
      { "field": "email", "message": "value is not a valid email address" }
    ]
  }
}
```

---

## Billing & Cashier (Phase 9)

All routes below are prefixed `/api/v1` and require a bearer token + tenant context, same as every other module. Role gating: Cashier/Owner/Administrator manage; Doctor view-only; Receptionist read-only (reads succeed, writes 403); Administrator/Owner-only for refund endpoints.

| Method | Path | Notes |
|---|---|---|
| `POST` | `/consultations/{consultation_id}/invoice` | Mostly internal/test trigger — the real trigger is consultation completion (`ConsultationService.complete_consultation()` calls the same idempotent creation path). Manage roles only. |
| `GET` | `/invoices` | Search/filter by `q` (invoice #/receipt #/patient/visit #/doctor/payment reference), `status`, `date_from`/`date_to`, `cashier_id`, paginated (`limit`/`offset`). |
| `GET` | `/invoices/{invoice_id}` | Full invoice detail with items/discounts/payments. |
| `GET` | `/visits/{visit_id}/invoice` | The (usually auto-created) invoice for a visit, or `null`. |
| `GET` | `/patients/{patient_id}/billing-history` | Patient's invoice history (for the Patient Profile "Billing History" tab). |
| `POST` | `/invoices/{invoice_id}/items` | Add a line item. Draft/PendingPayment invoices only. Manage roles only. |
| `PATCH` | `/invoices/{invoice_id}/items/{item_id}` | Edit a line item. Same status restriction. Manage roles only. |
| `DELETE` | `/invoices/{invoice_id}/items/{item_id}` | Remove a line item; invoice reverts to Draft if it becomes empty. Manage roles only. |
| `POST` | `/invoices/{invoice_id}/discounts` | Apply an invoice-level discount (SeniorCitizen/PWD/Employee/Custom, Percentage/FixedAmount); records the approver as the acting user. Manage roles only. |
| `POST` | `/invoices/{invoice_id}/payments` | Record a payment — body is `{"payments": [{payment_method, amount, reference_number?}, ...]}`, supporting split payments as multiple entries in one call. Manage roles only. |
| `POST` | `/payments/{payment_id}/void` | Void a payment; invoice status/amounts recompute backward. Manage roles only. |
| `POST` | `/payments/{payment_id}/refund` | Architecture-only stub — creates a Pending `Refund` row. Administrator/Owner only, no UI. |
| `POST` | `/refunds/{refund_id}/approve` | Architecture-only stub — flips a `Refund` to Approved. Administrator/Owner only, no UI. |
| `GET` | `/invoices/{invoice_id}/receipt` | Computed printable receipt payload (not a persisted resource). |
| `POST` | `/invoices/{invoice_id}/receipt/print` | Same payload, plus records an `invoice.receipt_printed` audit entry. |
| `GET` | `/billing/dashboard` | Cashier Dashboard stats: Pending Payments, Paid Today, Today's Revenue, Outstanding Balance, Refunds Pending, Recent Payments. |

---

## Laboratory Management (Phase 10)

All routes below are prefixed `/api/v1` and require a bearer token + tenant context. Role gating: Owner/Administrator/Laboratory manage the collect→process→enter-results→release→cancel workflow; Doctor and Receptionist are read-only (they still create Laboratory-category orders via the unchanged Phase 9 `POST /consultations/{id}/orders`); Administrator/Owner-only for template mutation.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/laboratory/dashboard` | Stat cards: Pending, Collected, Processing, Completed Today, STAT Orders, Cancelled — real computed counts. |
| `GET` | `/laboratory/orders` | Worklist. Omit `visit_id` for the full clinic worklist (Laboratory Dashboard); pass `visit_id` to scope to one visit (also used by the Visit Details Laboratory tab). Supersedes the Phase 9 placeholder of the same path that lived in `clinical_orders.py`. |
| `GET` | `/laboratory/orders/{laboratory_order_id}` | Full detail including results and attachments. |
| `POST` | `/laboratory/orders/{laboratory_order_id}/collect` | `Requested → Collected`. Manage roles only. |
| `POST` | `/laboratory/orders/{laboratory_order_id}/start-processing` | `Collected → Processing`. Manage roles only. |
| `POST` | `/laboratory/orders/{laboratory_order_id}/results` | Upsert (replace-all) result parameters; body `{"results": [{parameter_name, result_type, numeric_value?, text_value?, normal_range?, units?, interpretation?, remarks?}, ...]}`. First call advances status to `Completed` and fires the idempotent billing sync if the order is template-priced. Manage roles only. |
| `POST` | `/laboratory/orders/{laboratory_order_id}/release` | `Completed → Released` — the step that makes results final/visible to the doctor and patient history. Manage roles only. |
| `POST` | `/laboratory/orders/{laboratory_order_id}/cancel` | `→ Cancelled` from any non-terminal state. Manage roles only. |
| `POST` | `/laboratory/orders/{laboratory_order_id}/attachments` | Presigned-URL-stub upload record (PDFReport/Image/ScannedResult). Manage roles only. |
| `GET` | `/laboratory/orders/{laboratory_order_id}/attachments` | List attachments for an order. |
| `GET` | `/laboratory/templates` | List test templates (`?active_only=true` to filter). Broadly readable. |
| `POST` | `/laboratory/templates` | Create a test template with nested `parameters`. Administrator/Owner only. |
| `PATCH` | `/laboratory/templates/{template_id}` | Partial update, including replacing the `parameters` list. Administrator/Owner only. |
| `GET` | `/visits/{visit_id}/laboratory` | All laboratory orders for a visit (Visit Details Laboratory tab). |
| `GET` | `/patients/{patient_id}/laboratory` | All laboratory orders for a patient across visits (Patient Profile Laboratory tab). |

### Phase 11: Appointment Management

| Method | Path | Notes |
| --- | --- | --- |
| `POST` | `/appointments` | Create, slot-validated (rejects double-booking/outside-hours/lunch-break/holiday/blocked-date). Reception/Owner/Administrator. |
| `GET` | `/appointments` | Search/filter by patient/doctor/branch/department/status/type/date-range, paginated. |
| `GET` | `/appointments/calendar` | Same search, tuned for calendar views (date-range required, larger page size). |
| `GET` | `/appointments/dashboard/reception` | Today's Schedule / No-shows / Checked-in / Upcoming, for the Reception Dashboard. |
| `GET` | `/appointments/dashboard/doctor` | A doctor's today: Scheduled / Checked-in / Completed. |
| `GET` | `/appointments/{id}` | Full detail incl. denormalized names + history. |
| `GET` | `/appointments/{id}/history` | Domain audit trail (Created/Confirmed/Rescheduled/Cancelled/CheckedIn/Completed/NoShow). |
| `POST` | `/appointments/{id}/notes` | Free-text note, distinct from the reschedule reason. |
| `PATCH` | `/appointments/{id}/confirm` | `Booked → Confirmed`. Reception/Owner/Administrator. |
| `PATCH` | `/appointments/{id}/reschedule` | Validates the new slot, creates a new `Booked` row, marks the original `Rescheduled` (history records old/new date-time on both rows). Reception/Owner/Administrator. |
| `PATCH` | `/appointments/{id}/cancel` | `→ Cancelled`; offers the freed slot to the oldest matching waitlist entry. Reception/Owner/Administrator. |
| `POST` | `/appointments/{id}/check-in` | **The critical endpoint** — calls the existing `QueueService.create_queue()` to create a real linked Queue ticket + Visit; sets `queue_id`/`visit_id`. Reception/Owner/Administrator. |
| `PATCH` | `/appointments/{id}/complete` | `→ Completed`. Doctor/Owner/Administrator. |
| `PATCH` | `/appointments/{id}/no-show` | `→ NoShow`. Reception/Owner/Administrator. |
| `GET` | `/doctors/{doctor_id}/schedule` | Weekly working-hours days + vacation/blocked-date list. |
| `PUT` | `/doctors/{doctor_id}/schedule` | Replaces the doctor's recurring weekly schedule wholesale. Administrator/Owner only. |
| `POST` | `/doctors/{doctor_id}/schedule/blocks` | Add a vacation/blocked date. Administrator/Owner only. |
| `DELETE` | `/doctors/{doctor_id}/schedule/blocks/{block_id}` | Remove a block. Administrator/Owner only. |
| `GET` | `/doctors/{doctor_id}/available-slots?date=` | The Time Slot Engine's public interface — computed, not persisted. |
| `GET` | `/patients/{patient_id}/appointments` | Upcoming/Completed/Cancelled/NoShow buckets, for the Patient Profile Appointments tab. |

---

## Phase 12: Owner Dashboard & Reports

Every endpoint below is under `/api/v1/analytics` and gated by `require_analytics_role` — **Owner and Administrator only**, every other role (including Doctor/Cashier/Receptionist/Laboratory) gets `403` on all of them. All are read-only aggregation over existing tables (see `docs/DATABASE.md`'s Phase 12 section for which repository owns each metric) except the export endpoint, which also writes one `audit_logs` "report generated" row. Every report endpoint accepts `date_range` (`today` default | `yesterday` | `last_7_days` | `this_month` | `last_month` | `custom` — `custom` requires `start`/`end`, `YYYY-MM-DD`, else `400`).

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/analytics/dashboard` | The 16-stat Owner Dashboard payload (Patients/New Patients/Appointments/Walk-ins/Completed Consultations/Cancelled Visits/No Shows/Laboratory Orders/Prescriptions Issued/Pending Payments/Collected Revenue/Outstanding Balance/Avg Waiting Time/Avg Consultation Time/Doctors On Duty/Rooms In Use — today only, no filters). |
| `GET` | `/analytics/activity-feed?limit=` | Merges `visit_timeline_events` + `queue_status_history` + `audit_logs`, sorted descending, default `limit=50` (max 200). |
| `GET` | `/analytics/alerts` | Live threshold checks: High Queue Volume (>10 waiting), Long Waiting Time (>30 min), Outstanding Payments (>30 days overdue) — computed on request, not persisted notifications. System Errors/Failed Backups are explicitly out of scope (no infra monitoring exists yet). |
| `GET` | `/analytics/reports/patients` | New/Returning Patients, Daily/Monthly Census, Age/Gender Distribution. |
| `GET` | `/analytics/reports/doctors` | Per-doctor Patients Seen/Completed/Cancelled/Avg Consultation Time/Revenue Generated/Appointment Utilization. |
| `GET` | `/analytics/reports/revenue` | Total + by Doctor/Branch/Service/Payment Method, daily trend, Outstanding Invoices, Discount Summary. |
| `GET` | `/analytics/reports/queue` | Avg/Longest Waiting Time, Completed/Cancelled counts, Volume by Hour. |
| `GET` | `/analytics/reports/laboratory` | Orders Today/Completed/Pending, Avg Turnaround Time, Top Requested Tests, daily volume. |
| `GET` | `/analytics/reports/appointments` | Bookings/Completed/Cancelled/NoShow/Rescheduled, per-doctor utilization, daily trend. |
| `GET` | `/analytics/reports/{report}/export?format=csv\|excel\|pdf` | `report` is one of `patients`/`doctors`/`revenue`/`queue`/`laboratory`/`appointments`. `csv`/`excel` both return a real CSV body (Excel-compatible, no `openpyxl` dependency added for this phase) as a file download. `pdf` returns `501 Not Implemented` — an explicit architecture-only stub per the spec's "do not implement PDF styling yet". |

All `/analytics/reports/*` (including `/export`) also accept optional `doctor_id` for doctor-scoped filtering where the underlying query supports it.

---

## Phase 13: Live TV Queue Display

Two distinct security models on this feature's endpoints:

- `/tv-displays*` and `/announcements/*` are standard JWT-protected. Read (`GET`) uses `require_config_view_role` (broad — every operational role); create/update/delete use `require_config_manage_role` (**Owner/Administrator only**), the same gate reused from Phase 4's Clinic Configuration modules.
- `GET /public/tv-display/{public_slug}` takes **no authentication of any kind** — not even an optional bearer token is read. See `docs/DATABASE.md`'s Phase 13 section for the full security-model rationale. **This is safe to expose fully unauthenticated because the response only ever contains**: queue number, patient initials (never a full name), doctor name, room (currently always `null`, pending a future Queue↔ConsultationRoom link), clinic/branch name, and announcement text — never a full patient name, contact info, date of birth, or any clinical/billing data.

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| `POST` | `/tv-displays` | Owner/Administrator | Create a display config. `is_public: true` auto-generates a unique `public_slug` (192-bit `secrets.token_urlsafe`). |
| `GET` | `/tv-displays` | Any clinic role | List the clinic's configured displays. |
| `GET` | `/tv-displays/{id}` | Any clinic role | Single config detail. |
| `PATCH` | `/tv-displays/{id}` | Owner/Administrator | Update any field (theme/font/queue-size/animation/refresh-interval/logo/colors/scope/`is_active`). Toggling `is_public` to `true` on a config with no existing slug mints one; toggling it off keeps the slug on file (so re-enabling doesn't change a previously printed/posted URL) but it stops resolving publicly. |
| `DELETE` | `/tv-displays/{id}` | Owner/Administrator | Soft-delete; its public URL (if any) stops resolving immediately. |
| `GET` | `/tv-displays/{id}/preview` | Any clinic role | Authenticated equivalent of the public snapshot endpoint — same `TvDisplayData` shape — so staff can preview/use a private-mode display without needing its public slug. |
| `POST` | `/tv-displays/{id}/announcements` | Owner/Administrator | Create an announcement scoped to this display. |
| `GET` | `/tv-displays/{id}/announcements` | Any clinic role | List announcements scoped to this display (does not include clinic-wide ones — those are merged into the display payload itself, not this list). |
| `PATCH` | `/announcements/{id}` | Owner/Administrator | Update message/type/order/active/date-range. |
| `DELETE` | `/announcements/{id}` | Owner/Administrator | Soft-delete. |
| `GET` | `/public/tv-display/{public_slug}` | **None** | Now Serving + Next `queue_size` Waiting (`ACTIVE_QUEUE_STATUSES` only — Completed/Cancelled/Skipped/NoShow never appear) + active announcements + clinic/branch name + display settings. Unknown/private/inactive slug → `404`, never a `500` or another clinic's data. |

Every config/announcement create/update/delete writes an `audit_logs` entry (`tv_display.config_created`/`config_updated`/`config_deleted`/`announcement_created`/`announcement_updated`/`announcement_deleted`).

**Post-RC1 (Multi-Department/Multi-Doctor TV Queue Display)**: `TvDisplayNowServing` and `TvDisplayWaitingEntry` (both `GET /public/tv-display/{public_slug}` and `GET /tv-displays/{id}/preview` share the same shape) each gained two additive fields — `department_id: UUID | null` and `department_name: string | null` — alongside the existing `doctor_name`. No existing field was removed or renamed. A config with `branch_id`/`department_id`/`doctor_id` all `null` (create one via `POST /tv-displays` with no scope fields) returns the full multi-department feed for the clinic — confirmed live: calling four different-prefix tickets (a Doctor A ticket, a Doctor B ticket, a Laboratory ticket, a Radiology ticket) simultaneously all appeared together in one `now_serving` array, each correctly labeled via `doctor_name` (when assigned) or `department_name` (department-only tickets, e.g. Laboratory/Radiology).

### Post-RC1: 50/50 Queue + Information/Advertisement Panel

New, clinic-wide (not per-display) `/tv-info-content` endpoints, feeding the right half of the redesigned TV Display. Uses the exact same two role gates as the rest of this feature: `require_config_manage_role` (Owner/Administrator) for writes, `require_config_view_role` (broad clinic roles) for reads.

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| `POST` | `/tv-info-content` | Owner/Administrator | Create a content item — `title`, `body`, `content_type` (`ServicePricing`/`DoctorInfo`/`HealthTip`/`PreventiveReminder`/`Announcement`/`Promotion`/`Motivational`), `duration_seconds` (3–120, default 10), `display_order`, `is_active`, optional `image_url`. |
| `GET` | `/tv-info-content` | Any clinic role | List all of the clinic's content items (active and inactive), ordered by `display_order`. |
| `PATCH` | `/tv-info-content/{id}` | Owner/Administrator | Partial update, any field. |
| `DELETE` | `/tv-info-content/{id}` | Owner/Administrator | Soft-delete. |
| `POST` | `/tv-info-content/{id}/image` | Owner/Administrator | Multipart image upload (`file` field) — one of the few endpoints in this codebase that relays real file bytes rather than minting a presigned-URL stub (see `docs/DATABASE.md`). Validates extension (`.jpg`/`.jpeg`/`.png`/`.webp`) and size (5 MB max) against the actual uploaded bytes, writes to local disk, sets `image_url` to a relative path served back via a `StaticFiles` mount at `/media/tv-info-content/{clinic_id}/{file}` (**unauthenticated**, same security posture as the public TV display itself — see below), and returns the updated item. Re-uploading replaces the previous file. |
| `DELETE` | `/tv-info-content/{id}/image` | Owner/Administrator | Deletes the stored file (if any) and clears `image_url` back to `null`. |

`TvDisplayData` (both the public snapshot and the authenticated preview) gained one additive field: `info_content: TvInfoContentRead[]` — active-only, ordered by `display_order`. An empty array (no active content, or none configured) is a valid, expected response — the frontend's Information Panel renders a "No information to display" state rather than erroring. `image_url` on each item is a **relative** path (e.g. `/media/tv-info-content/{clinic_id}/{file}`), not an absolute URL — the backend has no configured public base URL, so the frontend resolves it against the API origin at render time (`resolveTvMediaUrl()` in `frontend/src/features/tv-display/api/tv-display-api.ts`). Every content/image create/update/delete writes an `audit_logs` entry (`tv_display.info_content_created`/`info_content_updated`/`info_content_deleted`/`info_content_image_updated`).

### Post-RC1: Short TV Display URL (`short_code`)

`POST`/`PATCH /tv-displays{,/{id}}` gained an optional `short_code` field — an admin-chosen, short human-typeable alias for the display's public URL (e.g. `"canora"`, so `GET /public/tv-display/canora` resolves the same row as `GET /public/tv-display/{public_slug}`), meant for entering a URL on a Smart TV remote where the 32-character `public_slug` is impractical to type. `null`/omitted (the default) means no short URL is configured — the long `public_slug` URL is completely unaffected either way, and pre-existing displays keep working exactly as before.

- **Format**: 2–32 characters, lowercase letters/digits/hyphens only (`^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$`), normalized to lowercase server-side so `/tv/Canora` and `/tv/canora` are equivalent. Not auto-generated, unlike `public_slug` — the admin types it.
- **Uniqueness**: enforced clinic-wide-unique via a DB unique index (same posture as `public_slug`), not scoped per-clinic — two clinics on the same instance cannot pick the same short code. A conflicting `short_code` on create/update returns `409 Conflict`.
- **Resolution**: `GET /public/tv-display/{public_slug}` now tries a `public_slug` match first and, only if that misses, falls back to a `short_code` match — the exact same `is_public=True, is_active=True, is_deleted=False` filters apply either way, so a short code is never a separate or weaker access-control path onto the row, just an additional lookup key. Disabling a display (`is_active=false`) or making it private stops the short code from resolving too, identically to `public_slug`.
- **Security tradeoff, disclosed rather than silent**: a short code is inherently far more guessable than the 192-bit `public_slug`. This is mitigated by (a) it being an explicit admin opt-in per display, same posture as `is_public` itself, and (b) the endpoint now being rate-limited per client IP (`RATE_LIMIT_TV_PUBLIC_MAX_ATTEMPTS`/`_WINDOW_SECONDS`, default 60 requests/60s) to blunt brute-force enumeration — generous enough that a real TV's 30s poll + WS-reconnect-with-backoff never trips it. See `docs/DATABASE.md`'s section on this column for the full rationale.
- **WebSocket unaffected**: the public snapshot response's `ws_auth_slug` field always carries the row's real `public_slug`, never the short code — the frontend (`use-tv-display-realtime.ts`) uses that resolved value, not whatever was typed in the URL, to open the `/ws/queues/{clinic_id}` connection. `ws_queues.py`'s WS auth path was not touched at all by this feature; it still only ever accepts the true high-entropy slug, exactly as before.

---

## Legacy Migration Wizard (Phase 14)

**Every endpoint under `/migration` is Owner/Administrator only** (`require_migration_role`) — the same strictest gate as Phase 12 Analytics; every other role gets `403` on every route, including `GET /migration/batches` (list/history).

| Method | Path | Notes |
| --- | --- | --- |
| `POST` | `/migration/batches` | Create a batch (`source_type`, `source_description`). Starts in `Draft`. |
| `GET` | `/migration/batches` | Migration History — list this clinic's batches, newest first. |
| `POST` | `/migration/batches/{id}/upload` | Multipart file upload (`files[]`) — CSV: one file per entity (filename stem matched case-insensitively to an entity type, e.g. `patients.csv`); Excel: first uploaded file is treated as the workbook. Only works for `source_type` CSV/Excel (`400` otherwise — the other source types have no working connect path in this build). Sets status → `Connected`. |
| `POST` | `/migration/batches/{id}/analyze` | Loads the adapter, detects entity types + source columns, sets `total_records_found`, status → `Analyzed`. Returns `{entity_type: [source_column, ...]}`. |
| `GET` | `/migration/batches/{id}/mappings/suggest?entity_type=Patients` | Re-reads the source schema for one entity and returns fuzzy/synonym-matched suggested mappings (source field, suggested destination field or `null`, `is_ignored`) — does not persist anything. |
| `GET` | `/migration/batches/{id}/mappings` | List saved `migration_field_mappings` rows for this batch. |
| `PUT` | `/migration/batches/{id}/mappings` | Replace all mappings for this batch (full-replace, not per-entity patch) — body `{"mappings": [...]}`. |
| `POST` | `/migration/batches/{id}/validate?entity_type=Patients` | Runs validation for one entity type, replacing any previously-persisted issues for that entity, writes `migration_validation_issues`, updates the batch's `total_warnings`/`total_errors`, status → `Validated`. Returns the issue list. |
| `POST` | `/migration/batches/{id}/preview?entity_type=Patients` | Computes rows-to-import/rows-to-skip/warnings/errors for one entity (runs validation first if it hasn't been run yet for that entity), writes nothing to destination tables, status → `Previewed`. |
| `PATCH` | `/migration/batches/{id}/issues/{issue_id}/resolve` | Set a validation issue's `resolution` (`Skip`/`Merge`/`Overwrite`/`CreateNew`). |
| `POST` | `/migration/batches/{id}/import` | Kicks off the import as a `BackgroundTasks` job (returns immediately, status → `Importing`) — processes the 17-step entity order in 500-row batched transactions. **Confirm clearly in the UI before calling this** — it writes real rows. |
| `POST` | `/migration/batches/{id}/resume` | Identical operation to `import` — every entity's own `last_processed_offset` makes re-running the same batch naturally pick up where it left off (or skip instantly if already `Completed`). |
| `POST` | `/migration/batches/{id}/retry-batch?entity_type=Patients` | Resets one entity's progress to `Pending`/offset 0 and re-triggers the background import — safe due to the `legacy_id`+`migration_batch_id` idempotency check even though it forces a full re-scan of that entity's rows. |
| `GET` | `/migration/batches/{id}/status` | Polling endpoint for the Migration Dashboard — batch summary + per-entity progress + `elapsed_seconds` + `estimated_seconds_remaining` (computed from current throughput). Frontend polls this every 2s while `Importing`, stops on a terminal status. |
| `POST` | `/migration/batches/{id}/cancel` | Marks the batch `Cancelled`; the background loop checks batch status before starting each entity and stops early. |
| `GET` | `/migration/batches/{id}/verify` | Computed-on-demand Verification Report: expected vs. imported counts per entity, `overall_ok`. |
| `GET` | `/migration/batches/{id}/logs` | The detailed operational log (`migration_logs`), distinct from the summary counters on the batch itself. |

Every batch lifecycle event (create/upload/analyze/validate/import-complete) and every entity-completion writes to both `migration_logs` (detailed) and `audit_logs` (`migration.batch_created`/`migration.batch_completed`).

**Tenant isolation**: every route resolves the batch via `WHERE id = ? AND clinic_id = ?` — a batch ID from another clinic 404s rather than leaking existence.

---

## Phase 15: SaaS Administration Portal (`/api/v1/platform-admin/*`)

**Separate auth requirement — read this before calling any endpoint below.** Every route in this section requires a Platform Administrator bearer token obtained from `POST /platform-admin/auth/login`, NOT a regular clinic-user token from `POST /auth/login`. The two token types are structurally different (see `docs/ARCHITECTURE.md` §7) — a clinic-user token gets a clean `401` on every route below, and conversely a platform-admin token gets a clean `401` on every existing clinic-scoped route (`/patients`, `/users`, etc.). There is no endpoint that accepts either token type.

### Auth

| Method | Path | Notes |
|---|---|---|
| `POST` | `/platform-admin/auth/login` | Body: `{identifier, password}`. Returns `{access_token, refresh_token, platform_admin_id, role}` — note the refresh token is returned in the JSON body (not a cookie), unlike the clinic portal's login. |
| `POST` | `/platform-admin/auth/refresh` | Body: `{refresh_token}`. |
| `POST` | `/platform-admin/auth/logout` | Requires platform-admin bearer token. |
| `GET` | `/platform-admin/auth/me` | Current platform admin's profile. |

### Dashboard

| Method | Path | Notes |
|---|---|---|
| `GET` | `/platform-admin/dashboard/health` | System Health stat grid — real aggregation: total/active/suspended clinics, trial/expired subscriptions, online users (live `refresh_tokens` count), `pg_database_size()`, background job totals. `api_requests_today` is `null` — no request-logging middleware exists yet (documented TODO, not fake data). |

### Tenant (clinic) management — the cross-tenant surface

| Method | Path | Notes |
|---|---|---|
| `GET` | `/platform-admin/tenants` | `?search=&status=&page=&page_size=`. Searches name/slug/email. **This is the endpoint that proves cross-tenant visibility** — returns every clinic, not scoped to any one tenant. |
| `GET` | `/platform-admin/tenants/{clinic_id}` | Single tenant detail. |
| `GET` | `/platform-admin/tenants/{clinic_id}/stats` | Real-time aggregation: user count, storage bytes (sum of consultation + laboratory attachment file sizes), current subscription plan/status. |
| `POST` | `/platform-admin/tenants` | Create a new tenant clinic (ImplementationTeam/PlatformAdministrator only). |
| `POST` | `/platform-admin/tenants/{clinic_id}/suspend` | Body: `{reason}`. Sets `status=Suspended`, revokes every user's refresh tokens in that clinic (force-logout), and blocks future logins for that clinic (`AuthService.login` checks `clinic.status`). |
| `POST` | `/platform-admin/tenants/{clinic_id}/reactivate` | Sets `status=Active`, clears suspension fields, restores login. |
| `POST` | `/platform-admin/tenants/{clinic_id}/archive` | Sets `status=Archived` (also blocks login, same as Suspended). |

### Subscription management

| Method | Path | Notes |
|---|---|---|
| `GET` / `PUT` | `/platform-admin/tenants/{clinic_id}/subscription` | `PUT` body: any subset of `plan`/`status`/`trial_start`/`trial_end`/`subscription_start`/`renewal_date`/`expiration_date`/`max_users`/`max_branches`/`storage_limit_mb`/`api_rate_limit`. Manually-editable records — no automated billing. |

### Feature flags

| Method | Path | Notes |
|---|---|---|
| `GET` | `/platform-admin/tenants/{clinic_id}/feature-flags` | Returns all 8 known keys (defaults to enabled if no row exists yet). |
| `PUT` | `/platform-admin/tenants/{clinic_id}/feature-flags` | Body: `{feature_key, is_enabled}`. Only `"appointments"` is actually consumed by clinic-facing code (proof-of-concept nav-visibility check) — the other 7 keys are real and toggleable but not yet wired into their modules. |

### Tenant user administration

| Method | Path | Notes |
|---|---|---|
| `GET` | `/platform-admin/tenants/{clinic_id}/users` | List a tenant's own staff accounts. |
| `POST` | `/platform-admin/tenants/{clinic_id}/users/{user_id}/reset-password` | Body: `{new_password}`. Also revokes all of that user's refresh tokens. |
| `POST` | `/platform-admin/tenants/{clinic_id}/users/{user_id}/lock` / `/unlock` | Reuses Phase 2's `UserStatus.LOCKED`. |
| `POST` | `/platform-admin/tenants/{clinic_id}/users/{user_id}/force-logout` | Revokes every refresh token for that user — verified in tests to actually invalidate the session. |

### Background jobs, audit log, platform users

| Method | Path | Notes |
|---|---|---|
| `GET` | `/platform-admin/background-jobs` | Surfaces real `background_jobs` rows plus Phase 14's `migration_batches` mapped into the same shape — no fake job system. |
| `GET` | `/platform-admin/audit-logs` | `?clinic_id=&action=&limit=`. Every write above logs here. |
| `GET` / `POST` | `/platform-admin/platform-users` | PlatformAdministrator-only (create/list platform staff accounts). |

### Role gating summary

Auditor is read-only on every route above (view endpoints only). SupportEngineer can additionally manage tenant users. ImplementationTeam can additionally manage tenants/subscriptions/flags. PlatformAdministrator can do everything, including manage platform users. See `app/core/dependencies.py`'s `PLATFORM_ADMIN_*_ROLES` sets and `docs/ARCHITECTURE.md` §7.3 for the full matrix.

---

## Phase 16: Production Hardening — infra probes, error envelope, backups

### Health / readiness / liveness probes

No auth required on any of these three — they're infra probes, never end-user or clinic-session traffic.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | Original combined check, unchanged (`{"status": "ok"}`), kept for backward compatibility. |
| `GET` | `/live` | Liveness: process is up and can answer HTTP at all. Zero dependencies (no DB call) - a container orchestrator restarts the process on failure here, so it must never depend on anything that could be transiently slow/down. Returns `{"status": "alive", "uptime_seconds": <float>}`. |
| `GET` | `/ready` | Readiness: process is up AND the database is actually reachable (`SELECT 1` via a real session). Returns `200 {"status": "ready", "database": "reachable"}` when healthy, or `503 {"status": "not_ready", "database": "unreachable", "detail": "..."}` when the DB can't be reached - a load balancer/orchestrator stops routing traffic here without restarting the process (that's `/live`'s job). |

### Standardized error envelope

Every error response across the API - `HTTPException`, a Pydantic validation error (`422`), or an unhandled `500` - now has the same shape:

```json
{ "detail": "...", "request_id": "3ac381b6-748b-4a59-92ed-7ad13ef26930" }
```

`detail` was already consistent across the codebase before this phase (FastAPI's own default shape, confirmed via a grep of every `HTTPException(` call site - none of ~40 route modules used an ad-hoc alternative shape). What Phase 16 actually added is `request_id` on every error body, matching the `X-Request-ID` response header (see below) - so a user-reported error (screenshot of a toast, a support ticket quoting the JSON body) can be matched to the exact server-side structured log line for that request.

For a `422` validation error, `detail` is still FastAPI's array-of-field-errors shape (`[{"type": ..., "loc": [...], "msg": ...}, ...]`) - unchanged, just with `request_id` alongside it.

### Request-ID tracing

Every request gets a UUID (reused from an inbound `X-Request-ID` header if the caller already set one, e.g. from an upstream gateway) - available as `request.state.request_id` to any handler/service, included in the structured JSON log line for that request (`app/middleware/request_logging.py`), and returned as an `X-Request-ID` response header on every response, success or error.

### Backup verification

| Method | Path | Notes |
|---|---|---|
| `POST` | `/platform-admin/backups` | PlatformAdministrator-only. Runs a real `pg_dump` against the live database (`app/services/backup_service.py`), verifies the resulting file is non-empty and starts with the real PostgreSQL dump preamble, and records a real `backups` row (`Completed` with `file_size_bytes`/`storage_location`, or `Failed` with `error_message`). |
| `GET` | `/platform-admin/backups` | Lists recent backup attempts (Owner/Administrator/Auditor view access). |

Restore is intentionally NOT exposed via any endpoint - see `docs/BACKUP.md` for the human-executable restore procedure.

---

## Phase 18: Patient Portal (`/api/v1/patient-portal/*`)

**Separate auth requirement — read this before calling any endpoint below.** Every non-auth route requires a patient bearer token obtained from `POST /patient-portal/auth/login`, NOT a clinic-user token (`/auth/login`) or a platform-admin token (`/platform-admin/auth/login`). All three token types are structurally different (distinct `type` JWT claim) — a patient token gets a clean `401` on every clinic-staff or platform-admin route, and vice versa. Every query below is scoped by `patient_id` + `clinic_id` taken from the verified token, never from a path/query/body parameter.

### Auth

| Method | Path | Notes |
|---|---|---|
| `POST` | `/patient-portal/auth/login` | Body: `{identifier, password}` — `identifier` is the patient's email OR mobile number. Returns `{access_token, refresh_token, token_type, patient_id}`. |
| `POST` | `/patient-portal/auth/refresh` | Body: `{refresh_token}`. |
| `POST` | `/patient-portal/auth/forgot-password` | Body: `{identifier}`. Always `202`, never reveals whether an account exists. |
| `POST` | `/patient-portal/auth/reset-password` | Body: `{token, new_password}`. |
| `POST` | `/patient-portal/auth/change-password` | Requires patient bearer token. Body: `{old_password, new_password}`. Audit-logged (`patient.password_change`). |

### Profile

| Method | Path | Notes |
|---|---|---|
| `GET` / `PUT` | `/patient-portal/profile` | `PUT` accepts any subset of contact-info fields (mobile/telephone/email/address/emergency contact). Every write is audit-logged (`patient.profile_update`). |
| `POST` | `/patient-portal/profile/photo` | Presigned-URL stub, same pattern as clinic-staff Patient Management's photo upload (`PatientService.request_photo_upload_url`) — no real file storage wired up in this dev sandbox. |
| `GET` / `PUT` | `/patient-portal/notification-preferences` | Simple boolean toggles (appointment reminders / lab alerts / billing notices / clinic announcements) — in-app only, no real delivery. |

### Dashboard

| Method | Path | Notes |
|---|---|---|
| `GET` | `/patient-portal/dashboard` | Aggregates upcoming appointments, recent visits, outstanding balance, latest released lab results, recent prescriptions, and a static announcements placeholder. |

### Appointments

| Method | Path | Notes |
|---|---|---|
| `GET` | `/patient-portal/appointments` | `?tab=upcoming\|completed\|cancelled\|rescheduled` (omit for all). Reuses the existing `Appointment` model, scoped to the caller's own `patient_id`/`clinic_id`. Includes `doctor_id` (added Phase 19, for the reschedule flow's slot lookup). |
| `GET` | `/patient-portal/appointments/branches` | Patient-safe read-only projection (id/name/address) of active branches. Not a copy of the staff `branches.py` endpoint (which is `require_config_view_role`-gated and returns richer staff-internal fields). |
| `GET` | `/patient-portal/appointments/departments` | Patient-safe read-only projection of active departments. |
| `GET` | `/patient-portal/appointments/doctors` | `?branch_id=&department_id=` (both optional). A doctor with `branch_id`/`department_id = NULL` (meaning "any branch/department") is always included, matching how `TimeSlotService` itself ignores those fields — see `docs/BUGS.md` BUG-010. |
| `GET` | `/patient-portal/appointments/availability` | `?doctor_id=&date_from=&date_to=&branch_id=` (branch_id optional). Returns which dates in the range have at least one open slot, respecting the doctor's schedule/breaks/blocked dates/holidays/max-daily-patients (Phase 11) — calls the SAME `TimeSlotService` staff booking uses. Range capped at 60 days. |
| `GET` | `/patient-portal/appointments/availability/{date}` | `?doctor_id=&branch_id=` (branch_id optional). Returns the open time slots for one date. |
| `POST` | `/patient-portal/appointments` | Creates an appointment. Validated by the exact same rules as staff booking (no past dates, no double-booking, no outside-hours/break/holiday/blocked-schedule/over-max-daily) via `TimeSlotService.validate_slot` + `AppointmentRepository.has_conflicting_booking`, with the real DB-level guarantee being the partial unique index `uq_appointments_doctor_slot_active` — a losing concurrent request gets a clean `409`, never a raw `500`. `patient_id` is always taken from the verified JWT, never the request body. Generates a reference number via the existing `AppointmentNumberGenerator` (`APT-YYYYMMDD-000001`). |
| `PATCH` | `/patient-portal/appointments/{id}/reschedule` | `404` (not `403`) if the appointment doesn't belong to the caller — never leaks existence of another patient's appointment. Same slot validation and concurrency guarantee as create. |
| `POST` | `/patient-portal/appointments/{id}/cancel` | `404` if not the caller's appointment. Offers the freed slot to the next matching waitlist entry (Phase 11's `WaitlistService`, unchanged). |

### Laboratory (Released results only)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/patient-portal/laboratory` | Only `LaboratoryOrderStatus.RELEASED` orders — Requested/Collected/Processing/Completed are never returned. |
| `GET` | `/patient-portal/laboratory/{lab_order_id}` | `404` (never another patient's data) if the order doesn't belong to the caller or isn't Released. |
| `GET` | `/patient-portal/laboratory/{lab_order_id}/pdf` | `501` placeholder — no existing lab-result PDF/export mechanism exists to reuse this phase. |

### Prescriptions (read-only)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/patient-portal/prescriptions` | Every item's dosage/frequency/duration/instructions; `is_current` flags `PrescriptionStatus.FINALIZED` rows. |

### Medical records (read-only, patient-visible only)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/patient-portal/medical-records` | Only diagnoses/attachments with `patient_visible = true` (new columns, default `false`) — a consultation with none is omitted entirely, not shown empty. |

### Billing (read-only)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/patient-portal/billing` | Outstanding balance + every invoice's line items and payment history. Online payment is not implemented (architecture note only). |

### Notifications (in-app feed)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/patient-portal/notifications` | Most recent 100, newest first. |
| `POST` | `/patient-portal/notifications/{notification_id}/read` | Marks read; `404` if it doesn't belong to the caller. |

### Phase 20 — Client Acceptance Revisions

| Method | Path | Notes |
|---|---|---|
| `POST` | `/invoices/{invoice_id}/discounts` | Role gate widened: Receptionist can now apply discounts (was Cashier/Owner/Administrator only). |
| `POST` | `/invoices/{invoice_id}/payments` | Role gate widened: Receptionist can now record payments (was Cashier/Owner/Administrator only). |
| `POST` | `/payments/{payment_id}/void` | Unchanged (Cashier/Owner/Administrator only) — now on its own `require_billing_void_role` dependency rather than sharing `require_billing_manage_role` with the two rows above. |
| `POST` | `/visits/{visit_id}/consultation/open-for-reception` | New. Receptionist/Nurse (and Doctor/Owner/Administrator) opens/resumes a visit's consultation without the Doctor-linkage check and without acquiring the edit lock. |
| `GET` | `/consultations/{consultation_id}/soap/subjective-objective` | New. Field-restricted read — returns only Subjective/Objective/vitals fields, never Assessment/Plan. Same role gate as above. |
| `PUT` | `/consultations/{consultation_id}/soap/subjective-objective` | New. Merge-write of only the submitted Subjective/Objective fields; preserves any existing Assessment/Plan untouched. Same role gate as above. |
| `POST` | `/consultations/{consultation_id}/complete` | Body is now optional `{ "consultation_fee": number }` — lets the Doctor override the auto-created invoice's Consultation Fee line at completion time. Omitting the body preserves prior behavior exactly. |
| `POST` | `/messages` | New. Send an internal message (`recipient_id`, `body`) to another staff user in the same clinic. Any authenticated clinic user. |
| `GET` | `/messages/conversation/{other_user_id}` | New. Every message between the caller and `other_user_id`, oldest first; marks the other party's unread messages to the caller as read as a side effect. |
| `GET` | `/messages/unread-count` | New. Caller's total unread message count across all conversations. |
| `GET` | `/messages/staff-directory` | New. Minimal id/name/role listing of the caller's own clinic's staff (excluding the caller) for the message recipient picker — deliberately not the Administrator/Owner-only `GET /users`. |

### Phase 20 — Client Acceptance Revisions, Round 2

No new endpoints added by this round's Printer Settings, Queue Table sorting, or messaging-badge items (Printer Settings is a client-only `localStorage` preference; sorting is client-side over an existing response; the badge consumes the `GET /messages/unread-count` endpoint above, already added in the prior pass but not yet surfaced in the UI). Two changes below:

| Method | Path | Notes |
|---|---|---|
| `DELETE` | `/invoices/{invoice_id}/discounts/{discount_id}` | New. Removes a previously-applied discount and recalculates the invoice's totals; audit-logged as `invoice.discount_removed`. Gated by the same `require_billing_discount_role` as `POST .../discounts` (now `{Owner, Administrator, Doctor}` — reversed from Receptionist back to Doctor this round; see BUG-019/BUG-020 in `docs/BUGS.md`). |
| `GET` | `/public/tv-display/{public_slug}` | No signature change, but its `now_serving`/`next_waiting` filtering (`TvDisplayService._build_display_data`) was fixed to compute "today" as `datetime.now(UTC).date()` instead of a naive, OS-timezone-dependent `date.today()` — see BUG-020. Same fix applies to `GET /tv-displays/{tv_display_id}/preview` (the authenticated equivalent), which shares the same internal method. |

### Phase 21 — Receptionist Shift Management

| Method | Path | Notes |
|---|---|---|
| `POST` | `/shifts` | New. Starts a shift for the caller (`opening_cash`, optional `branch_id`). Gated by `require_shift_manage_role` (`Owner`/`Administrator`/`Receptionist`). `409` if the caller already has an Open shift. |
| `GET` | `/shifts/current` | New. The caller's own currently-open shift with a live-computed summary (cash/GCash/card/other collections, discounts, refunds, expected cash), or `null`. Same role gate as above. |
| `GET` | `/shifts/{shift_id}` | New. Full shift detail/report. The owning Receptionist, or Owner/Administrator for any shift; `403` for any other Receptionist. |
| `POST` | `/shifts/{shift_id}/close` | New. Takes `actual_cash_count` (+ optional `notes`); computes `expected_cash`/`cash_difference` at that moment and marks the shift Closed. Same ownership rule as `GET /shifts/{id}`. |
| `POST` | `/shifts/{shift_id}/reopen` | New. Reopens a Closed shift. `require_shift_reopen_role` — Owner/Administrator only, never the shift's own Receptionist. |

All four mutating actions above write a real `audit_logs` row (`shift.opened`/`shift.closed`/`shift.reopened`), following the existing `AuditService.log_event` convention.

### Client Acceptance Revisions — Round 3 (items 6-8)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/messages/unread-by-conversation` | New (item 6). Per-conversation-partner unread breakdown for the caller: `[{other_user_id, other_user_name, unread_count, last_message_at}]`, sorted most-recent-first. Powers the top-nav bell's dropdown so opening one unread conversation doesn't clear another's indicator. |
| `POST` | `/queues` | Behavior change (item 7, no signature change): if the caller is a Receptionist, now requires an Open shift (`ShiftService.has_open_shift`) — `400` with `"Please start your shift before serving patients."` if not. Owner/Administrator/Doctor/Cashier/Nurse are unaffected. |
| `POST` | `/appointments/{appointment_id}/check-in` | Same item 7 gate as above — this endpoint delegates to `QueueService.create_queue()` internally, so the check is shared, not duplicated. |
| `POST` | `/invoices/{invoice_id}/payments` | Same item 7 gate as above (`PaymentService.record_payment`), checked before any payment row is written. |

No new endpoints for item 8 (Audible Queue Calling) — it is entirely client-side (Web Speech API + `localStorage`), no backend involvement.

### Client Acceptance Revisions — Round 3 (items 4, 13)

No new endpoints — both are behavior/error-message changes on existing routes, no request/response schema changes.

| Method | Path | Notes |
|---|---|---|
| `POST` | `/visits/{visit_id}/consultation/open-for-reception` | Error detail reworded (item 4, BUG-024) for the existing 400 case where the visit has no doctor assigned: now `"This visit has no doctor assigned yet. Assign a doctor to the queue ticket before entering vitals."` (was the less actionable `"Visit has no assigned doctor."`). Status code and trigger condition unchanged. |
| `POST` | `/queues` | New failure mode (item 13, BUG-025): now returns `409 Conflict` if creating the ticket would exceed the resolved `QueueSetting.max_daily_queue` (default 200) for that clinic/branch/prefix/day, with a message naming the prefix and the limit. Previously this ceiling was configured but never enforced. |

### Client Acceptance Revisions — Round 3 (item 14): Doctor Session Control

| Method | Path | Notes |
|---|---|---|
| `GET` | `/doctor-workspace/session` | New. Whether the caller's (or, for Owner/Administrator with `?doctor_id=`, the specified doctor's) session is active today: `{active: bool, started_at: datetime \| null}`. |
| `POST` | `/doctor-workspace/session/start` | New. Opens today's session for the doctor ("Start Receiving Patients"). Idempotent - calling again while already active just returns the existing session's status. |
| `POST` | `/doctor-workspace/session/end` | New. Closes the doctor's currently-open session, if any. |
| `POST` | `/doctor-workspace/next-patient` | New ("Next Patient"). Completes/moves past whichever visit is currently `Called`/`InConsultation` for the doctor (if any - a `Called`-but-not-started visit is marked `NoShow`, an `InConsultation` one is completed via the existing `complete_consultation` path), then calls the earliest `Waiting` visit assigned to that doctor, if one exists. Returns the newly-called visit's detail, or `null` if there was nothing waiting. Does NOT require an active session (a Doctor can still use it without pressing Start first) and does NOT block Reception's existing per-ticket Call action either way - see `docs/DATABASE.md`'s Round 3 item 14 entry for why no hard gate was added. |

All four are gated the same as the existing `/doctor-workspace/visits/*` action endpoints (`require_doctor_workspace_view_role` for the read, `require_doctor_workspace_act_role` for the three mutations) - Doctor acts on their own linked record, Owner/Administrator may target any doctor via `?doctor_id=`.

---

### Phase 2.7: YAKAP Patient Classification + Receptionist Queue Control

No new endpoints - purely additive fields on existing patient/queue endpoints, plus one new query filter.

| Method | Path | Notes |
|---|---|---|
| `POST` / `PUT` | `/patients`, `/patients/{id}` | `is_yakap_beneficiary` (bool, default `false`) accepted in `PatientCreate`/`PatientUpdate`, returned in `PatientRead`/`PatientListItem`. |
| `POST` | `/queues` | `visit_classification` (`"Yakap"` \| `"Regular"`, default `"Regular"`) accepted in `QueueCreate` - does not affect `queue_number`/`queue_prefix` generation. |
| `PATCH` | `/queues/{id}` | `visit_classification` now also accepted in `QueueUpdate` for reassignment after creation. |
| `GET` | `/queues` | New optional `visit_classification` query param filters the list - view-only, does not alter queue numbers or state. |
| `GET` | `/public/tv-display/{identifier}` | `now_serving[]`/`next_waiting[]` entries gained `visit_classification` - safe to expose publicly (same privacy tier as the pre-existing `priority` field). Patient name is still never included anywhere in this response; only `patient_initials` (pre-existing). |

Role gating unchanged: classification is set/edited under the same `QUEUE_MANAGE_ROLES`/`QUEUE_TRANSITION_ROLES` as every other queue field.

---

## Versioning

All routes are prefixed `/api/v1`. Breaking changes will be introduced under a new prefix (`/api/v2`) rather than mutating `v1` in place; additive/backwards-compatible changes (new optional fields, new endpoints) may land in `v1` directly.

## Interactive docs

The FastAPI app auto-generates OpenAPI docs at `/docs` (Swagger UI) and `/redoc`, available in local/staging environments. These are the authoritative, always-up-to-date schema reference; this document is a curated overview of the auth surface for quick reference and onboarding.
