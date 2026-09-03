"""Laboratory History reprint feature: `GET /patients/{patient_id}/laboratory`
(the endpoint `PatientLaboratoryHistory`'s "Print Results" action re-fetches
through `GET /laboratory/orders/{id}` -> `LaboratoryReportDialog`) already
existed before this feature and needed no backend changes - these tests
confirm it correctly returns a Released historical result with its own
persisted data, is scoped to the right patient, is tenant-isolated, and
still honors the existing LAB_VIEW_ROLES/LAB_MANAGE_ROLES gate. Reuses the
exact same helper/fixture conventions as `test_laboratory.py`."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.role import Role

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    from app.core.rate_limit import _memory_buckets

    _memory_buckets.clear()
    yield
    _memory_buckets.clear()


async def _login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post("/api/v1/auth/login", json={"email_or_username": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _owner_headers(client: AsyncClient, make_clinic_with_owner):
    clinic, owner, password = await make_clinic_with_owner()
    token = await _login(client, owner.email, password)
    return clinic, owner, {"Authorization": f"Bearer {token}"}


async def _make_role_login(db_session: AsyncSession, *, clinic_id, role_name: str, doctor_id=None, password: str = "TestPass123!"):
    from app.models.user import User

    result = await db_session.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one()
    suffix = uuid.uuid4().hex[:8]
    email = f"{role_name.lower()}-{suffix}@example.com"
    user = User(
        clinic_id=clinic_id, email=email, username=f"{role_name.lower()}{suffix}", hashed_password=hash_password(password),
        first_name="Test", last_name=role_name, role_id=role.id, doctor_id=doctor_id, is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return email, user


async def _setup_queue_deps(client: AsyncClient, headers: dict, *, first_name="Juan", last_name="Dela Cruz") -> dict:
    suffix = uuid.uuid4().hex[:6]
    mobile_suffix = str(uuid.uuid4().int)[:7]
    branch = (await client.post("/api/v1/branches", headers=headers, json={"name": "Main Branch", "code": f"MAIN{suffix}"})).json()
    department = (
        await client.post("/api/v1/departments", headers=headers, json={"department_code": f"GEN{suffix}", "name": "General Medicine"})
    ).json()
    doctor = (await client.post("/api/v1/doctors", headers=headers, json={"first_name": "Jose", "last_name": "Rizal"})).json()
    service = (
        await client.post(
            "/api/v1/services", headers=headers,
            json={"service_code": f"MEDCERT{suffix}", "service_name": "Medical Certificate", "default_price": "300.00"},
        )
    ).json()
    patient_resp = await client.post(
        "/api/v1/patients", headers=headers,
        json={
            "first_name": first_name, "last_name": last_name, "birth_date": "1990-05-15",
            "gender": "Male", "civil_status": "Single", "mobile_number": f"+63917{mobile_suffix}",
        },
    )
    assert patient_resp.status_code == 201, patient_resp.text
    patient = patient_resp.json()["patient"]
    return {
        "branch_id": branch["id"], "department_id": department["id"],
        "doctor_id": doctor["id"], "service_id": service["id"], "patient_id": patient["id"],
    }


def _queue_payload(deps: dict) -> dict:
    return {
        "patient_id": deps["patient_id"], "branch_id": deps["branch_id"],
        "department_id": deps["department_id"], "doctor_id": deps["doctor_id"],
        "service_id": deps["service_id"], "priority": "Normal",
    }


_DEFAULT_TEMPLATE_PARAMETERS = [
    {"parameter_name": "Hemoglobin", "unit": "g/dL", "normal_range": "12.0-16.0", "result_type": "Numeric"},
]


async def _setup_released_lab_order_for_clinic(client: AsyncClient, db_session, *, clinic, owner_headers, patient_deps=None):
    """Drives a Laboratory order all the way to Released, mirroring
    `test_laboratory.py::_setup_with_lab_order` + its full-lifecycle test's
    collect/process/results/release sequence, so the resulting order has
    real persisted `LaboratoryResult` rows (not template data). Takes an
    already-created clinic/owner (rather than a `make_clinic_with_owner`
    factory) so callers can create multiple patients/orders under the SAME
    clinic without minting a fresh clinic each time."""
    deps = patient_deps or await _setup_queue_deps(client, owner_headers)

    template_resp = await client.post(
        "/api/v1/laboratory/templates", headers=owner_headers,
        json={
            "test_name": "CBC", "test_category": "Hematology", "specimen_type": "Whole Blood",
            "default_price": "350.00", "turnaround_time_hours": 4, "parameters": _DEFAULT_TEMPLATE_PARAMETERS,
        },
    )
    assert template_resp.status_code == 201, template_resp.text

    queue = (await client.post("/api/v1/queues", headers=owner_headers, json=_queue_payload(deps))).json()
    visit_id = queue["visit_id"]

    doc_email, _doc_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor", doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "TestPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/call", headers=doc_headers)
    await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/start-consultation", headers=doc_headers)
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()

    order_resp = await client.post(
        f"/api/v1/consultations/{opened['id']}/orders", headers=doc_headers,
        json={"order_category": "Laboratory", "priority": "Routine", "items": [{"item_name": "CBC"}]},
    )
    assert order_resp.status_code == 200, order_resp.text
    order = order_resp.json()

    lab_email, _lab_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Laboratory")
    lab_token = await _login(client, lab_email, "TestPass123!")
    lab_headers = {"Authorization": f"Bearer {lab_token}"}

    lab_orders = (await client.get(f"/api/v1/laboratory/orders?visit_id={visit_id}", headers=owner_headers)).json()
    lab_order = next(lo for lo in lab_orders if lo["order_id"] == order["id"])
    lab_id = lab_order["id"]

    await client.post(f"/api/v1/laboratory/orders/{lab_id}/collect", headers=lab_headers)
    await client.post(f"/api/v1/laboratory/orders/{lab_id}/start-processing", headers=lab_headers)
    results_resp = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=lab_headers,
        json={"results": [{"parameter_name": "Hemoglobin", "result_type": "Numeric", "numeric_value": 13.5, "normal_range": "12.0-16.0", "units": "g/dL", "interpretation": "Normal"}]},
    )
    assert results_resp.status_code == 200, results_resp.text

    # Pathologist selection is now MANDATORY at release (product decision) -
    # a real, active, same-clinic Pathologist is required for every release
    # call in this file.
    pathologist_resp = await client.post(
        "/api/v1/pathologists",
        headers=owner_headers, json={"name": "Dr. Maria Santos", "license_number": "PRC-12345"},
    )
    assert pathologist_resp.status_code == 201, pathologist_resp.text
    release_resp = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/release",
        headers=lab_headers, json={"pathologist_id": pathologist_resp.json()["id"]},
    )
    assert release_resp.status_code == 200, release_resp.text

    return {
        "clinic": clinic, "owner_headers": owner_headers, "lab_headers": lab_headers,
        "patient_id": deps["patient_id"], "lab_id": lab_id, "released_order": release_resp.json(),
    }


async def _setup_released_lab_order(client: AsyncClient, make_clinic_with_owner, db_session, *, patient_deps=None):
    """Convenience wrapper for the common single-clinic case: creates a
    fresh clinic/owner, then delegates to `_setup_released_lab_order_for_clinic`."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    return await _setup_released_lab_order_for_clinic(client, db_session, clinic=clinic, owner_headers=owner_headers, patient_deps=patient_deps)


# --- 1. Historical released laboratory result can be retrieved ---

async def test_historical_released_result_retrievable_via_patient_history(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_released_lab_order(client, make_clinic_with_owner, db_session)

    resp = await client.get(f"/api/v1/patients/{ctx['patient_id']}/laboratory", headers=ctx["owner_headers"])
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 1
    assert items[0]["status"] == "Released"

    # The report-print path (`LaboratoryReportDialog`) re-fetches this
    # single-order endpoint, which must expose the ORIGINALLY persisted
    # result values (not anything re-derived from the current template).
    single = await client.get(f"/api/v1/laboratory/orders/{ctx['lab_id']}", headers=ctx["owner_headers"])
    assert single.status_code == 200, single.text
    body = single.json()
    assert body["status"] == "Released"
    assert len(body["results"]) == 1
    assert body["results"][0]["parameter_name"] == "Hemoglobin"
    assert float(body["results"][0]["numeric_value"]) == 13.5
    assert body["results"][0]["normal_range"] == "12.0-16.0"
    assert body["results"][0]["units"] == "g/dL"
    assert body["clinic_name"] == ctx["clinic"].name


async def test_historical_result_unaffected_by_later_template_changes(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """Item 9: changing the template's reference range afterwards must not
    change what a historical released result reports - the printed report
    always reflects what was actually persisted at result-entry time."""
    ctx = await _setup_released_lab_order(client, make_clinic_with_owner, db_session)

    templates = (await client.get("/api/v1/laboratory/templates", headers=ctx["owner_headers"])).json()
    template_list = templates["items"] if isinstance(templates, dict) else templates
    cbc_template = next(t for t in template_list if t["test_name"] == "CBC")
    update_resp = await client.patch(
        f"/api/v1/laboratory/templates/{cbc_template['id']}", headers=ctx["owner_headers"],
        json={
            "parameters": [
                {"parameter_name": "Hemoglobin", "unit": "mg/dL", "normal_range": "999-999", "result_type": "Numeric"},
            ]
        },
    )
    assert update_resp.status_code == 200, update_resp.text

    single = await client.get(f"/api/v1/laboratory/orders/{ctx['lab_id']}", headers=ctx["owner_headers"])
    assert single.json()["results"][0]["normal_range"] == "12.0-16.0"  # unchanged
    assert single.json()["results"][0]["units"] == "g/dL"  # unchanged


# --- 2. Correct patient/result association ---

async def test_patient_history_scoped_to_correct_patient(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps_a = await _setup_queue_deps(client, owner_headers, first_name="Patient", last_name="A")
    deps_b = await _setup_queue_deps(client, owner_headers, first_name="Patient", last_name="B")

    ctx_a = await _setup_released_lab_order_for_clinic(client, db_session, clinic=clinic, owner_headers=owner_headers, patient_deps=deps_a)

    # Patient B has no lab orders at all.
    resp_a = await client.get(f"/api/v1/patients/{deps_a['patient_id']}/laboratory", headers=owner_headers)
    resp_b = await client.get(f"/api/v1/patients/{deps_b['patient_id']}/laboratory", headers=owner_headers)
    assert len(resp_a.json()) == 1
    assert resp_b.json() == []
    assert resp_a.json()[0]["id"] == ctx_a["lab_id"]


# --- 3. Clinic isolation ---

async def test_patient_laboratory_history_clinic_isolation(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_released_lab_order(client, make_clinic_with_owner, db_session)
    _clinic_b, _owner_b, owner_b_headers = await _owner_headers(client, make_clinic_with_owner)

    # Clinic B's view of Clinic A's patient id is scoped to clinic_id under
    # the hood (same tenant-scoped-query pattern as every other list
    # endpoint in this codebase) - it returns 200 with an empty list rather
    # than 404, but the key guarantee holds: zero of Clinic A's data leaks.
    resp = await client.get(f"/api/v1/patients/{ctx['patient_id']}/laboratory", headers=owner_b_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == []

    # Clinic B cannot fetch the individual released order either (used by the print dialog).
    single = await client.get(f"/api/v1/laboratory/orders/{ctx['lab_id']}", headers=owner_b_headers)
    assert single.status_code == 404, single.text


# --- 4. Existing Laboratory permissions preserved ---

async def test_existing_lab_view_role_permissions_preserved_for_patient_history(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx = await _setup_released_lab_order(client, make_clinic_with_owner, db_session)

    # Receptionist is in LAB_VIEW_ROLES - can view patient history and the report.
    recep_email, _recep = await _make_role_login(db_session, clinic_id=ctx["clinic"].id, role_name="Receptionist")
    recep_headers = {"Authorization": f"Bearer {await _login(client, recep_email, 'TestPass123!')}"}
    recep_resp = await client.get(f"/api/v1/patients/{ctx['patient_id']}/laboratory", headers=recep_headers)
    assert recep_resp.status_code == 200, recep_resp.text
    recep_report = await client.get(f"/api/v1/laboratory/orders/{ctx['lab_id']}", headers=recep_headers)
    assert recep_report.status_code == 200, recep_report.text

    # Cashier is NOT in LAB_VIEW_ROLES - unchanged 403, same as any other lab endpoint.
    cashier_email, _cashier = await _make_role_login(db_session, clinic_id=ctx["clinic"].id, role_name="Cashier")
    cashier_headers = {"Authorization": f"Bearer {await _login(client, cashier_email, 'TestPass123!')}"}
    cashier_resp = await client.get(f"/api/v1/patients/{ctx['patient_id']}/laboratory", headers=cashier_headers)
    assert cashier_resp.status_code == 403, cashier_resp.text
