"""Phase 5B (P0, D1/D2): `app/api/v1/clinics.py` was a dead "foundation
stub" - zero frontend/backend callers anywhere in the codebase, and two of
its four endpoints were genuinely insecure: `POST /clinics` had NO auth
dependency at all (anonymous tenant creation), and `GET /clinics/{id}` had
no tenant-scoping (any authenticated user of any clinic could read any
other clinic's record). Investigation found the real, already-existing,
properly-authorized surfaces this duplicated: `/auth/register` (self-
service tenant creation, unaffected by this change) and
`/platform-admin/tenants/*` (the genuine cross-tenant admin surface, gated
by the separate `require_platform_admin_*` authority - see
app/api/v1/platform_admin/router.py). Removing the redundant, insecure
router is the smallest fix consistent with the existing architecture -
no new provisioning model was invented.

These tests prove the vulnerable surface is gone and the real surfaces
are unaffected."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_anonymous_post_clinics_no_longer_exists(client: AsyncClient) -> None:
    """The unauthenticated-tenant-creation vulnerability (D1) is closed by
    removing the route entirely - it now 404s instead of accepting an
    anonymous request."""
    resp = await client.post("/api/v1/clinics", json={"name": "x", "slug": "anonymous-clinic-attempt"})
    assert resp.status_code == 404


async def test_authenticated_get_clinics_by_id_no_longer_exists(client: AsyncClient, make_clinic_with_owner) -> None:
    """The cross-tenant-read vulnerability (D2) is closed the same way -
    an authenticated user (even from a real clinic) can no longer reach
    any clinic's record via this path."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    resp = await client.get(f"/api/v1/clinics/{clinic.id}", headers=owner_headers)
    assert resp.status_code == 404


async def test_auth_register_still_provisions_a_clinic_normally(client: AsyncClient) -> None:
    """`/auth/register` (the real, sole self-service provisioning path)
    is completely unaffected by removing the dead `/clinics` router."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "owner@removed-router-test.example",
            "username": "removedroutertestowner",
            "password": "TestPass123!",
            "first_name": "Test",
            "last_name": "Owner",
            "clinic_name": "Removed-Router Test Clinic",
            "clinic_slug": "removed-router-test-clinic",
        },
    )
    assert resp.status_code in (200, 201), resp.text


async def _owner_headers(client: AsyncClient, make_clinic_with_owner):
    clinic, owner, password = await make_clinic_with_owner()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email_or_username": owner.email, "password": password, "clinic_slug": clinic.slug},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return clinic, owner, {"Authorization": f"Bearer {token}"}
