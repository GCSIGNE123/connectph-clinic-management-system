"""Per-tenant feature flag CRUD + the `is_feature_enabled` check used by the
one wired proof-of-concept (Appointments sidebar link visibility - see
`frontend/src/features/clinic-settings` sidebar nav and GET
`/api/v1/platform-admin/tenants/{clinic_id}/feature-flags` /
`/api/v1/feature-flags/me` below).

Scope note: only the Appointments module's nav-visibility check actually
reads this flag. Every other feature key (laboratory/tv_queue/etc.) is real,
storable, and toggleable here, but is NOT wired into that module's own
UI/API - retrofitting feature-gating into 14 phases of code is out of scope
per the phase spec.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import TTL_FEATURE_FLAGS_SECONDS, cache_get, cache_invalidate, cache_set
from app.models.tenant_feature_flag import KNOWN_FEATURE_KEYS, TenantFeatureFlag
from app.services.platform_audit_service import PlatformAuditService


def _flag_cache_key(clinic_id: UUID, feature_key: str) -> str:
    return f"feature_flag:{clinic_id}:{feature_key}"


class FeatureFlagService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = PlatformAuditService(session)

    async def list_for_tenant(self, clinic_id: UUID) -> list[TenantFeatureFlag]:
        result = await self.session.execute(
            select(TenantFeatureFlag).where(TenantFeatureFlag.clinic_id == clinic_id)
        )
        existing = {row.feature_key: row for row in result.scalars().all()}
        # Ensure every known key has a row (default enabled) without persisting
        # until actually toggled, for a stable read shape.
        return [
            existing.get(key) or TenantFeatureFlag(clinic_id=clinic_id, feature_key=key, is_enabled=True)
            for key in KNOWN_FEATURE_KEYS
        ]

    async def set_flag(
        self, *, actor_id: UUID, clinic_id: UUID, feature_key: str, is_enabled: bool
    ) -> TenantFeatureFlag:
        result = await self.session.execute(
            select(TenantFeatureFlag).where(
                TenantFeatureFlag.clinic_id == clinic_id, TenantFeatureFlag.feature_key == feature_key
            )
        )
        flag = result.scalar_one_or_none()
        if flag is None:
            flag = TenantFeatureFlag(clinic_id=clinic_id, feature_key=feature_key, is_enabled=is_enabled)
            self.session.add(flag)
        else:
            flag.is_enabled = is_enabled
        flag.updated_by = actor_id
        await self.session.flush()
        await self.audit.log(
            actor_id=actor_id, action="feature_flag.set", entity_type="tenant_feature_flag",
            entity_id=feature_key, clinic_id=clinic_id, metadata={"is_enabled": is_enabled},
        )
        await self.session.commit()
        await self.session.refresh(flag)
        # Phase 16: invalidate immediately so the very next read (which may
        # be a different request/process reusing the cached value) sees the
        # new state - never rely on the TTL alone to correct a stale value.
        cache_invalidate(_flag_cache_key(clinic_id, feature_key))
        return flag

    @staticmethod
    async def is_feature_enabled(session: AsyncSession, *, clinic_id: UUID, feature_key: str) -> bool:
        """Public check used by clinic-scoped code (e.g. GET /api/v1/feature-flags/me).

        Defaults to True (enabled) when no row exists, so clinics created
        before this phase are unaffected until a platform admin explicitly
        disables something.

        Phase 16: this is called on effectively every request that renders
        the Appointments nav item, so it's cached (30s TTL) with immediate
        invalidation on `set_flag` above - a platform admin toggling a flag
        takes effect on the next request, not after up to 30 seconds.
        """
        cache_key = _flag_cache_key(clinic_id, feature_key)
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        result = await session.execute(
            select(TenantFeatureFlag).where(
                TenantFeatureFlag.clinic_id == clinic_id, TenantFeatureFlag.feature_key == feature_key
            )
        )
        flag = result.scalar_one_or_none()
        value = True if flag is None else flag.is_enabled
        cache_set(cache_key, value, ttl_seconds=TTL_FEATURE_FLAGS_SECONDS)
        return value
