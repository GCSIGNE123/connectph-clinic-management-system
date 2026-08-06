"""Integration tests for Phase 10 Laboratory Management: a Laboratory-
category Order (Phase 9, unchanged) auto-attaches a `laboratory_orders`
workflow record; collect -> process -> enter-results -> release lifecycle
with correct timeline events at each step (no duplicate "Ordered" event);
result entry supports multiple parameters, numeric and text; billing
integration (completing a priced lab order creates/updates an invoice line
item, and doing it twice does not duplicate the charge - the most important
test in this file per the Phase 7/8/9 sync-bug lesson); laboratory template
CRUD (Administrator-only mutation, broad read); role gating (Doctor creates
via Phase 9 endpoint, Laboratory role collects/processes/enters-results/
releases but cannot create, Reception view-only); patient-laboratory-
history and visit-laboratory endpoints; tenant isolation.
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


async def _setup_queue_deps(client: AsyncClient, headers: dict) -> dict:
    branch = (await client.post("/api/v1/branches", headers=headers, json={"name": "Main Branch", "code": "MAIN"})).json()
    department = (
        await client.post("/api/v1/departments", headers=headers, json={"department_code": "GEN", "name": "General Medicine"})
    ).json()
    doctor = (
        await client.post("/api/v1/doctors", headers=headers, json={"first_name": "Jose", "last_name": "Rizal"})
    ).json()
    service = (
        await client.post(
            "/api/v1/services", headers=headers,
            json={"service_code": "MEDCERT", "service_name": "Medical Certificate", "default_price": "300.00"},
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


async def _setup_with_lab_order(client: AsyncClient, make_clinic_with_owner, db_session, *, template_price="350.00"):
    """Sets up a clinic, doctor, patient, queue->visit, opens a consultation,
    creates a priced Laboratory template, then creates a Laboratory-category
    Order via the unchanged Phase 9 endpoint (which auto-attaches a
    laboratory_orders row matching the template by test name). Returns
    headers for Owner/Doctor/Laboratory/Receptionist roles plus ids."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)

    template_resp = await client.post(
        "/api/v1/laboratory/templates", headers=owner_headers,
        json={
            "test_name": "CBC", "test_category": "Hematology", "specimen_type": "Whole Blood",
            "default_price": template_price, "turnaround_time_hours": 4,
            "parameters": [
                {"parameter_name": "Hemoglobin", "unit": "g/dL", "normal_range": "12.0-16.0", "result_type": "Numeric"},
                {"parameter_name": "Remarks", "result_type": "Text"},
            ],
        },
    )
    assert template_resp.status_code == 201, template_resp.text
    template = template_resp.json()

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
        json={"order_category": "Laboratory", "priority": "STAT", "items": [{"item_name": "CBC"}]},
    )
    assert order_resp.status_code == 200, order_resp.text
    order = order_resp.json()

    lab_email, _lab_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Laboratory")
    lab_token = await _login(client, lab_email, "TestPass123!")
    lab_headers = {"Authorization": f"Bearer {lab_token}"}

    recep_email, _recep_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Receptionist")
    recep_token = await _login(client, recep_email, "TestPass123!")
    recep_headers = {"Authorization": f"Bearer {recep_token}"}

    lab_orders = (await client.get(f"/api/v1/laboratory/orders?visit_id={visit_id}", headers=owner_headers)).json()
    lab_order = next(lo for lo in lab_orders if lo["order_id"] == order["id"])

    return {
        "clinic": clinic, "owner_headers": owner_headers, "doc_headers": doc_headers,
        "lab_headers": lab_headers, "recep_headers": recep_headers, "deps": deps,
        "visit_id": visit_id, "consultation_id": cid, "order": order, "lab_order": lab_order,
        "template": template,
    }


# --- Auto-attach + full lifecycle ---

async def test_laboratory_order_auto_attached_from_phase9_order(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    assert ctx["lab_order"]["status"] == "Requested"
    assert ctx["lab_order"]["test_type"] == "CBC"
    assert ctx["lab_order"]["template_id"] == ctx["template"]["id"]
    assert ctx["lab_order"]["order_number"] == ctx["order"]["order_number"]


async def test_full_lifecycle_with_timeline_events(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    lab_headers = ctx["lab_headers"]

    collect = await client.post(f"/api/v1/laboratory/orders/{lab_id}/collect", headers=lab_headers)
    assert collect.status_code == 200, collect.text
    assert collect.json()["status"] == "Collected"

    processing = await client.post(f"/api/v1/laboratory/orders/{lab_id}/start-processing", headers=lab_headers)
    assert processing.json()["status"] == "Processing"

    results = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=lab_headers,
        json={
            "results": [
                {"parameter_name": "Hemoglobin", "result_type": "Numeric", "numeric_value": 14.2, "normal_range": "12.0-16.0", "units": "g/dL", "interpretation": "Normal"},
                {"parameter_name": "Remarks", "result_type": "Text", "text_value": "No abnormal cells seen"},
            ]
        },
    )
    assert results.status_code == 200, results.text
    assert results.json()["status"] == "Completed"
    assert len(results.json()["results"]) == 2

    release = await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=lab_headers)
    assert release.status_code == 200
    assert release.json()["status"] == "Released"

    timeline = await client.get(f"/api/v1/visits/{ctx['visit_id']}", headers=ctx["owner_headers"])
    events = [e["event_type"] for e in timeline.json()["timeline"]]
    assert events.count("OrderCreated") == 1, "Should not double-record OrderCreated when the lab workflow row attaches"
    assert "LabSpecimenCollected" in events
    assert "LabProcessingStarted" in events
    assert "LabResultsEntered" in events
    assert "LabResultsReleased" in events

    # Underlying Phase 9 Order.status should mirror the lab workflow (the
    # sync-lesson check - Consultation page's Orders tab reads this).
    orders = await client.get(f"/api/v1/visits/{ctx['visit_id']}/orders", headers=ctx["owner_headers"])
    order_row = next(o for o in orders.json() if o["id"] == ctx["order"]["id"])
    assert order_row["status"] == "Completed"


async def test_illegal_transition_rejected(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    resp = await client.post(f"/api/v1/laboratory/orders/{lab_id}/start-processing", headers=ctx["lab_headers"])
    assert resp.status_code == 400


# --- Billing integration (idempotent) ---

async def test_completing_priced_order_creates_invoice_line_item(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_price="350.00")
    lab_id = ctx["lab_order"]["id"]
    lab_headers = ctx["lab_headers"]

    await client.post(f"/api/v1/laboratory/orders/{lab_id}/collect", headers=lab_headers)
    await client.post(f"/api/v1/laboratory/orders/{lab_id}/start-processing", headers=lab_headers)
    result = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=lab_headers,
        json={"results": [{"parameter_name": "Hemoglobin", "result_type": "Numeric", "numeric_value": 14.0}]},
    )
    invoice_item_id = result.json()["invoice_item_id"]
    assert invoice_item_id is not None

    invoice = (await client.get(f"/api/v1/visits/{ctx['visit_id']}/invoice", headers=ctx["owner_headers"])).json()
    lab_items = [i for i in invoice["items"] if i["item_type"] == "Laboratory"]
    assert len(lab_items) == 1
    assert lab_items[0]["id"] == invoice_item_id
    assert float(lab_items[0]["unit_price"]) == 350.00


async def test_billing_sync_idempotent_on_resubmit(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """The critical Phase-7/8/9-lesson check for this phase: resubmitting
    results while still Completed (not yet Released) must not create a
    second invoice line item for the same laboratory order."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_price="350.00")
    lab_id = ctx["lab_order"]["id"]
    lab_headers = ctx["lab_headers"]

    await client.post(f"/api/v1/laboratory/orders/{lab_id}/collect", headers=lab_headers)
    await client.post(f"/api/v1/laboratory/orders/{lab_id}/start-processing", headers=lab_headers)
    first = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=lab_headers,
        json={"results": [{"parameter_name": "Hemoglobin", "result_type": "Numeric", "numeric_value": 14.0}]},
    )
    first_item_id = first.json()["invoice_item_id"]

    second = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=lab_headers,
        json={"results": [{"parameter_name": "Hemoglobin", "result_type": "Numeric", "numeric_value": 15.0}]},
    )
    assert second.json()["invoice_item_id"] == first_item_id

    invoice = (await client.get(f"/api/v1/visits/{ctx['visit_id']}/invoice", headers=ctx["owner_headers"])).json()
    lab_items = [i for i in invoice["items"] if i["item_type"] == "Laboratory"]
    assert len(lab_items) == 1, "Resubmitting results must not duplicate the invoice line item"


async def test_two_orders_same_test_name_get_distinct_invoice_items(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """Regression test for a real bug found live: two different laboratory
    orders sharing the same test name (description) must never end up
    pointing at the same invoice_item_id."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_price="350.00")
    doc_headers = ctx["doc_headers"]
    lab_headers = ctx["lab_headers"]

    order2_resp = await client.post(
        f"/api/v1/consultations/{ctx['consultation_id']}/orders", headers=doc_headers,
        json={"order_category": "Laboratory", "priority": "Routine", "items": [{"item_name": "CBC"}]},
    )
    order2 = order2_resp.json()
    lab_orders = (await client.get(f"/api/v1/laboratory/orders?visit_id={ctx['visit_id']}", headers=ctx["owner_headers"])).json()
    lab_order2 = next(lo for lo in lab_orders if lo["order_id"] == order2["id"])

    for lab_id in (ctx["lab_order"]["id"], lab_order2["id"]):
        await client.post(f"/api/v1/laboratory/orders/{lab_id}/collect", headers=lab_headers)
        await client.post(f"/api/v1/laboratory/orders/{lab_id}/start-processing", headers=lab_headers)
        await client.post(
            f"/api/v1/laboratory/orders/{lab_id}/results", headers=lab_headers,
            json={"results": [{"parameter_name": "Hemoglobin", "result_type": "Numeric", "numeric_value": 14.0}]},
        )

    r1 = await client.get(f"/api/v1/laboratory/orders/{ctx['lab_order']['id']}", headers=ctx["owner_headers"])
    r2 = await client.get(f"/api/v1/laboratory/orders/{lab_order2['id']}", headers=ctx["owner_headers"])
    assert r1.json()["invoice_item_id"] != r2.json()["invoice_item_id"]

    invoice = (await client.get(f"/api/v1/visits/{ctx['visit_id']}/invoice", headers=ctx["owner_headers"])).json()
    lab_items = [i for i in invoice["items"] if i["item_type"] == "Laboratory"]
    assert len(lab_items) == 2


# --- Templates ---

async def test_template_crud_administrator_only(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    _, _, doc_user = None, None, None
    doc_email, _doc = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor")
    doc_token = await _login(client, doc_email, "TestPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    create = await client.post(
        "/api/v1/laboratory/templates", headers=owner_headers,
        json={"test_name": "Urinalysis", "specimen_type": "Urine", "default_price": "150.00", "parameters": []},
    )
    assert create.status_code == 201
    template_id = create.json()["id"]

    forbidden = await client.post(
        "/api/v1/laboratory/templates", headers=doc_headers,
        json={"test_name": "FBS", "default_price": "100.00", "parameters": []},
    )
    assert forbidden.status_code == 403

    read = await client.get("/api/v1/laboratory/templates", headers=doc_headers)
    assert read.status_code == 200
    assert any(t["id"] == template_id for t in read.json())

    update = await client.patch(f"/api/v1/laboratory/templates/{template_id}", headers=owner_headers, json={"default_price": "175.00"})
    assert update.status_code == 200
    assert float(update.json()["default_price"]) == 175.00

    forbidden_update = await client.patch(f"/api/v1/laboratory/templates/{template_id}", headers=doc_headers, json={"default_price": "1.00"})
    assert forbidden_update.status_code == 403


# --- Role gating ---

async def test_role_gating_lab_manages_doctor_creates_reception_view_only(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]

    doc_collect = await client.post(f"/api/v1/laboratory/orders/{lab_id}/collect", headers=ctx["doc_headers"])
    assert doc_collect.status_code == 403

    recep_collect = await client.post(f"/api/v1/laboratory/orders/{lab_id}/collect", headers=ctx["recep_headers"])
    assert recep_collect.status_code == 403

    recep_view = await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["recep_headers"])
    assert recep_view.status_code == 200

    lab_collect = await client.post(f"/api/v1/laboratory/orders/{lab_id}/collect", headers=ctx["lab_headers"])
    assert lab_collect.status_code == 200


# --- Visit / Patient laboratory history ---

async def test_visit_and_patient_laboratory_endpoints(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)

    visit_lab = await client.get(f"/api/v1/visits/{ctx['visit_id']}/laboratory", headers=ctx["owner_headers"])
    assert visit_lab.status_code == 200
    assert len(visit_lab.json()) == 1
    assert visit_lab.json()[0]["id"] == ctx["lab_order"]["id"]

    patient_id = ctx["deps"]["patient_id"]
    patient_lab = await client.get(f"/api/v1/patients/{patient_id}/laboratory", headers=ctx["owner_headers"])
    assert patient_lab.status_code == 200
    assert len(patient_lab.json()) == 1


# --- Tenant isolation ---

async def test_tenant_isolation(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    _clinic_b, _owner_b, owner_b_headers = await _owner_headers(client, make_clinic_with_owner)

    resp = await client.get(f"/api/v1/laboratory/orders/{ctx['lab_order']['id']}", headers=owner_b_headers)
    assert resp.status_code == 404

    list_resp = await client.get(f"/api/v1/laboratory/orders?visit_id={ctx['visit_id']}", headers=owner_b_headers)
    assert list_resp.status_code == 200
    assert list_resp.json() == []
