"""Pydantic schemas for the Platform Administration Portal."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.platform_admin_user import PlatformAdminRole
from app.models.subscription import SubscriptionPlan, SubscriptionStatus


class PlatformLoginRequest(BaseModel):
    identifier: str = Field(min_length=1, description="Platform admin email or username.")
    password: str = Field(min_length=1)


class PlatformRefreshRequest(BaseModel):
    refresh_token: str


class PlatformTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    platform_admin_id: UUID
    role: str


class PlatformAdminMeResponse(BaseModel):
    id: UUID
    email: str
    username: str
    full_name: str
    role: str
    last_login_at: datetime | None
    model_config = {"from_attributes": True}


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=100)
    email: str | None = None
    # The clinic's first login. Required: a tenant with no Owner user is a
    # dead end - nobody could ever sign into it. Created atomically with the
    # clinic row so "create tenant" always yields an immediately-usable
    # clinic account, matching how every other clinic in this system works.
    owner_email: str = Field(min_length=1, max_length=255)
    owner_username: str = Field(min_length=1, max_length=100)
    owner_password: str = Field(min_length=8, max_length=255)
    owner_first_name: str = Field(min_length=1, max_length=100)
    owner_last_name: str = Field(min_length=1, max_length=100)


class TenantUpdateRequest(BaseModel):
    """All fields optional (partial update). Deliberately excludes status/
    suspended_*/archived_* - those are lifecycle transitions with their own
    dedicated, audited endpoints (suspend/reactivate/archive), not plain
    field edits."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=255)


class TenantSuspendRequest(BaseModel):
    reason: str | None = None


class TenantRead(BaseModel):
    id: UUID
    name: str
    slug: str
    email: str | None
    status: str
    suspended_at: datetime | None
    suspended_reason: str | None
    archived_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


class TenantListResponse(BaseModel):
    items: list[TenantRead]
    total: int
    page: int
    page_size: int


class TenantStatsResponse(BaseModel):
    user_count: int
    storage_used_bytes: int
    subscription_plan: str | None
    subscription_status: str | None


class FeatureFlagRead(BaseModel):
    feature_key: str
    is_enabled: bool
    model_config = {"from_attributes": True}


class FeatureFlagSetRequest(BaseModel):
    feature_key: str
    is_enabled: bool


class SubscriptionUpsertRequest(BaseModel):
    plan: SubscriptionPlan | None = None
    status: SubscriptionStatus | None = None
    trial_start: datetime | None = None
    trial_end: datetime | None = None
    subscription_start: datetime | None = None
    renewal_date: datetime | None = None
    expiration_date: datetime | None = None
    max_users: int | None = None
    max_branches: int | None = None
    storage_limit_mb: int | None = None
    api_rate_limit: int | None = None


class SubscriptionRead(BaseModel):
    id: UUID
    clinic_id: UUID
    plan: str
    status: str
    trial_start: datetime | None
    trial_end: datetime | None
    subscription_start: datetime | None
    renewal_date: datetime | None
    expiration_date: datetime | None
    max_users: int | None
    max_branches: int | None
    storage_limit_mb: int | None
    api_rate_limit: int | None
    model_config = {"from_attributes": True}


class TenantUserRead(BaseModel):
    id: UUID
    email: str
    username: str
    first_name: str
    last_name: str
    role: str | None
    status: str
    is_active: bool
    model_config = {"from_attributes": True}


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8)


class TenantUserCreateRequest(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=255)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    role_id: UUID


class TenantUserUpdateRequest(BaseModel):
    """All fields optional (partial update) - a platform admin editing a
    clinic's own staff account. Deliberately excludes password (use the
    separate `POST .../reset-password`, which also revokes sessions - a
    plain field update here shouldn't silently have that side effect)."""

    email: str | None = Field(default=None, min_length=1, max_length=255)
    username: str | None = Field(default=None, min_length=1, max_length=100)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    role_id: UUID | None = None


class RoleRead(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    model_config = {"from_attributes": True}


class RoleListResponse(BaseModel):
    items: list[RoleRead]


class SystemHealthResponse(BaseModel):
    total_clinics: int
    active_clinics: int
    suspended_clinics: int
    trial_subscriptions: int
    expired_subscriptions: int
    online_users: int
    database_size_bytes: int
    background_jobs_total: int
    background_jobs_failed: int
    api_requests_today: int | None


class PlatformAuditLogRead(BaseModel):
    id: UUID
    actor_id: UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    clinic_id: UUID | None
    created_at: datetime
    model_config = {"from_attributes": True}


class BackgroundJobRead(BaseModel):
    id: UUID
    job_type: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    retry_count: int
    clinic_id: UUID | None
    model_config = {"from_attributes": True}


class PlatformAdminUserCreateRequest(BaseModel):
    email: str
    username: str
    password: str = Field(min_length=8)
    full_name: str
    role: PlatformAdminRole
