"""Platform Administration Portal API - genuinely separate router module.

Every route here is prefixed `/api/v1/platform-admin/...` and gated by
`get_current_platform_admin` (see `app/core/dependencies.py`) - NEVER by
`get_current_user`/`require_roles`, which gate the existing clinic-scoped
routers. A clinic-user JWT presented to any endpoint below gets a clean 401
(wrong token `type`/missing `platform_admin_id` claim - see
`app/core/platform_admin_security.py`).
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_current_platform_admin,
    get_db,
    require_platform_admin_full,
    require_platform_admin_tenant_manage,
    require_platform_admin_user_manage,
    require_platform_admin_view,
)
from app.models.background_job import BackgroundJob
from app.models.migration_batch import MigrationBatch
from app.models.platform_admin_user import PlatformAdminUser
from app.models.platform_audit_log import PlatformAuditLog
from app.schemas.platform_admin import (
    BackgroundJobRead,
    FeatureFlagRead,
    FeatureFlagSetRequest,
    PlatformAdminMeResponse,
    PlatformAdminUserCreateRequest,
    PlatformAuditLogRead,
    PlatformLoginRequest,
    PlatformRefreshRequest,
    PlatformTokenResponse,
    ResetPasswordRequest,
    SubscriptionRead,
    SubscriptionUpsertRequest,
    SystemHealthResponse,
    TenantCreateRequest,
    TenantListResponse,
    TenantRead,
    TenantStatsResponse,
    TenantSuspendRequest,
    TenantUserRead,
)
from app.services.feature_flag_service import FeatureFlagService
from app.services.platform_admin_auth_service import PlatformAdminAuthService
from app.services.platform_dashboard_service import PlatformDashboardService
from app.services.subscription_management_service import SubscriptionManagementService
from app.services.tenant_management_service import TenantManagementService
from app.services.tenant_user_admin_service import TenantUserAdminService

router = APIRouter(prefix="/platform-admin", tags=["platform-admin"])


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------


@router.post("/auth/login", response_model=PlatformTokenResponse)
async def platform_login(payload: PlatformLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    service = PlatformAdminAuthService(db)
    result = await service.login(
        identifier=payload.identifier,
        password=payload.password,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return PlatformTokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        platform_admin_id=result.admin.id,
        role=result.admin.role.value,
    )


@router.post("/auth/refresh", response_model=PlatformTokenResponse)
async def platform_refresh(payload: PlatformRefreshRequest, db: AsyncSession = Depends(get_db)):
    service = PlatformAdminAuthService(db)
    result = await service.refresh(payload.refresh_token)
    return PlatformTokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        platform_admin_id=result.admin.id,
        role=result.admin.role.value,
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def platform_logout(
    current: PlatformAdminUser = Depends(get_current_platform_admin), db: AsyncSession = Depends(get_db)
):
    service = PlatformAdminAuthService(db)
    await service.logout(current)


@router.get("/auth/me", response_model=PlatformAdminMeResponse)
async def platform_me(current: PlatformAdminUser = Depends(get_current_platform_admin)):
    return PlatformAdminMeResponse.model_validate(current)


# --------------------------------------------------------------------------
# Dashboard / System Health
# --------------------------------------------------------------------------


@router.get("/dashboard/health", response_model=SystemHealthResponse, dependencies=[Depends(require_platform_admin_view)])
async def system_health(db: AsyncSession = Depends(get_db)):
    service = PlatformDashboardService(db)
    return SystemHealthResponse(**await service.get_system_health())


# --------------------------------------------------------------------------
# Tenant (clinic) management - THE cross-tenant surface.
# --------------------------------------------------------------------------


@router.get("/tenants", response_model=TenantListResponse, dependencies=[Depends(require_platform_admin_view)])
async def list_tenants(
    search: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    service = TenantManagementService(db)
    rows, total = await service.list_tenants(search=search, status_filter=status_filter, page=page, page_size=page_size)
    return TenantListResponse(
        items=[TenantRead.model_validate(r) for r in rows], total=total, page=page, page_size=page_size
    )


@router.get("/tenants/{clinic_id}", response_model=TenantRead, dependencies=[Depends(require_platform_admin_view)])
async def get_tenant(clinic_id: UUID, db: AsyncSession = Depends(get_db)):
    service = TenantManagementService(db)
    clinic = await service.get_tenant(clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return TenantRead.model_validate(clinic)


@router.get(
    "/tenants/{clinic_id}/stats", response_model=TenantStatsResponse, dependencies=[Depends(require_platform_admin_view)]
)
async def get_tenant_stats(clinic_id: UUID, db: AsyncSession = Depends(get_db)):
    service = TenantManagementService(db)
    stats = await service.get_tenant_stats(clinic_id)
    sub = stats["subscription"]
    return TenantStatsResponse(
        user_count=stats["user_count"],
        storage_used_bytes=stats["storage_used_bytes"],
        subscription_plan=sub.plan.value if sub else None,
        subscription_status=sub.status.value if sub else None,
    )


@router.post(
    "/tenants", response_model=TenantRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_platform_admin_tenant_manage)],
)
async def create_tenant(
    payload: TenantCreateRequest,
    current: PlatformAdminUser = Depends(get_current_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    service = TenantManagementService(db)
    clinic = await service.create_tenant(actor_id=current.id, name=payload.name, slug=payload.slug, email=payload.email)
    return TenantRead.model_validate(clinic)


@router.post(
    "/tenants/{clinic_id}/suspend", response_model=TenantRead, dependencies=[Depends(require_platform_admin_tenant_manage)]
)
async def suspend_tenant(
    clinic_id: UUID,
    payload: TenantSuspendRequest,
    current: PlatformAdminUser = Depends(get_current_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    service = TenantManagementService(db)
    try:
        clinic = await service.suspend_tenant(actor_id=current.id, clinic_id=clinic_id, reason=payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return TenantRead.model_validate(clinic)


@router.post(
    "/tenants/{clinic_id}/reactivate", response_model=TenantRead,
    dependencies=[Depends(require_platform_admin_tenant_manage)],
)
async def reactivate_tenant(
    clinic_id: UUID,
    current: PlatformAdminUser = Depends(get_current_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    service = TenantManagementService(db)
    try:
        clinic = await service.reactivate_tenant(actor_id=current.id, clinic_id=clinic_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return TenantRead.model_validate(clinic)


@router.post(
    "/tenants/{clinic_id}/archive", response_model=TenantRead, dependencies=[Depends(require_platform_admin_tenant_manage)]
)
async def archive_tenant(
    clinic_id: UUID,
    current: PlatformAdminUser = Depends(get_current_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    service = TenantManagementService(db)
    try:
        clinic = await service.archive_tenant(actor_id=current.id, clinic_id=clinic_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return TenantRead.model_validate(clinic)


# --------------------------------------------------------------------------
# Subscription management
# --------------------------------------------------------------------------


@router.get(
    "/tenants/{clinic_id}/subscription", response_model=SubscriptionRead | None,
    dependencies=[Depends(require_platform_admin_view)],
)
async def get_subscription(clinic_id: UUID, db: AsyncSession = Depends(get_db)):
    service = SubscriptionManagementService(db)
    sub = await service.get_for_tenant(clinic_id)
    return SubscriptionRead.model_validate(sub) if sub else None


@router.put(
    "/tenants/{clinic_id}/subscription", response_model=SubscriptionRead,
    dependencies=[Depends(require_platform_admin_tenant_manage)],
)
async def upsert_subscription(
    clinic_id: UUID,
    payload: SubscriptionUpsertRequest,
    current: PlatformAdminUser = Depends(get_current_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionManagementService(db)
    sub = await service.upsert(actor_id=current.id, clinic_id=clinic_id, **payload.model_dump())
    return SubscriptionRead.model_validate(sub)


# --------------------------------------------------------------------------
# Feature flags
# --------------------------------------------------------------------------


@router.get(
    "/tenants/{clinic_id}/feature-flags", response_model=list[FeatureFlagRead],
    dependencies=[Depends(require_platform_admin_view)],
)
async def list_feature_flags(clinic_id: UUID, db: AsyncSession = Depends(get_db)):
    service = FeatureFlagService(db)
    flags = await service.list_for_tenant(clinic_id)
    return [FeatureFlagRead(feature_key=f.feature_key, is_enabled=f.is_enabled) for f in flags]


@router.put(
    "/tenants/{clinic_id}/feature-flags", response_model=FeatureFlagRead,
    dependencies=[Depends(require_platform_admin_tenant_manage)],
)
async def set_feature_flag(
    clinic_id: UUID,
    payload: FeatureFlagSetRequest,
    current: PlatformAdminUser = Depends(get_current_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    service = FeatureFlagService(db)
    flag = await service.set_flag(
        actor_id=current.id, clinic_id=clinic_id, feature_key=payload.feature_key, is_enabled=payload.is_enabled
    )
    return FeatureFlagRead(feature_key=flag.feature_key, is_enabled=flag.is_enabled)


# --------------------------------------------------------------------------
# Tenant users (a platform admin managing a clinic's own staff accounts)
# --------------------------------------------------------------------------


@router.get(
    "/tenants/{clinic_id}/users", response_model=list[TenantUserRead], dependencies=[Depends(require_platform_admin_view)]
)
async def list_tenant_users(clinic_id: UUID, db: AsyncSession = Depends(get_db)):
    service = TenantUserAdminService(db)
    users = await service.list_tenant_users(clinic_id)
    return [
        TenantUserRead(
            id=u.id, email=u.email, username=u.username, first_name=u.first_name, last_name=u.last_name,
            role=u.role.name if u.role else None, status=u.status.value, is_active=u.is_active,
        )
        for u in users
    ]


@router.post(
    "/tenants/{clinic_id}/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_platform_admin_user_manage)],
)
async def reset_tenant_user_password(
    clinic_id: UUID,
    user_id: UUID,
    payload: ResetPasswordRequest,
    current: PlatformAdminUser = Depends(get_current_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    service = TenantUserAdminService(db)
    await service.reset_password(actor_id=current.id, clinic_id=clinic_id, user_id=user_id, new_password=payload.new_password)


@router.post(
    "/tenants/{clinic_id}/users/{user_id}/lock", response_model=TenantUserRead,
    dependencies=[Depends(require_platform_admin_user_manage)],
)
async def lock_tenant_user(
    clinic_id: UUID, user_id: UUID,
    current: PlatformAdminUser = Depends(get_current_platform_admin), db: AsyncSession = Depends(get_db),
):
    service = TenantUserAdminService(db)
    u = await service.lock(actor_id=current.id, clinic_id=clinic_id, user_id=user_id)
    return TenantUserRead(
        id=u.id, email=u.email, username=u.username, first_name=u.first_name, last_name=u.last_name,
        role=u.role.name if u.role else None, status=u.status.value, is_active=u.is_active,
    )


@router.post(
    "/tenants/{clinic_id}/users/{user_id}/unlock", response_model=TenantUserRead,
    dependencies=[Depends(require_platform_admin_user_manage)],
)
async def unlock_tenant_user(
    clinic_id: UUID, user_id: UUID,
    current: PlatformAdminUser = Depends(get_current_platform_admin), db: AsyncSession = Depends(get_db),
):
    service = TenantUserAdminService(db)
    u = await service.unlock(actor_id=current.id, clinic_id=clinic_id, user_id=user_id)
    return TenantUserRead(
        id=u.id, email=u.email, username=u.username, first_name=u.first_name, last_name=u.last_name,
        role=u.role.name if u.role else None, status=u.status.value, is_active=u.is_active,
    )


@router.post(
    "/tenants/{clinic_id}/users/{user_id}/force-logout", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_platform_admin_user_manage)],
)
async def force_logout_tenant_user(
    clinic_id: UUID, user_id: UUID,
    current: PlatformAdminUser = Depends(get_current_platform_admin), db: AsyncSession = Depends(get_db),
):
    service = TenantUserAdminService(db)
    await service.force_logout(actor_id=current.id, clinic_id=clinic_id, user_id=user_id)


# --------------------------------------------------------------------------
# Background jobs monitoring (surfaces real Phase 14 migration batches;
# no fake job system - see app/models/background_job.py docstring).
# --------------------------------------------------------------------------


@router.get(
    "/background-jobs", response_model=list[BackgroundJobRead], dependencies=[Depends(require_platform_admin_view)]
)
async def list_background_jobs(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select  # noqa: PLC0415

    native_jobs = (await db.execute(select(BackgroundJob).order_by(BackgroundJob.created_at.desc()).limit(100))).scalars().all()
    migration_batches = (
        await db.execute(select(MigrationBatch).order_by(MigrationBatch.created_at.desc()).limit(100))
    ).scalars().all()

    status_map = {
        "Draft": "Scheduled", "Connected": "Scheduled", "Analyzed": "Scheduled", "Previewed": "Scheduled",
        "Validated": "Scheduled", "Importing": "Running", "Completed": "Completed",
        "PartiallyCompleted": "Completed", "Failed": "Failed", "Cancelled": "Failed",
    }
    results = [BackgroundJobRead.model_validate(j) for j in native_jobs]
    for batch in migration_batches:
        results.append(
            BackgroundJobRead(
                id=batch.id, job_type="migration_import", status=status_map.get(batch.status.value, "Scheduled"),
                started_at=batch.started_at, completed_at=batch.completed_at, error_message=None,
                retry_count=0, clinic_id=batch.clinic_id,
            )
        )
    return results


# --------------------------------------------------------------------------
# Platform audit log
# --------------------------------------------------------------------------


@router.get(
    "/audit-logs", response_model=list[PlatformAuditLogRead], dependencies=[Depends(require_platform_admin_view)]
)
async def list_platform_audit_logs(
    clinic_id: UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select  # noqa: PLC0415

    stmt = select(PlatformAuditLog).order_by(PlatformAuditLog.created_at.desc()).limit(limit)
    if clinic_id is not None:
        stmt = stmt.where(PlatformAuditLog.clinic_id == clinic_id)
    if action is not None:
        stmt = stmt.where(PlatformAuditLog.action == action)
    rows = (await db.execute(stmt)).scalars().all()
    return [PlatformAuditLogRead.model_validate(r) for r in rows]


# --------------------------------------------------------------------------
# Platform admin user management (PlatformAdministrator-only)
# --------------------------------------------------------------------------


@router.get(
    "/platform-users", response_model=list[PlatformAdminMeResponse], dependencies=[Depends(require_platform_admin_full)]
)
async def list_platform_users(db: AsyncSession = Depends(get_db)):
    from app.repositories.platform_admin_repository import PlatformAdminUserRepository  # noqa: PLC0415

    repo = PlatformAdminUserRepository(db)
    return [PlatformAdminMeResponse.model_validate(a) for a in await repo.list_all()]


@router.post(
    "/platform-users", response_model=PlatformAdminMeResponse, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_platform_admin_full)],
)
async def create_platform_user(payload: PlatformAdminUserCreateRequest, db: AsyncSession = Depends(get_db)):
    from app.core.security import hash_password  # noqa: PLC0415

    admin = PlatformAdminUser(
        email=payload.email, username=payload.username, hashed_password=hash_password(payload.password),
        full_name=payload.full_name, role=payload.role,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return PlatformAdminMeResponse.model_validate(admin)


# --------------------------------------------------------------------------
# Backup verification (Phase 16) - real pg_dump execution + verification.
# Restore stays architecture-only/documented (docs/BACKUP.md), never
# automated via an API endpoint - see BackupService's module docstring.
# --------------------------------------------------------------------------


@router.post("/backups", dependencies=[Depends(require_platform_admin_full)])
async def trigger_backup(
    db: AsyncSession = Depends(get_db), current: PlatformAdminUser = Depends(get_current_platform_admin)
):
    from app.services.backup_service import BackupService  # noqa: PLC0415

    service = BackupService(db)
    backup = await service.run_backup(triggered_by=current.id)
    return {
        "id": backup.id,
        "status": backup.status.value,
        "file_size_bytes": backup.file_size_bytes,
        "storage_location": backup.storage_location,
        "error_message": backup.error_message,
    }


@router.get("/backups", dependencies=[Depends(require_platform_admin_view)])
async def list_backups(db: AsyncSession = Depends(get_db)):
    from app.services.backup_service import BackupService  # noqa: PLC0415

    service = BackupService(db)
    backups = await service.list_backups()
    return [
        {
            "id": b.id,
            "status": b.status.value,
            "started_at": b.started_at,
            "completed_at": b.completed_at,
            "file_size_bytes": b.file_size_bytes,
            "storage_location": b.storage_location,
            "error_message": b.error_message,
        }
        for b in backups
    ]
