# Security

This document describes the current and planned security posture of the CONNECT.PH Clinic Platform: authentication, password handling, rate limiting, CSRF/XSS mitigations, audit logging, and secrets management. This is a healthcare-adjacent system handling patient/clinical data in later phases, so security is treated as a foundational concern, not an afterthought.

---

## 1. JWT Strategy

- **Access token** — short-lived (default **15 minutes**), signed HS256 (or RS256 in production if key-splitting between issuer/verifier is desired), carries `sub` (user id), `clinic_id`, `roles`, `iat`, `exp`. Sent as a `Bearer` token in the `Authorization` header on every API request.
- **Refresh token** — longer-lived (default **7 days**, or a shorter session-only lifetime when `remember_me` is not set on login), opaque (not a JWT itself), tracked server-side in the `refresh_tokens` table (see [`DATABASE.md`](DATABASE.md)), **stored hashed** (never in plaintext — the DB row holds `token_hash`, the raw value exists only client-side and momentarily at issuance):
  - `logout` revokes the specific refresh token immediately (`revoked_at` set).
  - Refresh tokens are rotated on every use (old row revoked, new row issued with `parent_id` pointing at the old one) to limit the blast radius of a leaked refresh token — reuse of an already-revoked refresh token is treated as a signal of compromise and revokes the entire session chain for that user (walking `parent_id`).
  - Disabling a user (`POST /users/{id}/disable`) or an admin-initiated password reset also revokes all of that user's active refresh tokens.
- **Storage on the client:**
  - Frontend stores the access token in memory (React state/query cache), not `localStorage`, to reduce XSS exfiltration risk.
  - The refresh token is stored in an `HttpOnly`, `Secure`, `SameSite=Strict` cookie set by the backend on `login`/`refresh`, so client-side JavaScript cannot read it even if XSS occurs.
- Tokens are never logged (see [Audit Logging](#5-audit-logging) — audit logs record the *action*, not the token itself).

## 1a. Account Lockout Policy

- `users.failed_login_attempts` increments on every failed login attempt (wrong password or unknown-but-enumerated email is not distinguished in the response) and resets to `0` on a successful login.
- After **5** consecutive failures, `users.locked_until` is set to `now() + 15 minutes` (both thresholds tunable via config) and further login attempts return `403` with a generic "account temporarily locked, try again later" message — not a countdown, to avoid giving an attacker precise timing signal.
- An administrator can clear a lockout early via `POST /api/v1/users/{user_id}/admin-reset-password`, which also clears `failed_login_attempts`/`locked_until` (see [`API.md`](API.md)).
- Lockout is account-scoped (`clinic_id` + user), not IP-scoped — see [Rate Limiting](#3-rate-limiting) for the complementary IP-based control.
- Lockout events are written to `audit_logs` alongside the existing `auth.login.failure` entries, so repeated failures and the resulting lockout are both visible in the audit trail.

## 1b. Password Reset & Email Verification Token Lifecycle

- Both `password_reset_tokens` and `email_verification_tokens` follow the same pattern: a cryptographically random token is generated, only its hash (`token_hash`) is persisted, and the raw token is embedded in the emailed link.
- **Expiry:** password reset tokens expire after **1 hour**; email verification tokens after **24 hours**. Expired tokens are rejected with `400` on use.
- **Single-use:** consuming a token sets `used_at`; a second attempt with the same (already-used) token is rejected with `400`, indistinguishable from an expired/invalid token in the response (to avoid leaking which failure mode occurred).
- **Enumeration resistance:** `forgot-password` and `resend-verification` always return the same generic success message regardless of whether the email exists in the system.
- Successful `reset-password` revokes all of the user's active refresh tokens (forces re-login on all devices) as a precaution, since a password reset is often triggered by a suspected compromise.
- **Known TODO:** actual email delivery (SMTP) is not yet wired up — tokens are issued and stored correctly, but the link is not yet sent to the user's inbox. See [`API.md`](API.md) and [`DEPLOYMENT.md`](DEPLOYMENT.md) for the `SMTP_*` configuration this depends on.

## 2. Password Hashing

- Passwords are hashed with **`passlib`**, using **argon2** as the primary scheme (memory-hard, resistant to GPU cracking) with **bcrypt** supported as a fallback/verification scheme for compatibility.
- Plaintext passwords are never stored, logged, or included in `audit_logs` metadata.
- Password strength is validated at the API boundary (Zod on the frontend, Pydantic validators on the backend) — minimum length, and a policy such as requiring a mix of character classes, before hashing.
- `passlib`'s `CryptContext` is configured with `deprecated="auto"`, so if the hashing scheme's parameters (or the scheme itself) are upgraded later, existing hashes are transparently re-hashed on next successful login without forcing a mass password reset.

## 3. Rate Limiting (Redis-based)

Enforced (Phase 2) on the abuse-prone, unauthenticated auth endpoints:

- Redis-backed sliding-window/token-bucket counter, keyed by `(ip_address, endpoint)` and, where applicable, `(email, endpoint)` — so an attacker can't just rotate IPs to bypass an email-keyed limit, and legitimate users behind shared IPs (offices/NAT) aren't punished by IP-only limits.
- Applied to `login`, `register`, `forgot-password`, `resend-verification`, `refresh`.
- Initial limits (tunable via config): `login` — 10 attempts / 5 minutes per email, 30 / 5 minutes per IP; `forgot-password` / `resend-verification` — 3 / hour per email.
- Implemented as a FastAPI dependency wrapping the affected routers, backed by Redis `INCR` + `EXPIRE`, returning `429 Too Many Requests` with a `Retry-After` header on limit.
- Complementary to, and independent of, the account-level lockout in [1a](#1a-account-lockout-policy) — rate limiting throttles by IP/email before a request is even evaluated; lockout blocks a specific account after repeated failures regardless of source IP.

## 4. CSRF / XSS Mitigations

**XSS:**

- React escapes rendered content by default; `dangerouslySetInnerHTML` is disallowed by convention outside of tightly reviewed, sanitized cases (rich-text rendering, if introduced later, must go through a sanitizer such as `DOMPurify`).
- Content Security Policy (CSP) headers set at the Next.js/Vercel edge (via `next.config.ts` headers or middleware) restricting script sources; tightened over time as third-party integrations are added.
- Access tokens kept out of `localStorage`/`sessionStorage` (see JWT section) specifically to limit what an XSS payload could exfiltrate.

**CSRF:**

- Because the API is consumed via `Authorization: Bearer` headers (not ambient cookies) for the access token, classic CSRF (which relies on browsers automatically attaching cookies to cross-site requests) does not apply to authenticated API calls themselves.
- The refresh-token cookie (if/when cookie-based refresh is fully wired, see JWT section) is set with `SameSite=Strict` (or `Lax` if cross-site redirect flows require it) plus `HttpOnly` and `Secure`, which prevents it from being sent on cross-site requests in the first place — the primary CSRF defense for that cookie.
- State-changing requests additionally validate `Content-Type: application/json`, which simple cross-site form submissions cannot forge (they can only send `application/x-www-form-urlencoded` or `multipart/form-data` without JavaScript, and JavaScript-driven cross-origin requests are blocked by CORS — see below).
- CORS is configured on the FastAPI app (`CORSMiddleware`) with an explicit allow-list of the frontend's origin(s) (`localhost:3000` in dev, the Vercel production/preview domains in prod) rather than a wildcard, and credentials mode restricted to what's actually needed.

## 5. Audit Logging

- The `audit_logs` table (see [`DATABASE.md`](DATABASE.md)) is an append-only record of security-relevant events.
- Currently instrumented: `auth.login.success`, `auth.login.failure` (including on unknown email, to detect enumeration attempts — without leaking whether the email exists in the response itself).
- Planned expansion as business modules land: record creation/modification of sensitive entities (patient records, billing), permission/role changes, and admin actions (deactivating a user, changing clinic settings).
- Each entry captures `clinic_id`, `user_id` (nullable for pre-auth events), `action`, `entity_type`/`entity_id` where applicable, `ip_address`, `user_agent`, a `metadata` JSONB blob, and `created_at`. Entries are never updated or deleted by application code.
- Audit logs are tenant-scoped like any other business table but are readable platform-wide by platform administrators for security investigations (a documented, logged exception to normal tenant isolation, not a backdoor built into ordinary application flows).

## 6. Secrets Management & Environment Variables

- Secrets (`JWT_SECRET_KEY`, `DATABASE_URL`, Supabase service role keys, Redis URL, future SMTP credentials) are **never committed to the repository**. Each app has its own `.env.example` documenting required variables with placeholder values only.
- Local development: secrets live in `frontend/.env.local` and `backend/.env`, both git-ignored.
- Staging/production: secrets are configured directly in the hosting platform's secret store — Vercel Environment Variables (frontend) and Railway Variables (backend) — never passed through CI logs or baked into Docker images.
- `JWT_SECRET_KEY` (or the RS256 private key, if adopted) is generated per-environment (dev/staging/prod each have distinct keys) so a leak in one environment doesn't compromise another.
- GitHub Actions secrets (`VERCEL_TOKEN`, `RAILWAY_TOKEN`, etc. — see [`DEPLOYMENT.md`](DEPLOYMENT.md)) are stored in the repository's GitHub Actions secrets store, scoped to the minimum required permissions, and are not printed in workflow logs (GitHub automatically redacts secret values that appear in step output).
- The Supabase **service role key** (which bypasses row-level security) is used only by the backend server-side, never shipped to the frontend; the frontend, if it talks to Supabase directly for storage, uses the restricted **anon key** plus signed URLs/policies, not the service role key.
- Principle of least privilege applies to database roles as they're introduced (e.g., a future read-only reporting role for analytics queries, distinct from the migration/admin role used by Alembic).

## 7. Additional Practices

- Dependencies are kept current; CI includes lint/type-check steps as a first line of defense, with dependency vulnerability scanning (`npm audit`, `pip-audit`/`safety`, or GitHub Dependabot alerts) recommended as a near-term addition once the CI skeleton is exercised in practice.
- All traffic is served over HTTPS in every non-local environment (enforced by Vercel and Railway by default).
- Multi-tenant isolation itself (row-level `clinic_id` scoping, with Postgres RLS planned as a second enforcement layer) is documented in detail in [`ARCHITECTURE.md`](ARCHITECTURE.md#3-multi-tenancy-strategy) and is treated as a security control, not just a data-modeling concern.

## 8. Phase 16: Production Hardening — real findings

A dedicated review pass across CORS, rate limiting, file uploads, SQL-injection surface, and secrets, with real fixes applied where a genuine gap was found. Honest "reviewed, no issue found" findings are recorded here alongside the real fixes — not everything reviewed needed a change.

**CORS (`app/core/config.py`)** — reviewed, no issue found. `CORS_ORIGINS` is an explicit comma-separated allow-list (`http://localhost:3000,http://localhost:5173` in dev), never a wildcard `*`, and `allow_credentials=True` is paired with that explicit list (a wildcard + credentials combination is what's actually dangerous, and CORS middleware rejects that combination outright regardless). No change needed.

**Rate limiting (`app/core/rate_limit.py`)** — reviewed and re-confirmed live via the Phase 16 load-test script (see `docs/TESTING.md`): firing 20 concurrent logins against the same account/IP correctly returned `429 Too Many Requests` for every attempt beyond the configured `RATE_LIMIT_LOGIN_MAX_ATTEMPTS` (10), proving the limiter is live and working end-to-end, not just present in code. No change needed. Documented limitation (pre-existing, not new): the in-memory fallback bucket is per-process, so a multi-worker production deployment must point `REDIS_URL` at a real Redis instance for the limit to be enforced globally rather than per-worker.

**File upload validation — real gap found and fixed.** Read every attachment/photo upload endpoint in the codebase (`patients.py`, `doctors.py`, `clinic_settings.py`, `consultations.py`, `laboratory.py`, `migration.py`) before deciding what to change:
  - The patient-photo, doctor-photo, and clinic-branding upload endpoints take **no client-supplied file metadata at all** (no filename, no size field in the request body) — the object path/extension is fixed server-side (`photo-{token}.jpg`). There is genuinely nothing to validate at these three endpoints today; this is stated honestly rather than adding validation code with nothing to validate.
  - The **consultation-attachment** (`POST /consultations/{id}/attachments`) and **laboratory-attachment** (`POST /laboratory/orders/{id}/attachments`) endpoints DO take a client-declared `file_name`/`file_size_bytes` before minting a presigned upload URL, and had **zero** validation of either — a client could request a presigned URL for a `.exe` file or declare an arbitrarily large size with no server-side pushback. Fixed: `app/core/upload_validation.py` adds a real extension allow-list (`.pdf/.jpg/.jpeg/.png/.webp/.doc/.docx` for documents) and a 20MB size cap, enforced in both services before a presigned URL is issued. Covered by `app/tests/test_production_hardening.py`.
  - The **legacy migration wizard's** `POST /migration/batches/{id}/upload` endpoint is the one upload flow in the app that relays *real file bytes* through the backend (every other flow above is presigned-URL-only) and had zero extension/size validation before writing an arbitrary-sized client file straight to disk. Fixed: a real 50MB per-file cap and a CSV/Excel extension allow-list matching the batch's declared source type, enforced before any bytes are written.

**SQL injection — reviewed, no issue found.** Spot-checked repository query construction across `patient_repository.py`, `invoice_repository.py`, `queue_repository.py`, and `laboratory_repository.py`: every query is built via SQLAlchemy's `select()`/`where()` with bound parameters (`Model.column == value`), never raw string interpolation or f-string SQL. No instance of `text(f"...")`-style interpolation with untrusted input found anywhere in `app/repositories/` or `app/services/`. No change needed — the codebase's own architecture (always going through SQLAlchemy Core/ORM) already prevents this class of bug structurally.

**Secrets — reviewed, no issue found.** `backend/.env.example` was checked line-by-line: every value is a placeholder (`change-me-to-a-random-secret-in-production`, `your-supabase-service-key`, etc.), never a real credential. Grepped for `password`/`token`/`secret` in every `logger.info`/`logger.error`/`print(` call site across `app/` — no raw password, JWT, or refresh-token value is ever logged; the request-logging middleware only logs method/path/status/duration/request-id/clinic-id, never request bodies or headers. No change needed.

**Error envelope / request tracing** — see `docs/API.md`'s Phase 16 section: every error response now includes a `request_id` matching the `X-Request-ID` response header, making a reported error traceable to its exact server-side log line without needing to correlate on timestamp/IP, which is itself a (minor) security-operations improvement — faster incident triage.
