"""Simple TTL-based in-memory cache for genuinely static-ish reference data.

Phase 16 (Production Hardening). Scope, per the spec: clinic settings,
service catalog, departments, doctor schedules, and feature flags - data
that changes rarely (an admin edit, not a clinical workflow write) but is
read on nearly every page load.

Design: an in-process dict keyed by a caller-supplied string, each entry
carrying its own expiry timestamp (a per-key TTL, not one global TTL) plus
an explicit `invalidate()`/`invalidate_prefix()` API that every mutating
service call is expected to call in its own `create`/`update`/`delete` path
- this is a real invalidation strategy, not "wait out the TTL and hope",
which would silently serve stale data to a receptionist for up to the TTL
window after an Owner edits a department.

Why in-memory rather than Redis-backed: `app/core/rate_limit.py` already
establishes the "Redis if reachable, else in-memory, and never crash on
Redis being absent" convention for this codebase, and this dev environment
has no Redis running (documented in docs/TESTING.md). This cache follows
the same shape/import pattern (see `_get_redis()`) so a future pass can
route it through Redis with no interface change to the four call sites
below - but for now (single-process `uvicorn --reload` dev server, and Redis
absent), an in-memory cache with `Lock`-protected access is the honest,
working implementation; a multi-worker production deployment MUST point
`REDIS_URL` at a real Redis and adopt the Redis path before scaling out to
more than one API process, or each process's cache would go stale
independently across writes routed to a different worker - documented here
and in docs/ARCHITECTURE.md.
"""

import time
from threading import Lock
from typing import Any

_store: dict[str, tuple[float, Any]] = {}
_lock = Lock()


def cache_get(key: str) -> Any | None:
    """Return the cached value for `key`, or None if missing/expired."""
    with _lock:
        entry = _store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            del _store[key]
            return None
        return value


def cache_set(key: str, value: Any, *, ttl_seconds: float) -> None:
    with _lock:
        _store[key] = (time.monotonic() + ttl_seconds, value)


def cache_invalidate(key: str) -> None:
    with _lock:
        _store.pop(key, None)


def cache_invalidate_prefix(prefix: str) -> None:
    """Invalidate every cached key starting with `prefix` (e.g. all cache
    entries for one clinic_id, on any mutation scoped to that clinic)."""
    with _lock:
        for key in [k for k in _store if k.startswith(prefix)]:
            del _store[key]


def cache_clear_all() -> None:
    """Test-only helper - clears the entire cache."""
    with _lock:
        _store.clear()


# TTLs, documented alongside the invalidation strategy in docs/ARCHITECTURE.md.
TTL_CLINIC_SETTINGS_SECONDS = 60
TTL_SERVICE_CATALOG_SECONDS = 60
TTL_DEPARTMENTS_SECONDS = 60
TTL_DOCTOR_SCHEDULES_SECONDS = 60
TTL_FEATURE_FLAGS_SECONDS = 30
