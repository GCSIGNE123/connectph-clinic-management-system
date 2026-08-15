"""Feature 5 Part B (Patient Visit History clickable records) - backend
regression coverage. No backend code changed for Part B (the feature is
purely a frontend UI change: Orders/Prescriptions/Laboratory rows on the
Visit Details page became clickable, opening read-only dialogs built
entirely from data the page already fetched via
`GET /visits/{id}/orders`, `GET /visits/{id}/prescriptions`, and
`GET /visits/{id}/laboratory` - unchanged endpoints, unchanged role gates).
This file confirms that claim: the existing permission boundary on those
three endpoints is unchanged (a role outside the view set still gets 403,
so making list rows clickable can't have bypassed anything), and that an
authorized role's response already contains everything the new detail
dialogs render (items/clinical notes/prescription items/lab results -
proving no new, wider data surface was introduced for the click-to-view
feature).
"""

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


async def _setup_queue_deps(client: AsyncClient, headers: dict) -> dict:
    branch = (await client.post("/api/v1/branches", headers=headers, json={"name": "Main Branch", "code": "MAIN"})).json()
    department = (
        await client.post("/api/v1/departments", headers=headers, json={"department_code": "GEN", "name": "General Medicine"})
    ).json()
    doctor = (await client.post("/api/v1/doctors", headers=headers, json={"first_name": "Jose", "last_name": "Rizal"})).json()
    service = (
        await client.post(
            "/api/v1/services", headers=headers,
            json={"service_code": "MEDCERT", "service_name": "Medical Certificate", "default_price": "500.00"},
        )
    ).json()
    patient = (
        await client.post(
            "/api/v1/patients", headers=headers,
            json={
                "first_name": "Juan", "last_name": "Dela Cruz", "birth_date": "1990-05-15",
                "gender": "Male", "civil_status": "Single", "mobile_number": "+639171234567",
            },
        )
    ).json()["patient"]
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


async def _setup_visit_with_full_clinical_history(client: AsyncClient, make_clinic_with_owner, db_session):
    """Creates a visit with one order (Laboratory-category, so it also
    auto-attaches a `laboratory_orders` row), one prescription, and enters
    lab results - the full set of records the Visit Details page's Orders/
    Prescriptions/Laboratory cards render and the new detail dialogs
    expose on click."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)

    queue = (await client.post("/api/v1/queues", headers=owner_headers, json=_queue_payload(deps))).json()
    visit_id = queue["visit_id"]

    doc_email, _doc_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor", doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "TestPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/call", headers=doc_headers)
    await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/start-consultation", headers=doc_headers)
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    cid = opened["id"]

    order_resp = await client.post(
        f"/api/v1/consultations/{cid}/orders", headers=doc_headers,
        json={"order_category": "Laboratory", "priority": "Routine", "items": [{"item_name": "CBC"}], "clinical_notes": "Rule out anemia"},
    )
    assert order_resp.status_code == 200, order_resp.text

    rx_resp = await client.post(
        f"/api/v1/consultations/{cid}/prescriptions", headers=doc_headers,
        json={"items": [{"medicine": "Amoxicillin", "dosage": "500mg", "frequency": "TID", "duration": "7 days", "substitution_allowed": True}]},
    )
    assert rx_resp.status_code == 200, rx_resp.text

    lab_orders = (await client.get(f"/api/v1/visits/{visit_id}/laboratory", headers=owner_headers)).json()
    lab_id = lab_orders[0]["id"]
    await client.post(f"/api/v1/laboratory/orders/{lab_id}/collect", headers=owner_headers)
    await client.post(f"/api/v1/laboratory/orders/{lab_id}/start-processing", headers=owner_headers)
    await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=owner_headers,
        json={"results": [{"parameter_name": "Hemoglobin", "result_type": "Numeric", "numeric_value": 10.0, "range_low": "12.0", "range_high": "16.0"}]},
    )

    recep_email, _recep_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Receptionist")
    recep_token = await _login(client, recep_email, "TestPass123!")
    recep_headers = {"Authorization": f"Bearer {recep_token}"}

    cashier_email, _cashier_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Cashier")
    cashier_token = await _login(client, cashier_email, "TestPass123!")
    cashier_headers = {"Authorization": f"Bearer {cashier_token}"}

    return {"clinic": clinic, "owner_headers": owner_headers, "recep_headers": recep_headers, "cashier_headers": cashier_headers, "visit_id": visit_id}


# --- Data already present for the new detail dialogs to render (no new fetch) ---

async def test_visit_orders_response_already_includes_items_and_clinical_notes(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx = await _setup_visit_with_full_clinical_history(client, make_clinic_with_owner, db_session)
    resp = await client.get(f"/api/v1/visits/{ctx['visit_id']}/orders", headers=ctx["owner_headers"])
    assert resp.status_code == 200
    order = resp.json()[0]
    assert order["items"][0]["item_name"] == "CBC"
    assert order["clinical_notes"] == "Rule out anemia"


async def test_visit_prescriptions_response_already_includes_items(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_visit_with_full_clinical_history(client, make_clinic_with_owner, db_session)
    resp = await client.get(f"/api/v1/visits/{ctx['visit_id']}/prescriptions", headers=ctx["owner_headers"])
    assert resp.status_code == 200
    rx = resp.json()[0]
    assert rx["items"][0]["medicine"] == "Amoxicillin"


async def test_visit_laboratory_response_already_includes_results_and_interpretation(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx = await _setup_visit_with_full_clinical_history(client, make_clinic_with_owner, db_session)
    resp = await client.get(f"/api/v1/visits/{ctx['visit_id']}/laboratory", headers=ctx["owner_headers"])
    assert resp.status_code == 200
    lab_order = resp.json()[0]
    assert lab_order["results"][0]["parameter_name"] == "Hemoglobin"
    assert lab_order["results"][0]["interpretation"] == "Low"


# --- Unauthorized roles still rejected (unchanged permission boundary) ---

async def test_unauthorized_role_cannot_view_visit_orders(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_visit_with_full_clinical_history(client, make_clinic_with_owner, db_session)
    resp = await client.get(f"/api/v1/visits/{ctx['visit_id']}/orders", headers=ctx["cashier_headers"])
    assert resp.status_code == 403


async def test_unauthorized_role_cannot_view_visit_prescriptions(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_visit_with_full_clinical_history(client, make_clinic_with_owner, db_session)
    resp = await client.get(f"/api/v1/visits/{ctx['visit_id']}/prescriptions", headers=ctx["cashier_headers"])
    assert resp.status_code == 403


async def test_unauthorized_role_cannot_view_visit_laboratory(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_visit_with_full_clinical_history(client, make_clinic_with_owner, db_session)
    resp = await client.get(f"/api/v1/visits/{ctx['visit_id']}/laboratory", headers=ctx["cashier_headers"])
    assert resp.status_code == 403


async def test_authorized_view_only_role_can_still_view_all_three(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """Receptionist: view-only per spec, unchanged by this feature - still
    allowed to see (but not edit) all three record types."""
    ctx = await _setup_visit_with_full_clinical_history(client, make_clinic_with_owner, db_session)
    for path in ("orders", "prescriptions", "laboratory"):
        resp = await client.get(f"/api/v1/visits/{ctx['visit_id']}/{path}", headers=ctx["recep_headers"])
        assert resp.status_code == 200, f"{path}: {resp.text}"
