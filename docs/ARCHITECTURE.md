# Architecture

This document describes the system architecture of the CONNECT.PH Clinic Platform: the backend's clean-architecture layering, the multi-tenancy strategy, the dependency-injection approach, and the frontend's feature-based structure.

---

## 1. High-Level System Diagram

```
                         ┌─────────────────────────┐
                         │         Browser          │
                         └────────────┬─────────────┘
                                      │ HTTPS
                         ┌────────────▼─────────────┐
                         │   Next.js 15 (Vercel)     │
                         │  App Router / RSC / API   │
                         │   proxy for auth cookies  │
                         └────────────┬─────────────┘
                                      │ HTTPS (JWT bearer)
                         ┌────────────▼─────────────┐
                         │   FastAPI (Railway)       │
                         │  Routers → Services →     │
                         │  Repositories → Models    │
                         └──────┬───────────┬────────┘
                                │           │
                     ┌──────────▼───┐   ┌───▼──────────┐
                     │ PostgreSQL   │   │    Redis      │
                     │ (Supabase)   │   │ (rate limit,  │
                     │              │   │  cache, jobs) │
                     └──────────────┘   └───────────────┘
                                │
                     ┌──────────▼───┐
                     │ Supabase     │
                     │ Storage      │
                     │ (files/docs) │
                     └──────────────┘
```

WebSocket connections (for realtime queue updates in later phases) terminate at the FastAPI app alongside the REST API, sharing the same auth/tenant-context dependencies.

---

## 2. Backend: Clean Architecture Layering

The backend follows a strict top-down dependency direction — each layer only knows about the layer directly beneath it, never above:

```
┌────────────────────────────────────────────────────────┐
│  API Layer            app/api/v1/*.py                   │
│  - FastAPI routers, request/response models (Pydantic)  │
│  - Auth/tenant dependencies injected here                │
│  - No business logic, no direct DB access                │
└───────────────────────┬──────────────────────────────────┘
                         │ calls
┌────────────────────────▼─────────────────────────────────┐
│  Service Layer         app/services/*.py                  │
│  - Business logic, orchestration, validation rules         │
│  - Talks to one or more repositories                        │
│  - Framework-agnostic (no FastAPI imports)                   │
└───────────────────────┬────────────────────────────────────┘
                         │ calls
┌────────────────────────▼─────────────────────────────────┐
│  Repository Layer      app/repositories/*.py               │
│  - All SQL/ORM access lives here, nowhere else               │
│  - Every method that touches a tenant table takes/uses        │
│    the current clinic_id and filters by it                     │
└───────────────────────┬────────────────────────────────────┘
                         │ uses
┌────────────────────────▼─────────────────────────────────┐
│  Model / DB Layer      app/models/*.py, app/db/*.py         │
│  - SQLAlchemy 2.0 async ORM models, session/engine setup      │
│  - TenantMixin, TimestampMixin, SoftDeleteMixin, LegacyMixin   │
└──────────────────────────────────────────────────────────────┘
```

**Why this shape:**

- **Testability** — services can be unit-tested with fake/mock repositories, without a database.
- **Swap-ability** — the ORM/DB layer can change without touching business logic.
- **Auditability** — a reviewer can always answer "where does this table get written?" by looking at exactly one repository file.
- **Tenant safety** — because *all* DB access funnels through repositories, tenant scoping is enforced in one place instead of being re-implemented (and potentially forgotten) in every router.

`app/schemas/*.py` holds Pydantic request/response DTOs, shared between the API layer (validation, serialization) and, where useful, the service layer (internal DTOs). `app/middleware/*.py` holds cross-cutting concerns — tenant-context resolution, structured error handling, request logging — that wrap the whole request pipeline rather than living in any one layer.

---

## 3. Multi-Tenancy Strategy

### Chosen approach: shared schema, row-level tenant isolation (`clinic_id` column)

Every business table has a `clinic_id UUID NOT NULL REFERENCES clinics(id)` column. A single shared set of tables serves all clinics; rows are partitioned logically by `clinic_id`, not physically.

**Rejected alternative: schema-per-tenant / database-per-tenant.**

| Concern | Shared schema + `clinic_id` (chosen) | Schema/DB-per-tenant |
|---|---|---|
| Onboarding a new clinic | Insert one `clinics` row — instant | Provision a new schema/DB, run migrations against it |
| Migrations | One migration run touches all tenants | Must run against every tenant schema/DB — slow, error-prone at scale |
| Cross-tenant reporting/analytics (platform-level) | Trivial — `GROUP BY clinic_id` | Requires fan-out queries across N schemas |
| Connection pool usage | One pool, scales with total load | Pool pressure grows with tenant count |
| Operational complexity | Low — one thing to monitor/back up | High — N schemas/DBs to monitor/back up |
| Blast radius of a tenant-scoping bug | A missed `WHERE clinic_id = ?` leaks data — **mitigated below** | A bug is contained to one tenant's schema |

Given the target scale (many small-to-mid clinics, not a handful of huge enterprise tenants with strict physical-isolation requirements), the operational simplicity and fast onboarding of shared schema outweighs the isolation benefits of schema-per-tenant. The residual risk (a missed tenant filter) is addressed structurally, not just by convention:

1. **`TenantMixin`** (`app/models/mixins.py`) — declares `clinic_id` as a mapped column on every tenant-scoped model, so it is structurally impossible to define a business model without it.
2. **Repository pattern** — every repository method that reads/writes a tenant table requires a `clinic_id` (or a `TenantContext` object carrying it) as a parameter; there is no "unscoped" query helper exposed to services.
3. **FastAPI dependency injection** — `get_current_tenant()` (in `app/api/deps.py`) decodes the JWT, extracts `clinic_id`, and validates the user's membership in that clinic on every request. Services and repositories receive this resolved context via DI rather than re-deriving it, so there's one place tenant resolution can go wrong, not N.
4. **Defense in depth (planned, Phase 1+):** Postgres Row-Level Security (RLS) policies on tenant tables as a second, DB-enforced backstop, using a session-local `app.current_clinic_id` GUC set per-request — so even a bug in the repository layer cannot leak cross-tenant rows. RLS is not yet enabled at the foundation stage but the schema is designed to support it (every table has the `clinic_id` column RLS policies need).
5. **Audit logging** — `audit_logs` records `clinic_id`, `user_id`, action, and metadata for sensitive operations (starting with login events), giving a forensic trail if isolation is ever suspected to have failed.

### Global (non-tenant) tables

`roles`, `permissions`, `role_permissions` are platform-global (shared role/permission catalog across all clinics) rather than tenant-scoped, since the seeded role set (Owner, Administrator, Receptionist, Doctor, Nurse, Cashier, Laboratory, Pharmacy, Viewer) is common platform vocabulary. `clinics` and `subscriptions` are the tenant root and its billing relationship, respectively — they don't have a `clinic_id` themselves, they *are* (or belong to) the tenant.

---

## 4. Dependency Injection in FastAPI (`app/api/deps.py`)

Wiring follows FastAPI's native `Depends()` system, composed top-down:

```python
# app/api/deps.py (illustrative)

async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    payload = decode_jwt(token)              # raises 401 on invalid/expired
    user = await UserRepository(session).get_by_id(payload.sub)
    if user is None or user.is_deleted:
        raise HTTPException(401, "Invalid credentials")
    return user

async def get_current_tenant(
    user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
) -> TenantContext:
    payload = decode_jwt(token)
    return TenantContext(clinic_id=payload.clinic_id, user=user)

def get_user_service(
    session: AsyncSession = Depends(get_db_session),
) -> UserService:
    return UserService(UserRepository(session))
```

A router endpoint then declares only what it needs:

```python
# app/api/v1/auth.py (illustrative)

@router.post("/login")
async def login(
    payload: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    return await auth_service.login(payload.email, payload.password)

@router.get("/me")
async def me(tenant: TenantContext = Depends(get_current_tenant)):
    return tenant.user
```

Repositories and services are constructed per-request via these provider functions rather than as globals/singletons, which keeps the async DB session's lifecycle correctly scoped to the request and makes every layer trivially mockable in tests (override the `Depends` in `app.dependency_overrides` during Pytest fixtures).

---

## 5. Frontend: Feature-Based Structure

```
frontend/src/
├── app/                         # Next.js App Router — routing & composition only
│   ├── (auth)/                   # /login, /register, /forgot-password ...
│   │   └── login/page.tsx
│   └── (dashboard)/               # authenticated shell
│       └── dashboard/page.tsx
├── features/                    # domain/feature modules — the real logic lives here
│   └── auth/
│       ├── components/            # LoginForm, RegisterForm
│       ├── hooks/                  # useLogin, useSession
│       ├── api.ts                   # feature-scoped API calls (TanStack Query)
│       ├── schemas.ts                # Zod validation schemas
│       └── types.ts
├── components/
│   ├── ui/                       # shadcn/ui primitives (button, input, dialog, ...)
│   └── layout/                    # AppShell, Sidebar, Topbar
├── lib/                         # api-client (fetch wrapper + auth header), utils, config
├── hooks/                       # cross-feature hooks (useDebounce, useMediaQuery, ...)
└── types/                       # shared/global TypeScript types
```

**Rationale:**

- `app/` stays thin — pages compose feature components and handle routing/layout only; this keeps route files readable and avoids business logic creeping into `page.tsx`.
- `features/<name>/` is the unit of ownership — as business modules (patients, appointments, billing, ...) are built in later phases, each becomes its own folder under `features/` with the same internal shape (`components/hooks/api/schemas/types`), so the pattern established by `features/auth` today scales directly.
- `components/ui` stays feature-agnostic (pure shadcn primitives) so it's safe to share across every future feature without coupling.
- Server state (anything from the API) is owned by TanStack Query inside each feature's `api.ts`/hooks; client/UI state uses local component state or React Hook Form — there is no separate global client-state store at this stage, since server state dominates a CRUD-heavy clinic app.

---

## 6. Cross-Cutting Concerns

- **Error handling** — backend uses a centralized exception handler (`app/middleware`) mapping domain exceptions (e.g. `NotFoundError`, `TenantMismatchError`) to consistent JSON error responses; frontend's `lib/api-client.ts` normalizes these into a typed error shape consumed by TanStack Query's `onError` handlers.
- **Config** — backend config via `app/core/config.py` (Pydantic `BaseSettings`, reads env vars); frontend via `next.config.ts` + `NEXT_PUBLIC_*` env vars. See [`DEPLOYMENT.md`](DEPLOYMENT.md) for the full env var reference.
- **Realtime** — WebSocket endpoints (planned, Phase 2+) will sit alongside REST routers under `app/api/v1/ws/`, reusing the same `get_current_tenant` dependency pattern for connection-time auth.

---

## 7. Phase 15: The Two-Portal Architecture (SaaS Administration Portal)

Every phase through Phase 14 (and the Billing/Cashier module, renumbered Phase 16) operates *inside* one clinic's tenant boundary: every authenticated user is a row in the tenant-scoped `users` table, every JWT they carry has a `clinic_id` claim, and every query goes through `TenantMixin`-scoped repositories filtered by that `clinic_id`. Phase 15 deliberately introduces a second class of user — the **Platform Administrator** — who works for CONNECT.PH (the SaaS vendor) and legitimately needs to see and manage data *across* every tenant clinic (list all clinics, suspend any of them, view aggregate platform stats, etc.).

This is the single most important design decision in this phase: **how do you grant real cross-tenant access without weakening the tenant-isolation guarantee every prior phase depends on?**

### 7.1 The decision: a structurally separate user/auth model (option "b")

The spec offered two options:

- **(a)** Add `is_platform_admin: bool` + nullable `clinic_id` to the existing `users` table, reusing existing auth/login machinery.
- **(b)** A genuinely separate `platform_admin_users` table with its own login flow and JWT claim shape.

**We chose (b).** Rationale:

1. **The failure mode of (a) is catastrophic and silent.** If a platform admin is just a `User` row with `clinic_id = NULL`, then every single one of the ~14 phases' worth of existing code that does `Model.clinic_id == current_user.clinic_id` would need to be individually audited to confirm it correctly handles a `NULL` clinic_id (reject it, not silently skip the filter). One missed `if clinic_id is not None` guard anywhere in 14 phases of code is a cross-tenant data leak. Option (b) makes this class of bug *structurally impossible*: `PlatformAdminUser` is a completely different model with no `clinic_id` column at all, so there is no `User.clinic_id` comparison that could ever accidentally match it.
2. **JWTs are shaped differently, not just flagged differently.** A clinic-user access token (`app/core/security.py`) has the shape `{"sub": user_id, "user_id": ..., "clinic_id": ..., "role": <RoleName>, "type": "access"}`. A platform-admin access token (`app/core/platform_admin_security.py`) has the shape `{"sub": platform_admin_id, "platform_admin_id": ..., "platform_admin_role": <PlatformAdminRole>, "type": "platform_admin_access"}`. The `type` claim values never overlap between the two systems (`"access"`/`"refresh"` vs. `"platform_admin_access"`/`"platform_admin_refresh"`), and the platform-admin payload has no `clinic_id` key and no `user_id` key at all. `get_current_user` requires `type == "access"` and a `user_id` claim — a platform-admin token fails that check immediately. `get_current_platform_admin` requires `type == "platform_admin_access"` and a `platform_admin_id` claim — a clinic-user token fails that check immediately. There is no path by which one token type is accidentally accepted by the other dependency.
3. **Matches the spec's own framing**: "This should be architected as a separate portal", "Keep both portals logically separated."

Both token types are signed with the same `settings.JWT_SECRET_KEY` (as every JWT in this app is) — the separation that matters is claim shape and `type` value, not a different signing key.

### 7.2 What is NOT touched

- `app/db/mixins.py` (`TenantMixin`, etc.) — unchanged. No "sees everything" bypass was added to it.
- `app/core/dependencies.py`'s existing `get_current_user`, `require_roles`, and every existing `require_*_role` dependency — unchanged, still only ever resolve clinic-scoped `User` rows from clinic-scoped access tokens.
- Every existing repository (`UserRepository`, `PatientRepository`, etc.) — unchanged, still every query filters by `clinic_id`.
- `app/middleware/tenant_context.py` — unchanged. It only ever attempts to resolve tenant context from a clinic-user token's `clinic_id` claim; a platform-admin token simply has no such claim, so tenant-context resolution is a no-op for platform-admin requests (logged at DEBUG, not an error) rather than a special-cased bypass.

### 7.3 What Phase 15 adds, and where it lives

- **`platform_admin_users`** table (`app/models/platform_admin_user.py`) — no `clinic_id`, four roles (PlatformAdministrator/SupportEngineer/ImplementationTeam/Auditor).
- **`app/core/platform_admin_security.py`** — a fully separate JWT issuance/verification module. Does not import or call into `app/core/security.py`'s token functions.
- **`get_current_platform_admin`** (`app/core/dependencies.py`) — the only entry point into this world. Not layered on top of `get_current_user`; a completely independent dependency chain reading `platform_admin_oauth2_scheme` (its own `OAuth2PasswordBearer` instance, pointed at `/api/v1/platform-admin/auth/login`, distinct from the clinic portal's `oauth2_scheme`).
- **Cross-tenant services** (`app/services/tenant_management_service.py`, `subscription_management_service.py`, `feature_flag_service.py`, `platform_dashboard_service.py`, `tenant_user_admin_service.py`) — these are the ONLY places in the codebase that query `Clinic`/`Subscription`/`User` without a `clinic_id` filter. Every one of them is only ever constructed from `app/api/v1/platform_admin/router.py`, which is gated end-to-end by `get_current_platform_admin` / `require_platform_admin_*`. No clinic-scoped router imports any of these services, and none of these services are reachable from any clinic-scoped endpoint.
- **`app/api/v1/platform_admin/router.py`** — a dedicated router module, mounted once in `app/api/v1/router.py` under the `/platform-admin` prefix, kept structurally separate from every other router import.
- **Role/permission matrix** for the four platform roles (documented in `app/core/dependencies.py` next to `PLATFORM_ADMIN_*_ROLES`):

  | Role | View everything | Manage tenants/subscriptions/flags | Manage tenant users (reset/lock/force-logout) | Manage platform users/config |
  |---|---|---|---|---|
  | Auditor | Yes | No (403) | No (403) | No (403) |
  | SupportEngineer | Yes | No (403) | Yes | No (403) |
  | ImplementationTeam | Yes | Yes | No (403) | No (403) |
  | PlatformAdministrator | Yes | Yes | Yes | Yes |

  Auditor is deliberately read-only across the entire surface — it exists for compliance/audit access without a mutation footprint.

### 7.4 Tenant suspend/reactivate/archive and login blocking

`Clinic.status` (already existed from Phase 4) is reused/extended with `suspended_at`/`suspended_reason`/`archived_at`. Suspending a tenant (`TenantManagementService.suspend_tenant`) revokes every refresh token for every user in that clinic (force-logout) AND `AuthService.login` (`app/services/auth_service.py`) now checks `clinic.status in ("Suspended", "Archived")` immediately after resolving the user and blocks the login with a 403, before the password/lockout checks run. This was an explicit design decision for this phase (the spec left it to judgment): a suspended clinic must not be usable, not just invisible from platform-level nav.

### 7.5 Feature flags: real storage, one wired proof-of-concept

`tenant_feature_flags` supports all 8 known feature keys with real CRUD (`FeatureFlagService`). Only `is_feature_enabled(clinic_id, "appointments")` is actually consumed by clinic-facing code as a proof of concept — retrofitting feature-gating into 14 phases of existing UI/API would be its own multi-phase project and is explicitly out of scope here. The other seven keys are real, toggleable, and audited, but inert.

### 7.6 Explicit non-goals kept out of this phase

- No payment gateway / automated subscription billing — subscription fields are manually-editable records.
- API keys/OAuth clients/webhook secrets (`app/models/api_key.py`) have real CRUD + hashed-secret storage but are NOT wired into request authentication anywhere — that is a separate, larger retrofit.
- `platform_config` (`app/models/platform_config.py`) is a real key/value store, not a real integration with any email/SMS/AI/storage provider.
- `backups` records a "trigger manual backup" attempt; since `pg_dump` is not available in this sandboxed dev environment, the trigger endpoint is a documented, honestly-labeled stub (records a `Backup` row with status, does not execute a real dump). Restore is explicitly architecture-only (a stub method) — restoring over a live multi-tenant database is far too dangerous to implement here.
- `background_jobs` surfaces the one real background-style task in this codebase (Phase 14's migration imports) rather than inventing a fake job queue.

### 7.7 Frontend: a genuinely separate portal

`frontend/src/app/platform/` is a new top-level route group — NOT nested under the existing `(dashboard)` group, sharing none of its Sidebar/TopNav shell. It has its own layout (`app/platform/layout.tsx`, dark theme, "CONNECT.PH Platform Administration" branding) and its own login page (`app/platform/login/page.tsx`). `frontend/src/features/platform-admin/api/client.ts` uses distinct localStorage keys (`platform_access_token`/`platform_refresh_token`, vs. the clinic portal's `cph_access_token`/`cph_refresh_token`) and a distinct middleware-presence cookie (`platform_session` vs. `cph_session`), so the two auth states cannot collide even in the same browser session. `frontend/src/middleware.ts` gates `/platform/*` with its own protected-prefix/redirect logic, entirely separate from the clinic portal's checks, and redirects an unauthenticated platform-portal visitor to `/platform/login`, never to the clinic portal's `/login`.

## 8. Phase 16: Production Hardening

### 8.1 Caching strategy

`app/core/cache.py` implements a simple in-process TTL cache (`cache_get`/`cache_set`/`cache_invalidate`/`cache_invalidate_prefix`), following the exact "Redis if reachable, else in-memory, never crash on Redis being absent" convention already established by `app/core/rate_limit.py` (this dev environment has no Redis running, per `docs/TESTING.md`, so the in-memory path is what's actually exercised and verified).

**Wired call sites** (the spec's five candidates were: clinic settings, service catalog, departments, doctor schedules, feature flags — implemented for two of them as real, tested, end-to-end examples; the remaining three follow the identical pattern and are a direct, low-risk extension rather than something requiring new architecture):

- **Departments list** (`app/api/v1/departments.py`) — cache key includes every filter/pagination param (`departments:{clinic_id}:{q}:{status}:{limit}:{offset}`), TTL 60s, invalidated via `cache_invalidate_prefix(f"departments:{clinic_id}:")` on every create/update/delete/restore/seed-defaults call. Verified live (both via `pytest` and a real `curl` round-trip against the dev server): renaming a department and immediately re-listing shows the new name on the very next request, not after the TTL window.
- **Feature flags** (`app/services/feature_flag_service.py`'s `is_feature_enabled`) — cached per `(clinic_id, feature_key)`, TTL 30s (shorter, since this gates UI nav visibility and a platform admin toggling it should feel near-immediate), invalidated in `set_flag` on every toggle.

**Why invalidation, not just a short TTL**: a bare TTL-only cache would serve a stale department list to a receptionist for up to 60 seconds after an Owner edits it — silently wrong data with no error to signal it. Every wired mutation path explicitly calls the invalidation function in the same request that performed the write, so the *next* read (even one nanosecond later, even from a different worker in a single-process dev setup) sees the change. The TTL alone exists as a safety net (e.g. an invalidation call site missed in some future edit) and a bound on cache-entry memory growth, not as the primary correctness mechanism.

**Known limitation, documented rather than silently accepted**: this cache is process-local. A production deployment running more than one API worker process (e.g. multiple `uvicorn`/`gunicorn` workers, or multiple container replicas) would have each process's cache go stale independently of writes routed to a different worker, since invalidation only clears that worker's own in-memory dict. `app/core/cache.py`'s module docstring documents this explicitly: before scaling beyond one API process, route this cache through the same Redis instance `REDIS_URL` already points rate-limiting at (the interface — `cache_get`/`cache_set`/`cache_invalidate*` — is designed so call sites would need zero changes).

### 8.2 Request tracing

`app/middleware/request_logging.py` (extended, not replaced, from Phase 1) assigns every request a UUID (reusing an inbound `X-Request-ID` header if present), stashes it on `request.state.request_id`, includes it in the structured JSON access-log line, and returns it as an `X-Request-ID` response header — on both success and error responses (`app/main.py`'s three exception handlers all read `request.state.request_id`). This closes the loop between "a user reports an error" and "which server-side log line was that" without needing timestamp/IP correlation.

### 8.3 Observability probes

`/health` (unchanged), `/live` (liveness, zero dependencies), `/ready` (readiness, real `SELECT 1` against Postgres, `503` on failure) — see `docs/API.md` for the full contract and the rationale for keeping liveness dependency-free while readiness is allowed to fail.

### 8.4 Backup verification

`app/services/backup_service.py` extends Phase 15's bare `backups` table with a real service that shells out to `pg_dump` (confirmed available in this dev environment - `pg_dump (PostgreSQL) 16.4`), verifies the output file is non-empty and starts with the real PostgreSQL dump preamble, and records the outcome. Restore is explicitly NOT automated anywhere in this codebase — see `docs/BACKUP.md` for the human-executable procedure.
