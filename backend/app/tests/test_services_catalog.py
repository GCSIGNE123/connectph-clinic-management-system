"""Services catalog: concurrent-create race regression.

A real CSV-import failure surfaced this: two overlapping create requests
for the same `service_code` (e.g. a double-submitted import, or two staff
members importing the same catalog at once) both pass the existing
"does this code already exist" pre-check before either commits, so the
second request's actual INSERT hits the database's unique constraint. That
raised an unhandled `IntegrityError` that crashed the connection instead of
returning the same clean 409 the pre-check already promises - which the
browser then misreported as a CORS failure, masking the real cause.

The shared-session `client` fixture (see conftest.py) makes every HTTP
request in a test reuse one `AsyncSession`, so two real concurrent
transactions can't be driven through it. Instead: commit the conflicting
row via a second, independent session first, then monkeypatch the
pre-check to report "no existing row" - exactly what it would have seen
had it run a moment earlier, before the other transaction committed. This
exercises the real `create()` insert-then-catch path deterministically.
"""

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.schemas.clinic_service import ClinicServiceCreate
from app.services.clinic_service_catalog_service import ClinicServiceCatalogService

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    from app.core.rate_limit import _memory_buckets

    _memory_buckets.clear()
    yield
    _memory_buckets.clear()


async def test_create_converts_concurrent_duplicate_insert_to_clean_conflict(
    make_clinic_with_owner, db_session: AsyncSession, engine, monkeypatch
) -> None:
    clinic, owner, _password = await make_clinic_with_owner()
    payload = ClinicServiceCreate(service_code="RACE01", service_name="Race Test", default_price="100.00")

    # The "other request" wins the race: creates and commits first, on its
    # own independent session/connection.
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with session_maker() as other_session:
        other_service = ClinicServiceCatalogService(other_session)
        winner = await other_service.create(payload, clinic_id=clinic.id, actor=owner)
        assert winner.service_code == "RACE01"

    # Our session's pre-check is forced to report what it would genuinely
    # have seen had it run before the other transaction committed: nothing.
    async def fake_get_by_code(*args, **kwargs):
        return None

    service = ClinicServiceCatalogService(db_session)
    monkeypatch.setattr(service.repo, "get_by_code", fake_get_by_code)

    with pytest.raises(HTTPException) as exc_info:
        await service.create(payload, clinic_id=clinic.id, actor=owner)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Service code already in use"


async def test_double_submitted_import_row_is_never_duplicated(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """End-to-end confirmation via the real HTTP endpoint: submitting the
    same service_code twice in a row (the CSV-import scenario) always ends
    with exactly one row for that code, and the second attempt gets a clean
    409 - never a connection failure."""
    clinic, owner, password = await make_clinic_with_owner()
    login = await client.post("/api/v1/auth/login", json={"email_or_username": owner.email, "password": password})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    payload = {"service_code": "DUP01", "service_name": "Duplicate Test", "default_price": "100.00", "status": "Active"}

    first = await client.post("/api/v1/services", headers=headers, json=payload)
    assert first.status_code == 201, first.text

    second = await client.post("/api/v1/services", headers=headers, json=payload)
    assert second.status_code == 409, second.text
    assert second.json()["detail"] == "Service code already in use"

    listed = await client.get("/api/v1/services", headers=headers)
    codes = [s["service_code"] for s in listed.json()["items"]]
    assert codes.count("DUP01") == 1
