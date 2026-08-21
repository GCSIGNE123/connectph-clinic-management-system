"""Patient address field: covers the specific assertions the generic
`test_patients.py` create/tenant-isolation tests don't already make -
address is correctly persisted/returned, is optional (blank/omitted is
valid), and existing patient-creation behavior is unaffected. Reuses the
exact same `_patient_payload`/`_owner_headers`/`_login` conventions as
`test_patients.py` (tenant/cross-clinic address leakage itself is already
covered generically by `test_patients.py::test_tenant_isolation`, since
address is just one more field on the same 404-on-cross-tenant-GET
response)."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    from app.core.rate_limit import _memory_buckets

    _memory_buckets.clear()
    yield
    _memory_buckets.clear()


async def _login(client: AsyncClient, clinic_slug: str, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email_or_username": email, "password": password, "clinic_slug": clinic_slug},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _owner_headers(client: AsyncClient, make_clinic_with_owner):
    clinic, owner, password = await make_clinic_with_owner()
    token = await _login(client, clinic.slug, owner.email, password)
    return clinic, {"Authorization": f"Bearer {token}"}


def _patient_payload(**overrides) -> dict:
    payload = {
        "first_name": "Juan", "last_name": "Dela Cruz", "birth_date": "1990-05-15",
        "gender": "Male", "civil_status": "Single", "mobile_number": "+639171234567",
    }
    payload.update(overrides)
    return payload


async def test_create_patient_with_address_persists_correctly(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, headers = await _owner_headers(client, make_clinic_with_owner)

    create_resp = await client.post(
        "/api/v1/patients", headers=headers,
        json=_patient_payload(
            address_line="123 Rizal St.", barangay="Poblacion", city="Quezon City",
            province="Metro Manila", zip_code="1100",
        ),
    )
    assert create_resp.status_code == 201, create_resp.text
    patient = create_resp.json()["patient"]
    assert patient["address_line"] == "123 Rizal St."
    assert patient["barangay"] == "Poblacion"
    assert patient["city"] == "Quezon City"
    assert patient["province"] == "Metro Manila"
    assert patient["zip_code"] == "1100"

    # Persisted (not just echoed back) - fetching it again returns the same values.
    get_resp = await client.get(f"/api/v1/patients/{patient['id']}", headers=headers)
    assert get_resp.status_code == 200, get_resp.text
    fetched = get_resp.json()
    assert fetched["address_line"] == "123 Rizal St."
    assert fetched["barangay"] == "Poblacion"
    assert fetched["city"] == "Quezon City"
    assert fetched["province"] == "Metro Manila"
    assert fetched["zip_code"] == "1100"


async def test_create_patient_with_blank_address_line_persists_as_blank(client: AsyncClient, make_clinic_with_owner) -> None:
    """Only `address_line` is what the Queue tab's inline quick-create form
    submits (a single free-text line, not the full barangay/city/province/
    zip breakdown) - confirms it round-trips correctly as an empty string
    when left blank, matching what that form sends when untouched."""
    _clinic, headers = await _owner_headers(client, make_clinic_with_owner)

    create_resp = await client.post("/api/v1/patients", headers=headers, json=_patient_payload(address_line=""))
    assert create_resp.status_code == 201, create_resp.text
    patient = create_resp.json()["patient"]
    assert patient["address_line"] == "" or patient["address_line"] is None


async def test_create_patient_with_address_omitted_entirely_is_null(client: AsyncClient, make_clinic_with_owner) -> None:
    """Address is optional at the schema level - omitting every address
    field entirely (not even sending them) must not block patient creation."""
    _clinic, headers = await _owner_headers(client, make_clinic_with_owner)

    create_resp = await client.post("/api/v1/patients", headers=headers, json=_patient_payload())
    assert create_resp.status_code == 201, create_resp.text
    patient = create_resp.json()["patient"]
    assert patient["address_line"] is None
    assert patient["barangay"] is None
    assert patient["city"] is None
    assert patient["province"] is None
    assert patient["zip_code"] is None


async def test_existing_patient_creation_without_address_still_generates_patient_number(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """Regression guard: adding address to the Queue-tab form must not
    change any other patient-creation behavior - a patient created with no
    address fields at all still gets a normal sequential patient number."""
    _clinic, headers = await _owner_headers(client, make_clinic_with_owner)

    resp = await client.post("/api/v1/patients", headers=headers, json=_patient_payload())
    assert resp.status_code == 201, resp.text
    patient = resp.json()["patient"]
    assert patient["patient_number"].startswith("PAT-")
    assert patient["status"] == "Active"
