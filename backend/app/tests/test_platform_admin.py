"""Phase 15: SaaS Administration Portal tests.

Covers: platform-admin auth (distinct token shape), cross-tenant tenant
management, and - most importantly - that tenant isolation is preserved:
a regular clinic Owner/Doctor cannot reach any platform-admin endpoint and
cannot see another clinic's data through existing clinic-scoped endpoints.
"""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.platform_admin_user import PlatformAdminRole, PlatformAdminUser
from app.models.role import Role

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def platform_admin_factory(db_session: AsyncSession):
    async def _make(role: PlatformAdminRole = PlatformAdminRole.PLATFORM_ADMINISTRATOR, password: str = "PlatAdmin123!"):
        suffix = uuid.uuid4().hex[:8]
        admin = PlatformAdminUser(
            email=f"padmin-{suffix}@connectph.dev",
            username=f"padmin{suffix}",
            hashed_password=hash_password(password),
            full_name="Test Platform Admin",
            role=role,
            is_active=True,
        )
        db_session.add(admin)
        await db_session.commit()
        await db_session.refresh(admin)
        return admin, password

    return _make


async def _pa_login(client: AsyncClient, identifier: str, password: str) -> str:
    resp = await client.post(
        "/api/v1/platform-admin/auth/login", json={"identifier": identifier, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def _clinic_login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login", json={"email_or_username": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# --------------------------------------------------------------------------
# Auth: structurally distinct token
# --------------------------------------------------------------------------


async def test_platform_admin_login_issues_distinct_token(client: AsyncClient, platform_admin_factory):
    admin, password = await platform_admin_factory()
    token = await _pa_login(client, admin.email, password)

    # A platform-admin token must be rejected by an existing clinic-scoped endpoint.
    resp = await client.get("/api/v1/patients", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401

    # But accepted by the platform-admin "me" endpoint.
    resp = await client.get("/api/v1/platform-admin/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == admin.email


async def test_wrong_credentials_rejected(client: AsyncClient, platform_admin_factory):
    admin, _ = await platform_admin_factory()
    resp = await client.post(
        "/api/v1/platform-admin/auth/login", json={"identifier": admin.email, "password": "WrongPass123!"}
    )
    assert resp.status_code == 401


# --------------------------------------------------------------------------
# THE most important tests: cross-tenant visibility + isolation preserved
# --------------------------------------------------------------------------


async def test_platform_admin_sees_both_tenants_clinic_user_sees_only_own(
    client: AsyncClient, platform_admin_factory, make_clinic_with_owner
):
    admin, password = await platform_admin_factory()
    pa_token = await _pa_login(client, admin.email, password)

    clinic_a, owner_a, owner_a_pw = await make_clinic_with_owner()
    clinic_b, owner_b, owner_b_pw = await make_clinic_with_owner()

    # 1. Platform admin can see both via the cross-tenant tenants list.
    resp = await client.get(
        f"/api/v1/platform-admin/tenants?search={clinic_a.slug[:6]}",
        headers={"Authorization": f"Bearer {pa_token}"},
    )
    assert resp.status_code == 200
    names_a = {t["id"] for t in resp.json()["items"]}
    assert str(clinic_a.id) in names_a

    resp_all = await client.get("/api/v1/platform-admin/tenants?page_size=100", headers={"Authorization": f"Bearer {pa_token}"})
    all_ids = {t["id"] for t in resp_all.json()["items"]}
    assert str(clinic_a.id) in all_ids
    assert str(clinic_b.id) in all_ids

    # 2. Clinic A's Owner cannot reach ANY platform-admin endpoint.
    owner_a_token = await _clinic_login(client, owner_a.email, owner_a_pw)
    for path in [
        "/api/v1/platform-admin/tenants",
        "/api/v1/platform-admin/dashboard/health",
        "/api/v1/platform-admin/audit-logs",
        "/api/v1/platform-admin/platform-users",
    ]:
        resp = await client.get(path, headers={"Authorization": f"Bearer {owner_a_token}"})
        assert resp.status_code in (401, 403), f"{path} should reject a clinic-user token, got {resp.status_code}"

    # 3. Clinic A's Owner cannot see Clinic B's data through existing clinic-scoped endpoints.
    resp = await client.get("/api/v1/patients", headers={"Authorization": f"Bearer {owner_a_token}"})
    assert resp.status_code == 200
    body = resp.json()
    items = body["items"] if isinstance(body, dict) and "items" in body else body
    for item in items:
        assert item.get("clinic_id") in (None, str(clinic_a.id))

    resp = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {owner_a_token}"})
    assert resp.status_code == 200
    body = resp.json()
    items = body["items"] if isinstance(body, dict) and "items" in body else body
    user_ids = {u["id"] for u in items}
    assert str(owner_b.id) not in user_ids
    assert str(owner_a.id) in user_ids


async def test_suspend_reactivate_tenant_blocks_and_restores_login(
    client: AsyncClient, platform_admin_factory, make_clinic_with_owner
):
    admin, password = await platform_admin_factory()
    pa_token = await _pa_login(client, admin.email, password)
    clinic, owner, owner_pw = await make_clinic_with_owner()

    resp = await client.post(
        f"/api/v1/platform-admin/tenants/{clinic.id}/suspend",
        json={"reason": "unit test suspend"},
        headers={"Authorization": f"Bearer {pa_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "Suspended"

    resp = await client.post(
        "/api/v1/auth/login", json={"email_or_username": owner.email, "password": owner_pw}
    )
    assert resp.status_code == 403

    resp = await client.post(
        f"/api/v1/platform-admin/tenants/{clinic.id}/reactivate", headers={"Authorization": f"Bearer {pa_token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "Active"

    resp = await client.post(
        "/api/v1/auth/login", json={"email_or_username": owner.email, "password": owner_pw}
    )
    assert resp.status_code == 200


async def test_archive_tenant(client: AsyncClient, platform_admin_factory, make_clinic_with_owner):
    admin, password = await platform_admin_factory()
    pa_token = await _pa_login(client, admin.email, password)
    clinic, _, _ = await make_clinic_with_owner()

    resp = await client.post(
        f"/api/v1/platform-admin/tenants/{clinic.id}/archive", headers={"Authorization": f"Bearer {pa_token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "Archived"
    assert resp.json()["archived_at"] is not None


async def test_update_tenant(client: AsyncClient, platform_admin_factory, make_clinic_with_owner):
    admin, password = await platform_admin_factory()
    pa_token = await _pa_login(client, admin.email, password)
    clinic, _, _ = await make_clinic_with_owner()

    resp = await client.patch(
        f"/api/v1/platform-admin/tenants/{clinic.id}",
        json={"name": "Renamed Clinic", "email": "renamed@example.com"},
        headers={"Authorization": f"Bearer {pa_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Renamed Clinic"
    assert body["email"] == "renamed@example.com"
    # Slug untouched since it wasn't in the payload.
    assert body["slug"] == clinic.slug


async def test_update_tenant_rejects_duplicate_slug(
    client: AsyncClient, platform_admin_factory, make_clinic_with_owner
):
    admin, password = await platform_admin_factory()
    pa_token = await _pa_login(client, admin.email, password)
    clinic_a, _, _ = await make_clinic_with_owner()
    clinic_b, _, _ = await make_clinic_with_owner()

    resp = await client.patch(
        f"/api/v1/platform-admin/tenants/{clinic_b.id}",
        json={"slug": clinic_a.slug},
        headers={"Authorization": f"Bearer {pa_token}"},
    )
    assert resp.status_code == 409


async def test_delete_tenant_requires_archived_first(
    client: AsyncClient, platform_admin_factory, make_clinic_with_owner
):
    admin, password = await platform_admin_factory()
    pa_token = await _pa_login(client, admin.email, password)
    clinic, _, _ = await make_clinic_with_owner()

    resp = await client.delete(
        f"/api/v1/platform-admin/tenants/{clinic.id}", headers={"Authorization": f"Bearer {pa_token}"}
    )
    assert resp.status_code == 400


async def test_delete_tenant_requires_full_platform_admin_role(
    client: AsyncClient, platform_admin_factory, make_clinic_with_owner
):
    admin, password = await platform_admin_factory()
    pa_token = await _pa_login(client, admin.email, password)
    clinic, _, _ = await make_clinic_with_owner()
    await client.post(
        f"/api/v1/platform-admin/tenants/{clinic.id}/archive", headers={"Authorization": f"Bearer {pa_token}"}
    )

    support_admin, support_password = await platform_admin_factory(role=PlatformAdminRole.SUPPORT_ENGINEER)
    support_token = await _pa_login(client, support_admin.email, support_password)

    resp = await client.delete(
        f"/api/v1/platform-admin/tenants/{clinic.id}", headers={"Authorization": f"Bearer {support_token}"}
    )
    assert resp.status_code == 403


async def test_delete_tenant_after_archive(client: AsyncClient, platform_admin_factory, make_clinic_with_owner):
    admin, password = await platform_admin_factory()
    pa_token = await _pa_login(client, admin.email, password)
    clinic, _, _ = await make_clinic_with_owner()

    await client.post(
        f"/api/v1/platform-admin/tenants/{clinic.id}/archive", headers={"Authorization": f"Bearer {pa_token}"}
    )

    resp = await client.delete(
        f"/api/v1/platform-admin/tenants/{clinic.id}", headers={"Authorization": f"Bearer {pa_token}"}
    )
    assert resp.status_code == 204

    list_resp = await client.get(
        "/api/v1/platform-admin/tenants?page_size=100", headers={"Authorization": f"Bearer {pa_token}"}
    )
    assert all(t["id"] != str(clinic.id) for t in list_resp.json()["items"])


# --------------------------------------------------------------------------
# Feature flags
# --------------------------------------------------------------------------


async def test_feature_flag_crud_and_proof_of_concept_check(
    client: AsyncClient, platform_admin_factory, make_clinic_with_owner, db_session: AsyncSession
):
    admin, password = await platform_admin_factory()
    pa_token = await _pa_login(client, admin.email, password)
    clinic, _, _ = await make_clinic_with_owner()

    resp = await client.get(
        f"/api/v1/platform-admin/tenants/{clinic.id}/feature-flags", headers={"Authorization": f"Bearer {pa_token}"}
    )
    assert resp.status_code == 200
    keys = {f["feature_key"] for f in resp.json()}
    assert "appointments" in keys

    resp = await client.put(
        f"/api/v1/platform-admin/tenants/{clinic.id}/feature-flags",
        json={"feature_key": "appointments", "is_enabled": False},
        headers={"Authorization": f"Bearer {pa_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_enabled"] is False

    from app.services.feature_flag_service import FeatureFlagService

    enabled = await FeatureFlagService.is_feature_enabled(db_session, clinic_id=clinic.id, feature_key="appointments")
    assert enabled is False


# --------------------------------------------------------------------------
# Subscription management
# --------------------------------------------------------------------------


async def test_subscription_upsert(client: AsyncClient, platform_admin_factory, make_clinic_with_owner):
    admin, password = await platform_admin_factory()
    pa_token = await _pa_login(client, admin.email, password)
    clinic, _, _ = await make_clinic_with_owner()

    resp = await client.put(
        f"/api/v1/platform-admin/tenants/{clinic.id}/subscription",
        json={"plan": "professional", "status": "active", "max_users": 25},
        headers={"Authorization": f"Bearer {pa_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"] == "professional"
    assert body["max_users"] == 25


# --------------------------------------------------------------------------
# Tenant user administration: reset password / lock / unlock / force-logout
# --------------------------------------------------------------------------


async def test_tenant_user_force_logout_invalidates_refresh_tokens(
    client: AsyncClient, platform_admin_factory, make_clinic_with_owner, db_session: AsyncSession
):
    admin, password = await platform_admin_factory()
    pa_token = await _pa_login(client, admin.email, password)
    clinic, owner, owner_pw = await make_clinic_with_owner()

    login_resp = await client.post(
        "/api/v1/auth/login", json={"email_or_username": owner.email, "password": owner_pw}
    )
    assert login_resp.status_code == 200
    refresh_cookie = login_resp.cookies.get("refresh_token")
    assert refresh_cookie is not None

    resp = await client.post(
        f"/api/v1/platform-admin/tenants/{clinic.id}/users/{owner.id}/force-logout",
        headers={"Authorization": f"Bearer {pa_token}"},
    )
    assert resp.status_code == 204

    from app.models.refresh_token import RefreshToken

    result = await db_session.execute(select(RefreshToken).where(RefreshToken.user_id == owner.id))
    tokens = result.scalars().all()
    assert len(tokens) >= 1
    assert all(t.revoked_at is not None for t in tokens)


async def test_tenant_user_reset_password_lock_unlock(
    client: AsyncClient, platform_admin_factory, make_clinic_with_owner
):
    admin, password = await platform_admin_factory()
    pa_token = await _pa_login(client, admin.email, password)
    clinic, owner, _ = await make_clinic_with_owner()

    resp = await client.post(
        f"/api/v1/platform-admin/tenants/{clinic.id}/users/{owner.id}/reset-password",
        json={"new_password": "BrandNewPass123!"},
        headers={"Authorization": f"Bearer {pa_token}"},
    )
    assert resp.status_code == 204

    resp = await client.post(
        "/api/v1/auth/login", json={"email_or_username": owner.email, "password": "BrandNewPass123!"}
    )
    assert resp.status_code == 200

    resp = await client.post(
        f"/api/v1/platform-admin/tenants/{clinic.id}/users/{owner.id}/lock",
        headers={"Authorization": f"Bearer {pa_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "locked"

    resp = await client.post(
        f"/api/v1/platform-admin/tenants/{clinic.id}/users/{owner.id}/unlock",
        headers={"Authorization": f"Bearer {pa_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


async def test_tenant_user_update(client: AsyncClient, platform_admin_factory, make_clinic_with_owner):
    admin, password = await platform_admin_factory()
    pa_token = await _pa_login(client, admin.email, password)
    clinic, owner, _ = await make_clinic_with_owner()

    resp = await client.patch(
        f"/api/v1/platform-admin/tenants/{clinic.id}/users/{owner.id}",
        json={"first_name": "Updated", "last_name": "Owner"},
        headers={"Authorization": f"Bearer {pa_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["first_name"] == "Updated"
    assert body["last_name"] == "Owner"

    # Persisted, not just echoed back.
    list_resp = await client.get(
        f"/api/v1/platform-admin/tenants/{clinic.id}/users", headers={"Authorization": f"Bearer {pa_token}"}
    )
    updated = next(u for u in list_resp.json() if u["id"] == str(owner.id))
    assert updated["first_name"] == "Updated"


async def test_tenant_user_update_rejects_duplicate_email(
    client: AsyncClient, platform_admin_factory, make_clinic_with_owner, db_session: AsyncSession
):
    admin, password = await platform_admin_factory()
    pa_token = await _pa_login(client, admin.email, password)
    clinic, owner, _ = await make_clinic_with_owner()

    from app.models.user import User as UserModel

    second_user = UserModel(
        clinic_id=clinic.id, email="second@example.com", username="second-user",
        hashed_password=hash_password("SecondPass123!"), first_name="Second", last_name="User",
        role_id=owner.role_id, is_active=True, is_email_verified=True,
    )
    db_session.add(second_user)
    await db_session.commit()
    await db_session.refresh(second_user)

    resp = await client.patch(
        f"/api/v1/platform-admin/tenants/{clinic.id}/users/{second_user.id}",
        json={"email": owner.email},
        headers={"Authorization": f"Bearer {pa_token}"},
    )
    assert resp.status_code == 409


async def test_tenant_user_delete_requires_full_platform_admin_role(
    client: AsyncClient, platform_admin_factory, make_clinic_with_owner
):
    """Delete is gated to PLATFORM_ADMINISTRATOR only - a lesser role like
    Support Engineer (which CAN edit/lock/reset-password) must not be able
    to permanently remove a clinic's user account."""
    support_admin, support_password = await platform_admin_factory(role=PlatformAdminRole.SUPPORT_ENGINEER)
    pa_token = await _pa_login(client, support_admin.email, support_password)
    clinic, owner, _ = await make_clinic_with_owner()

    resp = await client.delete(
        f"/api/v1/platform-admin/tenants/{clinic.id}/users/{owner.id}",
        headers={"Authorization": f"Bearer {pa_token}"},
    )
    assert resp.status_code == 403


async def test_tenant_user_delete(client: AsyncClient, platform_admin_factory, make_clinic_with_owner):
    admin, password = await platform_admin_factory()
    pa_token = await _pa_login(client, admin.email, password)
    clinic, owner, owner_pw = await make_clinic_with_owner()

    resp = await client.delete(
        f"/api/v1/platform-admin/tenants/{clinic.id}/users/{owner.id}",
        headers={"Authorization": f"Bearer {pa_token}"},
    )
    assert resp.status_code == 204

    # Soft-deleted user no longer appears in the list.
    list_resp = await client.get(
        f"/api/v1/platform-admin/tenants/{clinic.id}/users", headers={"Authorization": f"Bearer {pa_token}"}
    )
    assert all(u["id"] != str(owner.id) for u in list_resp.json())

    # And can no longer log in.
    login_resp = await client.post(
        "/api/v1/auth/login", json={"email_or_username": owner.email, "password": owner_pw}
    )
    assert login_resp.status_code == 401


# --------------------------------------------------------------------------
# Platform role gating (Auditor read-only, etc.)
# --------------------------------------------------------------------------


async def test_auditor_role_is_read_only(client: AsyncClient, platform_admin_factory, make_clinic_with_owner):
    admin, password = await platform_admin_factory(role=PlatformAdminRole.AUDITOR)
    pa_token = await _pa_login(client, admin.email, password)
    clinic, _, _ = await make_clinic_with_owner()

    # Auditor CAN view.
    resp = await client.get("/api/v1/platform-admin/tenants", headers={"Authorization": f"Bearer {pa_token}"})
    assert resp.status_code == 200

    # Auditor CANNOT suspend (write action).
    resp = await client.post(
        f"/api/v1/platform-admin/tenants/{clinic.id}/suspend", json={},
        headers={"Authorization": f"Bearer {pa_token}"},
    )
    assert resp.status_code == 403

    # Auditor CANNOT create a platform user (full-admin-only action).
    resp = await client.post(
        "/api/v1/platform-admin/platform-users",
        json={"email": "x@x.com", "username": "xuser", "password": "SomePass123!", "full_name": "X", "role": "Auditor"},
        headers={"Authorization": f"Bearer {pa_token}"},
    )
    assert resp.status_code == 403


async def test_implementation_team_can_manage_tenants_but_not_platform_users(
    client: AsyncClient, platform_admin_factory, make_clinic_with_owner
):
    admin, password = await platform_admin_factory(role=PlatformAdminRole.IMPLEMENTATION_TEAM)
    pa_token = await _pa_login(client, admin.email, password)
    clinic, _, _ = await make_clinic_with_owner()

    resp = await client.post(
        f"/api/v1/platform-admin/tenants/{clinic.id}/suspend", json={},
        headers={"Authorization": f"Bearer {pa_token}"},
    )
    assert resp.status_code == 200

    resp = await client.post(
        "/api/v1/platform-admin/platform-users",
        json={"email": "y@y.com", "username": "yuser", "password": "SomePass123!", "full_name": "Y", "role": "Auditor"},
        headers={"Authorization": f"Bearer {pa_token}"},
    )
    assert resp.status_code == 403


# --------------------------------------------------------------------------
# Dashboard + audit log
# --------------------------------------------------------------------------


async def test_dashboard_health_returns_real_numbers(client: AsyncClient, platform_admin_factory, make_clinic_with_owner):
    admin, password = await platform_admin_factory()
    pa_token = await _pa_login(client, admin.email, password)
    await make_clinic_with_owner()
    await make_clinic_with_owner()

    resp = await client.get("/api/v1/platform-admin/dashboard/health", headers={"Authorization": f"Bearer {pa_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_clinics"] >= 2
    assert body["database_size_bytes"] > 0


async def test_platform_audit_log_records_actions(client: AsyncClient, platform_admin_factory, make_clinic_with_owner):
    admin, password = await platform_admin_factory()
    pa_token = await _pa_login(client, admin.email, password)
    clinic, _, _ = await make_clinic_with_owner()

    await client.post(
        f"/api/v1/platform-admin/tenants/{clinic.id}/suspend", json={"reason": "audit test"},
        headers={"Authorization": f"Bearer {pa_token}"},
    )

    resp = await client.get(
        f"/api/v1/platform-admin/audit-logs?clinic_id={clinic.id}", headers={"Authorization": f"Bearer {pa_token}"}
    )
    assert resp.status_code == 200
    actions = {row["action"] for row in resp.json()}
    assert "tenant.suspend" in actions
