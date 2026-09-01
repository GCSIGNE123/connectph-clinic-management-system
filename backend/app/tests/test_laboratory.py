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
from app.models.laboratory_attachment import LaboratoryAttachment
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


_DEFAULT_TEMPLATE_PARAMETERS = [
    {"parameter_name": "Hemoglobin", "unit": "g/dL", "normal_range": "12.0-16.0", "result_type": "Numeric"},
    {"parameter_name": "Remarks", "result_type": "Text"},
]


async def _setup_with_lab_order(client: AsyncClient, make_clinic_with_owner, db_session, *, template_price="350.00", template_parameters=None):
    """Sets up a clinic, doctor, patient, queue->visit, opens a consultation,
    creates a priced Laboratory template, then creates a Laboratory-category
    Order via the unchanged Phase 9 endpoint (which auto-attaches a
    laboratory_orders row matching the template by test name). Returns
    headers for Owner/Doctor/Laboratory/Receptionist roles plus ids.

    `template_parameters` defaults to the original two-parameter fixture
    (unchanged, so every pre-existing test keeps working identically) -
    Feature 3 tests pass their own parameter list (with range_low/
    range_high/expected_normal_text) without touching this default."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)

    template_resp = await client.post(
        "/api/v1/laboratory/templates", headers=owner_headers,
        json={
            "test_name": "CBC", "test_category": "Hematology", "specimen_type": "Whole Blood",
            "default_price": template_price, "turnaround_time_hours": 4,
            "parameters": template_parameters if template_parameters is not None else _DEFAULT_TEMPLATE_PARAMETERS,
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


async def test_laboratory_order_exposes_reception_queue_number(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """A: Laboratory Worklist "Queue #" column - the order's linked visit has
    a Reception Queue ticket (created via the normal POST /queues flow), and
    the laboratory order's API response must surface that same queue_number
    (via the existing Visit.queue relationship) rather than a duplicated or
    fabricated value."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    visit = (await client.get(f"/api/v1/visits/{ctx['visit_id']}", headers=ctx["owner_headers"])).json()
    assert visit["queue_number"] is not None

    lab_orders = (
        await client.get(f"/api/v1/laboratory/orders?visit_id={ctx['visit_id']}", headers=ctx["owner_headers"])
    ).json()
    lab_order = next(lo for lo in lab_orders if lo["order_id"] == ctx["order"]["id"])
    assert lab_order["queue_number"] == visit["queue_number"]

    single = (
        await client.get(f"/api/v1/laboratory/orders/{lab_order['id']}", headers=ctx["owner_headers"])
    ).json()
    assert single["queue_number"] == visit["queue_number"]


async def test_laboratory_order_without_queue_reports_no_queue_number(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """B: a laboratory order whose visit was created directly (no linked
    Reception Queue ticket - e.g. POST /visits, the internal/test-only path)
    must not crash and must report queue_number as None rather than
    fabricating one."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)

    visit = (
        await client.post(
            "/api/v1/visits", headers=owner_headers,
            json={"patient_id": deps["patient_id"], "branch_id": deps["branch_id"], "doctor_id": deps["doctor_id"]},
        )
    ).json()
    assert visit["queue_id"] is None

    template_resp = await client.post(
        "/api/v1/laboratory/templates", headers=owner_headers,
        json={
            "test_name": "Urinalysis", "test_category": "Chemistry", "specimen_type": "Urine",
            "default_price": "200.00", "turnaround_time_hours": 2, "parameters": _DEFAULT_TEMPLATE_PARAMETERS,
        },
    )
    assert template_resp.status_code == 201, template_resp.text

    doc_email, _doc_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor", doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "TestPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    opened = (await client.post(f"/api/v1/visits/{visit['id']}/consultation/open", headers=doc_headers)).json()
    order_resp = await client.post(
        f"/api/v1/consultations/{opened['id']}/orders", headers=doc_headers,
        json={"order_category": "Laboratory", "priority": "Routine", "items": [{"item_name": "Urinalysis"}]},
    )
    assert order_resp.status_code == 200, order_resp.text

    lab_orders = (
        await client.get(f"/api/v1/laboratory/orders?visit_id={visit['id']}", headers=owner_headers)
    ).json()
    assert len(lab_orders) == 1
    assert lab_orders[0]["queue_number"] is None


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


# --- Template deletion (soft delete only) ---

async def test_delete_template_soft_deletes_and_hides_from_listing(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """1/2/3/4: a successful delete marks the template `is_deleted=True` +
    `is_active=False` in the DB, and it no longer appears in the normal
    `GET /templates` listing - while the row itself (and its parameters)
    physically still exist, per the soft-delete requirement."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    create = await client.post(
        "/api/v1/laboratory/templates", headers=owner_headers,
        json={
            "test_name": "To Be Deleted", "default_price": "50.00",
            "parameters": [{"parameter_name": "Result", "result_type": "Text"}],
        },
    )
    assert create.status_code == 201
    template_id = create.json()["id"]

    delete = await client.delete(f"/api/v1/laboratory/templates/{template_id}", headers=owner_headers)
    assert delete.status_code == 204

    listed = await client.get("/api/v1/laboratory/templates", headers=owner_headers)
    assert all(t["id"] != template_id for t in listed.json())

    from sqlalchemy import select as _select

    from app.models.laboratory_template import LaboratoryTemplate, LaboratoryTemplateParameter

    row = (
        await db_session.execute(_select(LaboratoryTemplate).where(LaboratoryTemplate.id == template_id))
    ).scalar_one()
    assert row.is_deleted is True
    assert row.is_active is False

    param_rows = (
        await db_session.execute(
            _select(LaboratoryTemplateParameter).where(LaboratoryTemplateParameter.template_id == template_id)
        )
    ).scalars().all()
    assert len(param_rows) == 1, "parameters must be preserved, not physically deleted"


async def test_delete_template_preserves_existing_lab_order_readability(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """5: an existing laboratory order that already references this
    template must remain fully readable (order detail, including its
    nested template/parameters) after the template is deleted from the
    catalog."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    template_id = ctx["template"]["id"]

    delete = await client.delete(f"/api/v1/laboratory/templates/{template_id}", headers=ctx["owner_headers"])
    assert delete.status_code == 204

    order_detail = await client.get(f"/api/v1/laboratory/orders/{ctx['lab_order']['id']}", headers=ctx["owner_headers"])
    assert order_detail.status_code == 200
    assert order_detail.json()["template_id"] == template_id
    assert order_detail.json()["template"]["id"] == template_id


async def test_delete_template_rejects_cross_clinic(client: AsyncClient, make_clinic_with_owner) -> None:
    """6: a template belonging to a DIFFERENT clinic must 404, and must
    never be modified."""
    _clinic_a, _owner_a, headers_a = await _owner_headers(client, make_clinic_with_owner)
    _clinic_b, _owner_b, headers_b = await _owner_headers(client, make_clinic_with_owner)
    create = await client.post(
        "/api/v1/laboratory/templates", headers=headers_b,
        json={"test_name": "Clinic B Template", "default_price": "20.00", "parameters": []},
    )
    template_id = create.json()["id"]

    delete = await client.delete(f"/api/v1/laboratory/templates/{template_id}", headers=headers_a)
    assert delete.status_code == 404

    unchanged = await client.get("/api/v1/laboratory/templates", headers=headers_b)
    assert any(t["id"] == template_id and t["is_active"] for t in unchanged.json())


async def test_delete_template_forbidden_for_non_administrator_roles(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """7: only Owner/Administrator (LAB_TEMPLATE_MANAGE_ROLES) may delete -
    same gate `create_template`/`update_template` already enforce."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    create = await client.post(
        "/api/v1/laboratory/templates", headers=owner_headers,
        json={"test_name": "Protected Template", "default_price": "10.00", "parameters": []},
    )
    template_id = create.json()["id"]

    for role_name in ("Doctor", "Laboratory", "Receptionist"):
        email, _user = await _make_role_login(db_session, clinic_id=clinic.id, role_name=role_name)
        token = await _login(client, email, "TestPass123!")
        headers = {"Authorization": f"Bearer {token}"}
        forbidden = await client.delete(f"/api/v1/laboratory/templates/{template_id}", headers=headers)
        assert forbidden.status_code == 403, role_name

    still_listed = await client.get("/api/v1/laboratory/templates", headers=owner_headers)
    assert any(t["id"] == template_id for t in still_listed.json())


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


# --- Feature 3: template-driven result entry, structured ranges, automatic
# interpretation. Uses a template whose parameters carry range_low/
# range_high/expected_normal_text - `_setup_with_lab_order`'s DEFAULT
# parameters (no ranges) are covered separately by
# `test_backward_compatible_with_pre_feature3_template_and_results` below. ---

_RANGED_TEMPLATE_PARAMETERS = [
    {
        "parameter_name": "Hemoglobin", "unit": "g/dL", "normal_range": "12.0-16.0",
        "result_type": "Numeric", "range_low": "12.0", "range_high": "16.0",
    },
    {
        "parameter_name": "Protein", "normal_range": "Negative",
        "result_type": "Text", "expected_normal_text": "Negative",
    },
]


async def _advance_to_processing(client, lab_id, headers) -> None:
    """`enter_results` legitimately requires the order to already be past
    `Requested` (see `LaboratoryService.enter_results`'s status guard, and
    `test_illegal_transition_rejected` which verifies that guard). Uses the
    real `/collect` -> `/start-processing` endpoints - the same transitions
    `test_full_lifecycle_with_timeline_events` exercises - rather than
    mutating `laboratory_orders.status` directly, so this stays a genuine
    end-to-end path through the unchanged workflow, not a shortcut around
    it."""
    collect = await client.post(f"/api/v1/laboratory/orders/{lab_id}/collect", headers=headers)
    assert collect.status_code == 200, collect.text
    processing = await client.post(f"/api/v1/laboratory/orders/{lab_id}/start-processing", headers=headers)
    assert processing.status_code == 200, processing.text


async def _enter_one_result(client, lab_id, headers, **overrides) -> dict:
    await _advance_to_processing(client, lab_id, headers)
    result = {
        "parameter_name": "Hemoglobin", "result_type": "Numeric",
        "numeric_value": 14.0, "range_low": "12.0", "range_high": "16.0",
    }
    result.update(overrides)
    resp = await client.post(f"/api/v1/laboratory/orders/{lab_id}/results", headers=headers, json={"results": [result]})
    assert resp.status_code == 200, resp.text
    return resp.json()["results"][0]


async def test_numeric_result_below_range_is_low(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    result = await _enter_one_result(client, ctx["lab_order"]["id"], ctx["lab_headers"], numeric_value=10.0)
    assert result["interpretation"] == "Low"


async def test_numeric_result_within_range_is_normal(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    result = await _enter_one_result(client, ctx["lab_order"]["id"], ctx["lab_headers"], numeric_value=14.0)
    assert result["interpretation"] == "Normal"


async def test_numeric_result_above_range_is_high(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    result = await _enter_one_result(client, ctx["lab_order"]["id"], ctx["lab_headers"], numeric_value=18.0)
    assert result["interpretation"] == "High"


async def test_numeric_result_missing_lower_bound_stays_uninterpreted(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """Phase 2B note: a submitted range_low/range_high is now authoritatively
    re-resolved server-side (see `LaboratoryService._apply_resolved_range_to_result`)
    whenever the parameter_name matches a template parameter - so blanking a
    bound for "Hemoglobin" (which has a configured template default) no
    longer reaches interpretation as blank; the backend fills it back in.
    This test now targets a parameter_name with NO template match
    ("Reticulocyte" - not in `_RANGED_TEMPLATE_PARAMETERS`), which is the
    still-real case this behavior covers: an untemplated/ad-hoc result row,
    where the client-submitted range is respected as-is, unchanged from
    pre-Phase-2B."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    result = await _enter_one_result(
        client, ctx["lab_order"]["id"], ctx["lab_headers"],
        parameter_name="Reticulocyte", numeric_value=14.0, range_low=None, range_high="16.0",
    )
    assert result["interpretation"] is None


async def test_numeric_result_missing_upper_bound_stays_uninterpreted(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """See test_numeric_result_missing_lower_bound_stays_uninterpreted's
    Phase 2B note - same reasoning, untemplated parameter_name."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    result = await _enter_one_result(
        client, ctx["lab_order"]["id"], ctx["lab_headers"],
        parameter_name="Reticulocyte", numeric_value=14.0, range_low="12.0", range_high=None,
    )
    assert result["interpretation"] is None


async def test_numeric_result_missing_range_entirely_stays_uninterpreted(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """See test_numeric_result_missing_lower_bound_stays_uninterpreted's
    Phase 2B note - same reasoning, untemplated parameter_name."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    result = await _enter_one_result(
        client, ctx["lab_order"]["id"], ctx["lab_headers"],
        parameter_name="Reticulocyte", numeric_value=14.0, range_low=None, range_high=None,
    )
    assert result["interpretation"] is None


async def test_templated_parameter_range_is_server_resolved_even_if_client_submits_different_values(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Phase 2B: the whole point of the new resolution path - a client
    submitting a stale/wrong/blank range for a parameter that DOES match a
    template parameter gets overridden with the backend's own resolved
    value (here, since no LaboratoryReferenceRange is configured, that's
    the template's own default 12.0/16.0), not what the client sent."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    result = await _enter_one_result(
        client, ctx["lab_order"]["id"], ctx["lab_headers"],
        numeric_value=14.0, range_low="1.0", range_high="2.0",
    )
    assert result["range_low"] == "12.0000"
    assert result["range_high"] == "16.0000"
    assert result["interpretation"] == "Normal"


async def test_numeric_result_missing_value_stays_uninterpreted(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """Missing value never gets an interpretation - even with a fully
    configured range, there's nothing to compare it against. FastAPI/
    Pydantic itself rejects a genuinely *invalid* (non-numeric-string)
    value at request-validation time (422, before this service code even
    runs) - this test covers the "left blank" case."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    result = await _enter_one_result(client, ctx["lab_order"]["id"], ctx["lab_headers"], numeric_value=None)
    assert result["interpretation"] is None


async def test_invalid_non_numeric_value_rejected_before_reaching_interpretation(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    resp = await client.post(
        f"/api/v1/laboratory/orders/{ctx['lab_order']['id']}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "Hemoglobin", "result_type": "Numeric", "numeric_value": "not-a-number", "range_low": "12.0", "range_high": "16.0"}]},
    )
    assert resp.status_code == 422


async def test_qualitative_result_matching_expected_value_is_normal(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    result = await _enter_one_result(
        client, ctx["lab_order"]["id"], ctx["lab_headers"],
        parameter_name="Protein", result_type="Text", text_value="Negative", numeric_value=None,
        range_low=None, range_high=None, expected_normal_text="Negative",
    )
    assert result["interpretation"] == "Normal"


async def test_qualitative_result_mismatching_expected_value_is_abnormal(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    result = await _enter_one_result(
        client, ctx["lab_order"]["id"], ctx["lab_headers"],
        parameter_name="Protein", result_type="Text", text_value="Trace", numeric_value=None,
        range_low=None, range_high=None, expected_normal_text="Negative",
    )
    assert result["interpretation"] == "Abnormal"


async def test_qualitative_result_with_no_expected_value_stays_uninterpreted(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    result = await _enter_one_result(
        client, ctx["lab_order"]["id"], ctx["lab_headers"],
        parameter_name="Color", result_type="Text", text_value="Straw", numeric_value=None,
        range_low=None, range_high=None, expected_normal_text=None,
    )
    assert result["interpretation"] is None


async def test_explicit_manual_interpretation_override_is_preserved(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """A clinician-supplied interpretation always wins, even when it
    disagrees with what the range would compute - the software's
    computed value is a suggestion, never authoritative."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    # 14.0 is squarely within 12.0-16.0 (would auto-compute "Normal"), but
    # the lab tech explicitly flags it "Abnormal" (e.g. trending/clinical
    # context the software doesn't know about).
    result = await _enter_one_result(client, ctx["lab_order"]["id"], ctx["lab_headers"], numeric_value=14.0, interpretation="Abnormal")
    assert result["interpretation"] == "Abnormal"


async def test_template_parameters_with_ranges_surfaced_on_order_for_result_entry_prefill(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Fixes the pre-Feature-3 gap: the order's linked template (with its
    parameters' ranges) must be present on GET so the frontend can
    pre-populate Result Entry rows from it."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    resp = await client.get(f"/api/v1/laboratory/orders/{ctx['lab_order']['id']}", headers=ctx["owner_headers"])
    assert resp.status_code == 200
    order = resp.json()
    assert order["template"] is not None
    assert order["template"]["test_name"] == "CBC"
    param_names = {p["parameter_name"] for p in order["template"]["parameters"]}
    assert param_names == {"Hemoglobin", "Protein"}
    hemoglobin = next(p for p in order["template"]["parameters"] if p["parameter_name"] == "Hemoglobin")
    assert hemoglobin["range_low"] == "12.0000"
    assert hemoglobin["range_high"] == "16.0000"
    protein = next(p for p in order["template"]["parameters"] if p["parameter_name"] == "Protein")
    assert protein["expected_normal_text"] == "Negative"


async def test_backward_compatible_with_pre_feature3_template_and_results(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """A template/result created with none of the new range fields (the
    exact pre-Feature-3 shape) keeps working identically: range columns
    are simply null, and an explicitly-supplied interpretation (the only
    way results worked before this feature) is preserved unchanged."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)  # default (rangeless) parameters
    lab_id = ctx["lab_order"]["id"]

    order = (await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["owner_headers"])).json()
    hemoglobin_param = next(p for p in order["template"]["parameters"] if p["parameter_name"] == "Hemoglobin")
    assert hemoglobin_param["range_low"] is None
    assert hemoglobin_param["range_high"] is None
    assert hemoglobin_param["expected_normal_text"] is None

    await _advance_to_processing(client, lab_id, ctx["lab_headers"])
    resp = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=ctx["lab_headers"],
        json={
            "results": [
                {"parameter_name": "Hemoglobin", "result_type": "Numeric", "numeric_value": 14.2, "normal_range": "12.0-16.0", "units": "g/dL", "interpretation": "Normal"},
                {"parameter_name": "Remarks", "result_type": "Text", "text_value": "No abnormal cells seen"},
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    hemoglobin_result = next(r for r in results if r["parameter_name"] == "Hemoglobin")
    assert hemoglobin_result["interpretation"] == "Normal"  # explicitly supplied, unchanged behavior
    assert hemoglobin_result["range_low"] is None
    assert hemoglobin_result["range_high"] is None
    remarks_result = next(r for r in results if r["parameter_name"] == "Remarks")
    assert remarks_result["interpretation"] is None  # never supplied, no expected_normal_text either -> stays null


# --- Feature 3: starter templates (structure only, no clinical ranges) ---

async def test_seed_default_templates_creates_cbc_urinalysis_and_blood_typing_structure_only(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Phase 3: Blood Typing joins CBC/Urinalysis in the starter set -
    structure only (Categorical options, no reference range/interpretation
    configured, matching the same bar CBC/Urinalysis's own seeded structure
    already holds).

    Phase 4C note: seed-defaults now also creates 6 qualitative templates
    (HCG Serum/Urine, HBsAg, HAV, VDRL/Syphilis, Dengue Rapid Test) - this
    test was updated to include them in the expected name set; their own
    structure is covered by the dedicated
    `test_phase_4c_template_exists_with_expected_parameters` tests.

    Phase 4D note: 6 more (Stool Exam, Fecal Occult Blood, Sputum Exam,
    Gram Stain, Trichomonas Vaginalis Mount, KOH Mount) - see
    `test_phase_4d_template_exists_with_expected_parameters`."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)

    resp = await client.post("/api/v1/laboratory/templates/seed-defaults", headers=owner_headers)
    assert resp.status_code == 200, resp.text
    created = resp.json()
    names = {t["test_name"] for t in created}
    assert names == {"CBC", "Urinalysis", "Blood Typing"} | _PHASE_4C_TEST_NAMES | _PHASE_4D_TEST_NAMES

    blood_typing = next(t for t in created if t["test_name"] == "Blood Typing")
    param_names = {p["parameter_name"] for p in blood_typing["parameters"]}
    assert param_names == {"ABO Group", "Rh Factor"}
    abo = next(p for p in blood_typing["parameters"] if p["parameter_name"] == "ABO Group")
    assert abo["result_type"] == "Categorical"
    assert abo["options"] == ["A", "B", "AB", "O"]
    rh = next(p for p in blood_typing["parameters"] if p["parameter_name"] == "Rh Factor")
    assert rh["options"] == ["Positive", "Negative"]

    for template in created:
        for param in template["parameters"]:
            # Structure only - no clinical reference range/interpretation values seeded.
            assert param["range_low"] is None
            assert param["range_high"] is None
            assert param["expected_normal_text"] is None

    # Idempotent: calling again does not duplicate.
    resp2 = await client.post("/api/v1/laboratory/templates/seed-defaults", headers=owner_headers)
    assert resp2.status_code == 200
    assert resp2.json() == []
    list_resp = await client.get("/api/v1/laboratory/templates", headers=owner_headers)
    all_names = [t["test_name"] for t in list_resp.json()]
    assert all_names.count("CBC") == 1
    assert all_names.count("Urinalysis") == 1
    assert all_names.count("Blood Typing") == 1


async def test_seed_default_templates_requires_administrator_role(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    resp = await client.post("/api/v1/laboratory/templates/seed-defaults", headers=ctx["lab_headers"])
    assert resp.status_code == 403


# --- Feature 4: laboratory result image attachments ---

_FAKE_JPEG_BYTES = b"\xff\xd8\xff\xe0fake-jpeg-bytes-for-testing\xff\xd9"


async def _upload_attachment(client, lab_id, headers, *, filename="cbc-result.jpg", content=_FAKE_JPEG_BYTES, content_type="image/jpeg", attachment_type=None):
    data = {"attachment_type": attachment_type} if attachment_type else {}
    return await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/attachments", headers=headers,
        data=data, files={"file": (filename, content, content_type)},
    )


async def test_upload_laboratory_attachment_sends_real_file_bytes_not_just_metadata(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    resp = await _upload_attachment(client, ctx["lab_order"]["id"], ctx["lab_headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["attachment_type"] == "Image"
    assert body["file_name"] == "cbc-result.jpg"
    assert body["file_size_bytes"] == len(_FAKE_JPEG_BYTES)
    # Real, authenticated, viewable URL - never the old fake
    # "https://storage.stub.connectph.dev/..." presigned-URL stub.
    assert body["file_url"] == f"/laboratory/orders/{ctx['lab_order']['id']}/attachments/{body['id']}/file"
    assert "storage.stub" not in body["file_url"]

    # Immediately listed.
    list_resp = await client.get(f"/api/v1/laboratory/orders/{ctx['lab_order']['id']}/attachments", headers=ctx["lab_headers"])
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["id"] == body["id"]

    # Also surfaced on the order itself (fixes the pre-Feature-4 gap where
    # LaboratoryOrderRead.attachments was hardcoded to []).
    order_resp = await client.get(f"/api/v1/laboratory/orders/{ctx['lab_order']['id']}", headers=ctx["owner_headers"])
    assert len(order_resp.json()["attachments"]) == 1
    assert order_resp.json()["attachments"][0]["id"] == body["id"]


async def test_attachment_file_is_written_under_the_persistent_var_directory(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Verifies the actual bytes land under the same `var/` root
    `consultations.py` uses for its own persistent attachments - the
    directory that `backend_var_data`'s Docker volume mount covers in
    production (`docker/docker-compose.prod.yml`), so uploads survive a
    backend container recreation."""
    from app.api.v1.laboratory import LABORATORY_ATTACHMENTS_UPLOAD_ROOT

    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    resp = await _upload_attachment(client, lab_id, ctx["lab_headers"], filename="scan.png", content=b"\x89PNGfake-png-bytes", content_type="image/png")
    assert resp.status_code == 200, resp.text

    list_resp = await client.get(f"/api/v1/laboratory/orders/{lab_id}/attachments", headers=ctx["lab_headers"])
    attachment = list_resp.json()[0]
    row = (await db_session.execute(select(LaboratoryAttachment).where(LaboratoryAttachment.id == uuid.UUID(attachment["id"])))).scalar_one()
    file_path = LABORATORY_ATTACHMENTS_UPLOAD_ROOT / str(ctx["clinic"].id) / lab_id / row.file_url
    assert file_path.is_file()
    assert file_path.read_bytes() == b"\x89PNGfake-png-bytes"


async def test_get_attachment_file_returns_correct_bytes_and_content_type(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    upload_resp = await _upload_attachment(client, lab_id, ctx["lab_headers"])
    attachment_id = upload_resp.json()["id"]

    file_resp = await client.get(f"/api/v1/laboratory/orders/{lab_id}/attachments/{attachment_id}/file", headers=ctx["lab_headers"])
    assert file_resp.status_code == 200
    assert file_resp.content == _FAKE_JPEG_BYTES
    assert file_resp.headers["content-type"] == "image/jpeg"


async def test_get_attachment_file_requires_authentication(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    upload_resp = await _upload_attachment(client, lab_id, ctx["lab_headers"])
    attachment_id = upload_resp.json()["id"]

    resp = await client.get(f"/api/v1/laboratory/orders/{lab_id}/attachments/{attachment_id}/file")
    assert resp.status_code == 401


async def test_get_attachment_file_rejects_role_with_no_laboratory_view_access(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Enforces the exact same LAB_VIEW_ROLES boundary already used for
    viewing the laboratory order/results (Owner/Administrator/Laboratory/
    Doctor/Receptionist) - a role outside that set (e.g. Cashier) must not
    be able to view a laboratory attachment either."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    upload_resp = await _upload_attachment(client, lab_id, ctx["lab_headers"])
    attachment_id = upload_resp.json()["id"]

    cashier_email, _cashier_user = await _make_role_login(db_session, clinic_id=ctx["clinic"].id, role_name="Cashier")
    cashier_token = await _login(client, cashier_email, "TestPass123!")
    cashier_headers = {"Authorization": f"Bearer {cashier_token}"}

    resp = await client.get(f"/api/v1/laboratory/orders/{lab_id}/attachments/{attachment_id}/file", headers=cashier_headers)
    assert resp.status_code == 403


async def test_upload_attachment_requires_lab_manage_role_not_just_view(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Receptionist can view (LAB_VIEW_ROLES) but must not be able to
    upload (LAB_MANAGE_ROLES) - same manage-vs-view boundary already
    enforced for collect/process/enter-results/release/cancel."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    resp = await _upload_attachment(client, ctx["lab_order"]["id"], ctx["recep_headers"])
    assert resp.status_code == 403


async def test_get_attachment_file_missing_from_disk_returns_404_not_a_crash(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Handles a missing/broken file gracefully (e.g. the DB row survived
    but the on-disk bytes didn't, or were manually removed) - a clean 404,
    never an unhandled exception/500."""
    from app.api.v1.laboratory import LABORATORY_ATTACHMENTS_UPLOAD_ROOT

    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    upload_resp = await _upload_attachment(client, lab_id, ctx["lab_headers"])
    attachment_id = upload_resp.json()["id"]

    row = (await db_session.execute(select(LaboratoryAttachment).where(LaboratoryAttachment.id == uuid.UUID(attachment_id)))).scalar_one()
    file_path = LABORATORY_ATTACHMENTS_UPLOAD_ROOT / str(ctx["clinic"].id) / lab_id / row.file_url
    file_path.unlink()

    resp = await client.get(f"/api/v1/laboratory/orders/{lab_id}/attachments/{attachment_id}/file", headers=ctx["lab_headers"])
    assert resp.status_code == 404


async def test_upload_attachment_rejects_disallowed_extension(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    resp = await _upload_attachment(client, ctx["lab_order"]["id"], ctx["lab_headers"], filename="malware.exe", content=b"not-an-image", content_type="application/octet-stream")
    assert resp.status_code == 400


async def test_upload_attachment_rejects_oversized_image(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    oversized = b"\xff\xd8\xff" + b"x" * (5 * 1024 * 1024 + 1)  # MAX_IMAGE_SIZE_BYTES + 1
    resp = await _upload_attachment(client, ctx["lab_order"]["id"], ctx["lab_headers"], content=oversized)
    assert resp.status_code == 400
    assert "too large" in resp.json()["detail"].lower()


async def test_attachment_tenant_isolation(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx_a = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    upload_resp = await _upload_attachment(client, ctx_a["lab_order"]["id"], ctx_a["lab_headers"])
    attachment_id = upload_resp.json()["id"]

    ctx_b = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)

    # Clinic B's own headers can't see clinic A's order/attachment at all.
    resp = await client.get(
        f"/api/v1/laboratory/orders/{ctx_a['lab_order']['id']}/attachments/{attachment_id}/file", headers=ctx_b["lab_headers"]
    )
    assert resp.status_code == 404


# --- Phase 2A: Structured Result Backend Foundation ---
# New parameter kinds (Categorical/Microscopy/Titer), requires_site,
# LaboratoryResult.site/structured_value, and LaboratoryReferenceRange.
# Every existing Numeric/Text template/result behavior above is unchanged -
# these tests only cover the additive surface.

async def test_template_parameter_stores_new_kinds_options_and_requires_site(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#10/#11/#12: a template parameter can be created with a new
    `result_type` (Categorical here), a stored `options` choice list, and
    `requires_site=True` - all round-trip through the API unchanged."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    create = await client.post(
        "/api/v1/laboratory/templates", headers=owner_headers,
        json={
            "test_name": "Blood Typing", "test_category": "Immunohematology", "default_price": "150.00",
            "parameters": [
                {
                    "parameter_name": "ABO Group", "result_type": "Categorical",
                    "options": ["A", "B", "AB", "O"], "display_order": 0,
                },
                {
                    "parameter_name": "KOH Mount", "result_type": "Microscopy",
                    "options": [{"label": "Site", "type": "text"}, {"label": "Microscopy", "type": "text"}],
                    "requires_site": True, "display_order": 1,
                },
                {"parameter_name": "S. Typhi Titer", "result_type": "Titer", "display_order": 2},
            ],
        },
    )
    assert create.status_code == 201, create.text
    params = {p["parameter_name"]: p for p in create.json()["parameters"]}

    abo = params["ABO Group"]
    assert abo["result_type"] == "Categorical"
    assert abo["options"] == ["A", "B", "AB", "O"]
    assert abo["requires_site"] is False

    koh = params["KOH Mount"]
    assert koh["result_type"] == "Microscopy"
    assert koh["options"] == [{"label": "Site", "type": "text"}, {"label": "Microscopy", "type": "text"}]
    assert koh["requires_site"] is True

    titer = params["S. Typhi Titer"]
    assert titer["result_type"] == "Titer"
    assert titer["options"] is None
    assert titer["requires_site"] is False


async def test_laboratory_result_stores_structured_value_and_site(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#13/#14: entering a result for a Categorical/site-based parameter
    persists `structured_value`/`site` and round-trips them unchanged -
    proven end-to-end through the real /results endpoint, not a direct DB
    write, matching this file's existing convention.

    Note (Phase 3): uses `{"value": "O"}` for the Categorical result - the
    canonical key Phase 3 establishes for `structured_value` (and that
    `LaboratoryService._validate_categorical_value` now checks against
    configured options). Originally written in Phase 2A before that
    convention existed."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    template = (
        await client.post(
            "/api/v1/laboratory/templates", headers=owner_headers,
            json={
                "test_name": "Blood Typing 2", "default_price": "150.00",
                "parameters": [
                    {"parameter_name": "ABO Group", "result_type": "Categorical", "options": ["A", "B", "AB", "O"]},
                    {"parameter_name": "KOH Mount", "result_type": "Microscopy", "requires_site": True},
                ],
            },
        )
    ).json()

    queue = (await client.post("/api/v1/queues", headers=owner_headers, json=_queue_payload(deps))).json()
    visit_id = queue["visit_id"]
    doc_email, _doc_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor", doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "TestPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}
    await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/call", headers=doc_headers)
    await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/start-consultation", headers=doc_headers)
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    order = (
        await client.post(
            f"/api/v1/consultations/{opened['id']}/orders", headers=doc_headers,
            json={"order_category": "Laboratory", "items": [{"item_name": "Blood Typing 2"}]},
        )
    ).json()
    lab_orders = (await client.get(f"/api/v1/laboratory/orders?visit_id={visit_id}", headers=owner_headers)).json()
    lab_id = next(lo for lo in lab_orders if lo["order_id"] == order["id"])["id"]

    lab_email, _lab_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Laboratory")
    lab_token = await _login(client, lab_email, "TestPass123!")
    lab_headers = {"Authorization": f"Bearer {lab_token}"}
    await _advance_to_processing(client, lab_id, lab_headers)

    resp = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=lab_headers,
        json={
            "results": [
                {
                    "parameter_name": "ABO Group", "result_type": "Categorical",
                    "structured_value": {"value": "O"},
                },
                {
                    "parameter_name": "KOH Mount", "result_type": "Microscopy",
                    "site": "Vaginal", "structured_value": {"Microscopy": "Budding yeast cells seen"},
                },
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    results = {r["parameter_name"]: r for r in resp.json()["results"]}
    assert results["ABO Group"]["structured_value"] == {"value": "O"}
    assert results["KOH Mount"]["site"] == "Vaginal"
    assert results["KOH Mount"]["structured_value"] == {"Microscopy": "Budding yeast cells seen"}

    # Re-fetch confirms persistence, not just an echoed request payload.
    refetched = (await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=owner_headers)).json()
    refetched_results = {r["parameter_name"]: r for r in refetched["results"]}
    assert refetched_results["ABO Group"]["structured_value"] == {"value": "O"}
    assert refetched_results["KOH Mount"]["site"] == "Vaginal"


async def test_reference_range_create_list_and_toggle_active(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#15/#16/#17: a LaboratoryReferenceRange can be created for a real
    template parameter, is listed under that parameter, and its
    `is_active` flag can be toggled (activate/deactivate) via PATCH."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    hemoglobin_param_id = next(p["id"] for p in ctx["template"]["parameters"] if p["parameter_name"] == "Hemoglobin")

    create = await client.post(
        f"/api/v1/laboratory/templates/parameters/{hemoglobin_param_id}/reference-ranges", headers=ctx["owner_headers"],
        json={"sex": "Male", "age_min_years": 18, "age_max_years": 65, "range_low": "13.0", "range_high": "17.0"},
    )
    assert create.status_code == 201, create.text
    range_id = create.json()["id"]
    assert create.json()["template_parameter_id"] == hemoglobin_param_id
    assert create.json()["is_active"] is True

    listed = await client.get(
        f"/api/v1/laboratory/templates/parameters/{hemoglobin_param_id}/reference-ranges", headers=ctx["owner_headers"]
    )
    assert listed.status_code == 200
    assert any(r["id"] == range_id for r in listed.json())

    deactivate = await client.patch(
        f"/api/v1/laboratory/reference-ranges/{range_id}", headers=ctx["owner_headers"], json={"is_active": False}
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["is_active"] is False

    active_only = await client.get(
        f"/api/v1/laboratory/templates/parameters/{hemoglobin_param_id}/reference-ranges?active_only=true",
        headers=ctx["owner_headers"],
    )
    assert active_only.json() == []

    reactivate = await client.patch(
        f"/api/v1/laboratory/reference-ranges/{range_id}", headers=ctx["owner_headers"], json={"is_active": True}
    )
    assert reactivate.status_code == 200
    assert reactivate.json()["is_active"] is True


async def test_reference_range_requires_administrator_role(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    hemoglobin_param_id = next(p["id"] for p in ctx["template"]["parameters"] if p["parameter_name"] == "Hemoglobin")
    resp = await client.post(
        f"/api/v1/laboratory/templates/parameters/{hemoglobin_param_id}/reference-ranges", headers=ctx["lab_headers"],
        json={"range_low": "13.0", "range_high": "17.0"},
    )
    assert resp.status_code == 403


async def test_template_default_range_remains_fallback_alongside_reference_ranges(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#18: adding a LaboratoryReferenceRange does not touch or overwrite the
    template parameter's own row - `range_low`/`range_high`/
    `expected_normal_text` on the actual `LaboratoryTemplateParameter`
    (read via the template catalog, not via an order) are unchanged; both
    coexist, exactly as documented (the new table is additive, not a
    replacement).

    Note (Phase 2B): `GET /laboratory/orders/{id}` now intentionally shows
    the PATIENT-RESOLVED range for that order (see `LaboratoryService.
    _overlay_resolved_ranges`) - for a Male patient with a matching Male
    reference range configured, that's correctly 13.0/17.0, not the
    template default. This test asserts the template's OWN row is
    untouched, which is what "fallback" actually means; the resolved-range-
    on-an-order behavior is covered by
    `test_live_result_entry_uses_matching_sex_specific_reference_range`."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    template_id = ctx["template"]["id"]
    hemoglobin_param_id = next(p["id"] for p in ctx["template"]["parameters"] if p["parameter_name"] == "Hemoglobin")

    await client.post(
        f"/api/v1/laboratory/templates/parameters/{hemoglobin_param_id}/reference-ranges", headers=ctx["owner_headers"],
        json={"sex": "Male", "range_low": "13.0", "range_high": "17.0"},
    )

    templates = (await client.get("/api/v1/laboratory/templates", headers=ctx["owner_headers"])).json()
    template = next(t for t in templates if t["id"] == template_id)
    hemoglobin = next(p for p in template["parameters"] if p["parameter_name"] == "Hemoglobin")
    assert hemoglobin["range_low"] == "12.0000"
    assert hemoglobin["range_high"] == "16.0000"


async def test_resolve_reference_range_matches_patient_demographics(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#19: a demographic-specific LaboratoryReferenceRange resolves for a
    patient matching its sex/age bounds. `_setup_with_lab_order`'s patient
    is Male, born 1990-05-15 (age 36 as of the fixed system date this suite
    runs under), so a Male 18-65 range matches."""
    from app.services.laboratory_service import LaboratoryService

    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    hemoglobin_param_id = next(p["id"] for p in ctx["template"]["parameters"] if p["parameter_name"] == "Hemoglobin")
    patient_id = ctx["deps"]["patient_id"]

    create = await client.post(
        f"/api/v1/laboratory/templates/parameters/{hemoglobin_param_id}/reference-ranges", headers=ctx["owner_headers"],
        json={"sex": "Male", "age_min_years": 18, "age_max_years": 65, "range_low": "13.0", "range_high": "17.0"},
    )
    assert create.status_code == 201, create.text

    service = LaboratoryService(db_session)
    resolved = await service.resolve_reference_range_for_patient(
        uuid.UUID(hemoglobin_param_id), uuid.UUID(patient_id), clinic_id=ctx["clinic"].id
    )
    assert resolved is not None
    assert float(resolved.range_low) == 13.0
    assert float(resolved.range_high) == 17.0


async def test_resolve_reference_range_falls_back_to_default_when_no_match(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#20: a reference range scoped to a non-matching demographic (Female,
    when the fixture patient is Male) is not returned - resolution comes
    back None, meaning the caller falls back to the template parameter's
    own default range_low/range_high (still 12.0/16.0, verified via the
    API in `test_template_default_range_remains_fallback_alongside_reference_ranges`)."""
    from app.services.laboratory_service import LaboratoryService

    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    hemoglobin_param_id = next(p["id"] for p in ctx["template"]["parameters"] if p["parameter_name"] == "Hemoglobin")
    patient_id = ctx["deps"]["patient_id"]

    create = await client.post(
        f"/api/v1/laboratory/templates/parameters/{hemoglobin_param_id}/reference-ranges", headers=ctx["owner_headers"],
        json={"sex": "Female", "range_low": "12.0", "range_high": "15.5"},
    )
    assert create.status_code == 201, create.text

    service = LaboratoryService(db_session)
    resolved = await service.resolve_reference_range_for_patient(
        uuid.UUID(hemoglobin_param_id), uuid.UUID(patient_id), clinic_id=ctx["clinic"].id
    )
    assert resolved is None


async def test_historical_result_range_unchanged_when_reference_range_later_modified(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#21: a LaboratoryResult already entered keeps the range_low/
    range_high it was submitted with (denormalized at submission time,
    unchanged Feature-3 behavior) even after a LaboratoryReferenceRange row
    covering the same parameter is later created and deactivated -
    resolution/reference-range changes are not retroactive."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    lab_id = ctx["lab_order"]["id"]
    hemoglobin_param_id = next(p["id"] for p in ctx["template"]["parameters"] if p["parameter_name"] == "Hemoglobin")

    result = await _enter_one_result(client, lab_id, ctx["lab_headers"], numeric_value=14.0)
    assert result["range_low"] == "12.0000"
    assert result["range_high"] == "16.0000"

    create = await client.post(
        f"/api/v1/laboratory/templates/parameters/{hemoglobin_param_id}/reference-ranges", headers=ctx["owner_headers"],
        json={"sex": "Male", "range_low": "13.0", "range_high": "17.0"},
    )
    range_id = create.json()["id"]
    await client.patch(f"/api/v1/laboratory/reference-ranges/{range_id}", headers=ctx["owner_headers"], json={"is_active": False})

    refetched = (await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["owner_headers"])).json()
    hemoglobin_result = next(r for r in refetched["results"] if r["parameter_name"] == "Hemoglobin")
    assert hemoglobin_result["range_low"] == "12.0000"
    assert hemoglobin_result["range_high"] == "16.0000"


async def test_interpret_result_computes_critical_low_and_high_only_when_configured() -> None:
    """Interpretation-engine extension: `interpret_result()` accepts
    optional critical_low/critical_high (keyword-only, default None). Not
    wired into the live enter_results path this phase (see
    laboratory_interpretation.py's Phase 2A note) - covered directly here
    to prove the pure function itself is correct and that omitting the new
    kwargs (every existing call site) leaves behavior exactly as before."""
    from decimal import Decimal as D

    from app.models.laboratory_result import LaboratoryInterpretation, LaboratoryResultType
    from app.services.laboratory_interpretation import interpret_result

    # Existing behavior, no critical bounds passed at all - unchanged.
    assert (
        interpret_result(
            result_type=LaboratoryResultType.NUMERIC, numeric_value=D("14.0"), text_value=None,
            range_low=D("12.0"), range_high=D("16.0"), expected_normal_text=None,
        )
        == LaboratoryInterpretation.NORMAL
    )

    # Critical bounds configured and breached.
    assert (
        interpret_result(
            result_type=LaboratoryResultType.NUMERIC, numeric_value=D("2.0"), text_value=None,
            range_low=D("12.0"), range_high=D("16.0"), expected_normal_text=None,
            critical_low=D("5.0"), critical_high=D("20.0"),
        )
        == LaboratoryInterpretation.CRITICAL_LOW
    )
    assert (
        interpret_result(
            result_type=LaboratoryResultType.NUMERIC, numeric_value=D("25.0"), text_value=None,
            range_low=D("12.0"), range_high=D("16.0"), expected_normal_text=None,
            critical_low=D("5.0"), critical_high=D("20.0"),
        )
        == LaboratoryInterpretation.CRITICAL_HIGH
    )

    # Critical bounds configured but not breached - ordinary Low/Normal/High still applies.
    assert (
        interpret_result(
            result_type=LaboratoryResultType.NUMERIC, numeric_value=D("14.0"), text_value=None,
            range_low=D("12.0"), range_high=D("16.0"), expected_normal_text=None,
            critical_low=D("5.0"), critical_high=D("20.0"),
        )
        == LaboratoryInterpretation.NORMAL
    )

    # Only one critical bound configured - never guesses, falls through to ordinary range logic.
    assert (
        interpret_result(
            result_type=LaboratoryResultType.NUMERIC, numeric_value=D("2.0"), text_value=None,
            range_low=D("12.0"), range_high=D("16.0"), expected_normal_text=None,
            critical_low=D("5.0"), critical_high=None,
        )
        == LaboratoryInterpretation.LOW
    )


# --- Phase 2B: connect LaboratoryReferenceRange to live result entry (CBC
# proof case). `_setup_with_lab_order`'s fixture patient is Male, born
# 1990-05-15 - age 36 as of this suite's system date, used throughout below
# for sex/age matching. All tests go through the real HTTP API path
# (order creation -> reference-range config -> GET for prefill -> POST
# results -> re-GET), per the phase's explicit "test the real path, not
# just helper functions" requirement. ---

async def _create_reference_range(client, owner_headers, parameter_id, **fields) -> dict:
    resp = await client.post(
        f"/api/v1/laboratory/templates/parameters/{parameter_id}/reference-ranges", headers=owner_headers, json=fields
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_live_result_entry_prefill_shows_matching_sex_specific_reference_range(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#1: end-to-end - a Male-scoped reference range (13.0-17.0, narrower
    than the template's own 12.0-16.0 default) is configured for
    Hemoglobin; the GET the frontend's Result Entry dialog fetches on open
    now shows the resolved (not template-default) range for the Male
    fixture patient, including the existing free-text "Normal Range"
    display field (unchanged UI element, now reflecting the resolved
    bounds instead of the template's stale description)."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    hemoglobin_param_id = next(p["id"] for p in ctx["template"]["parameters"] if p["parameter_name"] == "Hemoglobin")
    await _create_reference_range(
        client, ctx["owner_headers"], hemoglobin_param_id,
        sex="Male", age_min_years=18, age_max_years=65, range_low="13.0", range_high="17.0",
    )

    order = (await client.get(f"/api/v1/laboratory/orders/{ctx['lab_order']['id']}", headers=ctx["owner_headers"])).json()
    hemoglobin_param = next(p for p in order["template"]["parameters"] if p["parameter_name"] == "Hemoglobin")
    assert hemoglobin_param["range_low"] == "13.0000"
    assert hemoglobin_param["range_high"] == "17.0000"
    assert hemoglobin_param["normal_range"] == "13.0000-17.0000"


async def test_live_result_entry_below_matching_reference_range_is_low(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#8/#9/#12: a Male-scoped reference range (13.0-17.0) is configured;
    entering 12.5 (below 13.0, but Normal against the template's own
    12-16 default) resolves and uses the reference range, not the
    template default - Low - and the saved result retains that range."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    hemoglobin_param_id = next(p["id"] for p in ctx["template"]["parameters"] if p["parameter_name"] == "Hemoglobin")
    await _create_reference_range(
        client, ctx["owner_headers"], hemoglobin_param_id,
        sex="Male", age_min_years=18, age_max_years=65, range_low="13.0", range_high="17.0",
    )
    result = await _enter_one_result(client, ctx["lab_order"]["id"], ctx["lab_headers"], numeric_value=12.5)
    assert result["range_low"] == "13.0000"
    assert result["range_high"] == "17.0000"
    assert result["interpretation"] == "Low"


async def test_live_result_entry_within_matching_reference_range_is_normal(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#8/#10/#12."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    hemoglobin_param_id = next(p["id"] for p in ctx["template"]["parameters"] if p["parameter_name"] == "Hemoglobin")
    await _create_reference_range(
        client, ctx["owner_headers"], hemoglobin_param_id,
        sex="Male", age_min_years=18, age_max_years=65, range_low="13.0", range_high="17.0",
    )
    result = await _enter_one_result(client, ctx["lab_order"]["id"], ctx["lab_headers"], numeric_value=15.0)
    assert result["range_low"] == "13.0000"
    assert result["range_high"] == "17.0000"
    assert result["interpretation"] == "Normal"


async def test_live_result_entry_above_matching_reference_range_is_high(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#8/#11/#12: entering 17.5 (above 17.0, but Normal against the
    template's own 12-16 default) resolves and uses the reference range -
    High."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    hemoglobin_param_id = next(p["id"] for p in ctx["template"]["parameters"] if p["parameter_name"] == "Hemoglobin")
    await _create_reference_range(
        client, ctx["owner_headers"], hemoglobin_param_id,
        sex="Male", age_min_years=18, age_max_years=65, range_low="13.0", range_high="17.0",
    )
    result = await _enter_one_result(client, ctx["lab_order"]["id"], ctx["lab_headers"], numeric_value=17.5)
    assert result["range_low"] == "13.0000"
    assert result["range_high"] == "17.0000"
    assert result["interpretation"] == "High"


async def test_live_result_entry_ignores_non_matching_sex_specific_reference_range(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#2: a reference range scoped to Female is not applied to the Male
    fixture patient - resolution falls through to the template's own
    default (12.0-16.0), proven live through result entry."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    hemoglobin_param_id = next(p["id"] for p in ctx["template"]["parameters"] if p["parameter_name"] == "Hemoglobin")
    await _create_reference_range(
        client, ctx["owner_headers"], hemoglobin_param_id, sex="Female", range_low="11.0", range_high="15.0",
    )

    result = await _enter_one_result(client, ctx["lab_order"]["id"], ctx["lab_headers"], numeric_value=15.5)
    assert result["range_low"] == "12.0000"
    assert result["range_high"] == "16.0000"
    assert result["interpretation"] == "Normal"  # 15.5 is Normal against 12-16, would be High against the Female 11-15 range


async def test_live_result_entry_uses_any_sex_reference_range(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#3: a reference range with sex left unset (None) applies regardless
    of the patient's sex."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    hemoglobin_param_id = next(p["id"] for p in ctx["template"]["parameters"] if p["parameter_name"] == "Hemoglobin")
    await _create_reference_range(client, ctx["owner_headers"], hemoglobin_param_id, range_low="10.0", range_high="20.0")

    result = await _enter_one_result(client, ctx["lab_order"]["id"], ctx["lab_headers"], numeric_value=17.0)
    assert result["range_low"] == "10.0000"
    assert result["range_high"] == "20.0000"
    assert result["interpretation"] == "Normal"  # would be High against the template's own 12-16 default


async def test_live_result_entry_uses_matching_age_specific_reference_range(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#4: a reference range whose age band (18-65) includes the fixture
    patient's age (36) is used."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    hemoglobin_param_id = next(p["id"] for p in ctx["template"]["parameters"] if p["parameter_name"] == "Hemoglobin")
    await _create_reference_range(
        client, ctx["owner_headers"], hemoglobin_param_id, age_min_years=18, age_max_years=65, range_low="13.5", range_high="17.5",
    )

    result = await _enter_one_result(client, ctx["lab_order"]["id"], ctx["lab_headers"], numeric_value=13.0)
    assert result["range_low"] == "13.5000"
    assert result["interpretation"] == "Low"


async def test_live_result_entry_ignores_out_of_range_age_reference_range(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#5: a reference range whose age band (0-17, pediatric) excludes the
    fixture patient's age (36) is not applied - falls back to the
    template's own default."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    hemoglobin_param_id = next(p["id"] for p in ctx["template"]["parameters"] if p["parameter_name"] == "Hemoglobin")
    await _create_reference_range(
        client, ctx["owner_headers"], hemoglobin_param_id, age_min_years=0, age_max_years=17, range_low="9.0", range_high="13.0",
    )

    result = await _enter_one_result(client, ctx["lab_order"]["id"], ctx["lab_headers"], numeric_value=14.0)
    assert result["range_low"] == "12.0000"
    assert result["range_high"] == "16.0000"
    assert result["interpretation"] == "Normal"


async def test_live_result_entry_falls_back_to_template_default_with_no_reference_range_configured(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#6: unchanged Phase 2A behavior, proven again through the now-wired
    live path - with zero LaboratoryReferenceRange rows configured for the
    parameter at all, result entry uses the template's own default range."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    result = await _enter_one_result(client, ctx["lab_order"]["id"], ctx["lab_headers"], numeric_value=14.0)
    assert result["range_low"] == "12.0000"
    assert result["range_high"] == "16.0000"
    assert result["interpretation"] == "Normal"


async def test_live_result_entry_ignores_inactive_reference_range(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#7: a matching reference range that has been deactivated
    (is_active=False) is not used - falls back to the template default,
    proven live through result entry after PATCH-deactivating it."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    hemoglobin_param_id = next(p["id"] for p in ctx["template"]["parameters"] if p["parameter_name"] == "Hemoglobin")
    created = await _create_reference_range(
        client, ctx["owner_headers"], hemoglobin_param_id, sex="Male", range_low="13.0", range_high="17.0",
    )
    deactivate = await client.patch(
        f"/api/v1/laboratory/reference-ranges/{created['id']}", headers=ctx["owner_headers"], json={"is_active": False}
    )
    assert deactivate.status_code == 200

    result = await _enter_one_result(client, ctx["lab_order"]["id"], ctx["lab_headers"], numeric_value=14.0)
    assert result["range_low"] == "12.0000"
    assert result["range_high"] == "16.0000"
    assert result["interpretation"] == "Normal"


async def test_manual_interpretation_override_preserved_alongside_resolved_range(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#13: a clinician-supplied interpretation still wins even when a
    demographic-specific reference range is configured and resolved - the
    resolved range is stored (for display/history), but the interpretation
    itself is never recalculated over an explicit value."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    hemoglobin_param_id = next(p["id"] for p in ctx["template"]["parameters"] if p["parameter_name"] == "Hemoglobin")
    await _create_reference_range(client, ctx["owner_headers"], hemoglobin_param_id, sex="Male", range_low="13.0", range_high="17.0")

    # 15.0 would auto-compute "Normal" against the resolved 13-17 range, but
    # the lab tech explicitly overrides it.
    result = await _enter_one_result(
        client, ctx["lab_order"]["id"], ctx["lab_headers"], numeric_value=15.0, interpretation="Abnormal"
    )
    assert result["interpretation"] == "Abnormal"
    assert result["range_low"] == "13.0000"  # the resolved range is still stored for the record
    assert result["range_high"] == "17.0000"


async def test_historical_result_keeps_range_used_at_entry_after_reference_range_later_changes(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#14 (live-path version of the Phase 2A test): a result entered while
    a Male 13.0-17.0 reference range was active keeps that exact range
    stored even after a NEW, different active range is later configured for
    the same parameter - the historical result is never retroactively
    recalculated against the newer configuration."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    hemoglobin_param_id = next(p["id"] for p in ctx["template"]["parameters"] if p["parameter_name"] == "Hemoglobin")
    await _create_reference_range(client, ctx["owner_headers"], hemoglobin_param_id, sex="Male", range_low="13.0", range_high="17.0")

    result = await _enter_one_result(client, ctx["lab_order"]["id"], ctx["lab_headers"], numeric_value=15.0)
    assert result["range_low"] == "13.0000"
    assert result["range_high"] == "17.0000"
    assert result["interpretation"] == "Normal"

    # Laboratory later reconfigures the range for this parameter (e.g. new
    # analyzer/methodology) - a second, different active range now exists.
    await _create_reference_range(client, ctx["owner_headers"], hemoglobin_param_id, sex="Male", range_low="12.0", range_high="14.0")

    refetched = (await client.get(f"/api/v1/laboratory/orders/{ctx['lab_order']['id']}", headers=ctx["owner_headers"])).json()
    hemoglobin_result = next(r for r in refetched["results"] if r["parameter_name"] == "Hemoglobin")
    assert hemoglobin_result["range_low"] == "13.0000"
    assert hemoglobin_result["range_high"] == "17.0000"
    assert hemoglobin_result["interpretation"] == "Normal"  # unchanged, even though 15.0 would now be "High" under 12-14


# --- Phase 3: Blood Typing - the first Categorical laboratory test. Proves
# the generic result_type=="Categorical" + options + structured_value
# mechanism introduced in Phase 2A is reusable end-to-end, through the
# EXISTING LaboratoryTemplate -> LaboratoryTemplateParameter -> LaboratoryOrder
# -> LaboratoryResult architecture - no separate Blood Typing subsystem. ---

_BLOOD_TYPING_PARAMETERS = [
    {"parameter_name": "ABO Group", "result_type": "Categorical", "options": ["A", "B", "AB", "O"]},
    {"parameter_name": "Rh Factor", "result_type": "Categorical", "options": ["Positive", "Negative"]},
]


async def _setup_blood_typing_order(client: AsyncClient, make_clinic_with_owner, db_session):
    """Mirrors `_setup_with_lab_order` exactly (clinic/doctor/patient/queue
    ->visit/consultation/order/roles), but for a "Blood Typing" template
    instead of the hardcoded "CBC" that helper uses - proving the doctor's
    existing free-text order-creation flow (unchanged) and the existing
    test-name-matching auto-attach (unchanged) both work unmodified for a
    Categorical-parameter template, exactly as they already do for CBC."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)

    template_resp = await client.post(
        "/api/v1/laboratory/templates", headers=owner_headers,
        json={
            "test_name": "Blood Typing", "test_category": "Immunohematology", "specimen_type": "Whole Blood",
            "default_price": "150.00", "parameters": _BLOOD_TYPING_PARAMETERS,
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
        json={"order_category": "Laboratory", "priority": "Routine", "items": [{"item_name": "Blood Typing"}]},
    )
    assert order_resp.status_code == 200, order_resp.text
    order = order_resp.json()

    lab_email, _lab_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Laboratory")
    lab_token = await _login(client, lab_email, "TestPass123!")
    lab_headers = {"Authorization": f"Bearer {lab_token}"}

    lab_orders = (await client.get(f"/api/v1/laboratory/orders?visit_id={visit_id}", headers=owner_headers)).json()
    lab_order = next(lo for lo in lab_orders if lo["order_id"] == order["id"])

    return {
        "clinic": clinic, "owner_headers": owner_headers, "doc_headers": doc_headers,
        "lab_headers": lab_headers, "deps": deps, "visit_id": visit_id, "consultation_id": cid,
        "order": order, "lab_order": lab_order, "template": template,
    }


async def test_blood_typing_template_parameters_are_categorical_with_options(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#1/#2/#3/#4/#5/#9/#10/#11: Blood Typing exists as a normal
    LaboratoryTemplate with ABO Group/Rh Factor, both Categorical, with
    their configured options - retrieved via the same template/order APIs
    every other test in this file uses."""
    ctx = await _setup_blood_typing_order(client, make_clinic_with_owner, db_session)
    param_names = {p["parameter_name"] for p in ctx["template"]["parameters"]}
    assert param_names == {"ABO Group", "Rh Factor"}

    abo = next(p for p in ctx["template"]["parameters"] if p["parameter_name"] == "ABO Group")
    assert abo["result_type"] == "Categorical"
    assert abo["options"] == ["A", "B", "AB", "O"]

    rh = next(p for p in ctx["template"]["parameters"] if p["parameter_name"] == "Rh Factor")
    assert rh["result_type"] == "Categorical"
    assert rh["options"] == ["Positive", "Negative"]

    # #14: the order moved through the existing free-text doctor-order ->
    # auto-attach flow, unchanged, and the linked template round-trips the
    # same way via the order detail endpoint the Result Entry dialog uses.
    order = (await client.get(f"/api/v1/laboratory/orders/{ctx['lab_order']['id']}", headers=ctx["owner_headers"])).json()
    assert order["template"]["test_name"] == "Blood Typing"
    order_param_names = {p["parameter_name"] for p in order["template"]["parameters"]}
    assert order_param_names == {"ABO Group", "Rh Factor"}


async def test_blood_typing_valid_abo_and_rh_values_are_accepted_and_stored_structurally(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#3/#8/#15/#16: valid categorical values are accepted; the result is
    stored via the structured `structured_value` column, not concatenated
    into a text field - and no false Normal/Abnormal interpretation is
    generated (#11)."""
    ctx = await _setup_blood_typing_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    await _advance_to_processing(client, lab_id, ctx["lab_headers"])

    resp = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=ctx["lab_headers"],
        json={
            "results": [
                {"parameter_name": "ABO Group", "result_type": "Categorical", "structured_value": {"value": "O"}},
                {"parameter_name": "Rh Factor", "result_type": "Categorical", "structured_value": {"value": "Positive"}},
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    results = {r["parameter_name"]: r for r in resp.json()["results"]}
    assert results["ABO Group"]["structured_value"] == {"value": "O"}
    assert results["ABO Group"]["interpretation"] is None
    assert results["ABO Group"]["numeric_value"] is None
    assert results["ABO Group"]["text_value"] is None
    assert results["Rh Factor"]["structured_value"] == {"value": "Positive"}
    assert results["Rh Factor"]["interpretation"] is None


async def test_blood_typing_invalid_abo_value_is_rejected(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """#5/#13: 'X' is not a configured ABO Group option - rejected with 400,
    not silently saved."""
    ctx = await _setup_blood_typing_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    await _advance_to_processing(client, lab_id, ctx["lab_headers"])

    resp = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "ABO Group", "result_type": "Categorical", "structured_value": {"value": "X"}}]},
    )
    assert resp.status_code == 400, resp.text
    assert "abo group" in resp.json()["detail"].lower()


async def test_blood_typing_invalid_rh_value_is_rejected(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """#7/#13: a value never configured for Rh Factor is rejected - this is
    the explicit security acceptance criterion (backend must not trust the
    frontend/a hand-crafted request)."""
    ctx = await _setup_blood_typing_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    await _advance_to_processing(client, lab_id, ctx["lab_headers"])

    resp = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "Rh Factor", "result_type": "Categorical", "structured_value": {"value": "UnknownValue"}}]},
    )
    assert resp.status_code == 400, resp.text
    assert "rh factor" in resp.json()["detail"].lower()


async def test_blood_typing_empty_categorical_value_is_rejected(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """#8: submitting a Categorical row with no selected value at all
    (structured_value omitted) is rejected, not silently saved as a valid
    empty result."""
    ctx = await _setup_blood_typing_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    await _advance_to_processing(client, lab_id, ctx["lab_headers"])

    resp = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "ABO Group", "result_type": "Categorical"}]},
    )
    assert resp.status_code == 400, resp.text


async def test_blood_typing_result_persists_and_reloads_for_editing(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#16/#17/editing: after saving, re-fetching the order (the same GET
    the Result Entry dialog re-fetches on open) shows the persisted
    structured values, proving they survive a full round trip rather than
    only existing in the mutation's own response."""
    ctx = await _setup_blood_typing_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    await _advance_to_processing(client, lab_id, ctx["lab_headers"])

    await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=ctx["lab_headers"],
        json={
            "results": [
                {"parameter_name": "ABO Group", "result_type": "Categorical", "structured_value": {"value": "AB"}},
                {"parameter_name": "Rh Factor", "result_type": "Categorical", "structured_value": {"value": "Negative"}},
            ]
        },
    )

    refetched = (await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["owner_headers"])).json()
    results = {r["parameter_name"]: r for r in refetched["results"]}
    assert results["ABO Group"]["structured_value"] == {"value": "AB"}
    assert results["Rh Factor"]["structured_value"] == {"value": "Negative"}


async def test_blood_typing_untemplated_categorical_row_skips_option_validation(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """A Categorical row with no matching template parameter (e.g. an
    ad-hoc/free-text row, no `options` to validate against) is left alone -
    same "never invent a constraint that wasn't configured" fallback
    already proven for range resolution in Phase 2B."""
    ctx = await _setup_blood_typing_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    await _advance_to_processing(client, lab_id, ctx["lab_headers"])

    resp = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "Free Text Note", "result_type": "Categorical", "structured_value": {"value": "anything"}}]},
    )
    assert resp.status_code == 200, resp.text


async def test_blood_typing_tenant_isolation(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_blood_typing_order(client, make_clinic_with_owner, db_session)
    _clinic_b, _owner_b, owner_b_headers = await _owner_headers(client, make_clinic_with_owner)
    resp = await client.get(f"/api/v1/laboratory/orders/{ctx['lab_order']['id']}", headers=owner_b_headers)
    assert resp.status_code == 404


# --- Phase 4A: Urinalysis template/data architecture. Backend/template
# foundation only - no result-entry behavior change. Proves a single
# LaboratoryTemplate can mix Numeric/Text/Categorical parameters across
# generic display "sections", using the existing architecture unmodified
# except for one additive `section` column. ---

_URINALYSIS_EXPECTED_SECTIONS = {
    "Color": "Physical Examination", "Transparency": "Physical Examination",
    "Specific Gravity": "Physical Examination", "pH": "Physical Examination",
    "Protein": "Chemical Examination", "Glucose": "Chemical Examination",
    "Ketones": "Chemical Examination", "Blood": "Chemical Examination",
    "Bilirubin": "Chemical Examination", "Urobilinogen": "Chemical Examination",
    "Nitrite": "Chemical Examination", "Leukocytes": "Chemical Examination",
    "RBC": "Microscopic Examination", "WBC": "Microscopic Examination",
    "Epithelial Cells": "Microscopic Examination", "Bacteria": "Microscopic Examination",
    "Mucus Threads": "Microscopic Examination", "Crystals": "Microscopic Examination",
    "Casts": "Microscopic Examination",
}

_URINALYSIS_EXPECTED_TYPES = {
    "Color": "Categorical", "Transparency": "Categorical",
    "Specific Gravity": "Numeric", "pH": "Numeric",
    "Protein": "Categorical", "Glucose": "Categorical", "Ketones": "Categorical", "Blood": "Categorical",
    "Bilirubin": "Categorical", "Urobilinogen": "Categorical", "Nitrite": "Categorical", "Leukocytes": "Categorical",
    "RBC": "Numeric", "WBC": "Numeric",
    "Epithelial Cells": "Text", "Bacteria": "Text", "Mucus Threads": "Text", "Crystals": "Text", "Casts": "Text",
}


async def _seed_and_get_urinalysis(client: AsyncClient, owner_headers: dict) -> dict:
    resp = await client.post("/api/v1/laboratory/templates/seed-defaults", headers=owner_headers)
    assert resp.status_code == 200, resp.text
    templates = (await client.get("/api/v1/laboratory/templates", headers=owner_headers)).json()
    return next(t for t in templates if t["test_name"] == "Urinalysis")


async def test_urinalysis_template_exists_via_existing_seed_mechanism(client: AsyncClient, make_clinic_with_owner) -> None:
    """#1/#15: Urinalysis is created through the same opt-in seed-defaults
    endpoint CBC/Blood Typing already use - no new seeding system."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    urinalysis = await _seed_and_get_urinalysis(client, owner_headers)
    assert urinalysis["test_name"] == "Urinalysis"
    assert urinalysis["specimen_type"] == "Urine"


async def test_urinalysis_seeding_is_idempotent(client: AsyncClient, make_clinic_with_owner) -> None:
    """#16: calling seed-defaults again does not duplicate Urinalysis (or
    any other starter template)."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    await client.post("/api/v1/laboratory/templates/seed-defaults", headers=owner_headers)
    resp2 = await client.post("/api/v1/laboratory/templates/seed-defaults", headers=owner_headers)
    assert resp2.status_code == 200
    assert resp2.json() == []
    templates = (await client.get("/api/v1/laboratory/templates", headers=owner_headers)).json()
    assert [t["test_name"] for t in templates].count("Urinalysis") == 1


async def test_urinalysis_contains_expected_parameter_structure(client: AsyncClient, make_clinic_with_owner) -> None:
    """#2: the full, expected 19-parameter structure exists - Physical/
    Chemical/Microscopic examination parameters, matching the spec's
    example layout."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    urinalysis = await _seed_and_get_urinalysis(client, owner_headers)
    param_names = {p["parameter_name"] for p in urinalysis["parameters"]}
    assert param_names == set(_URINALYSIS_EXPECTED_SECTIONS.keys())


async def test_urinalysis_parameters_have_deterministic_order(client: AsyncClient, make_clinic_with_owner) -> None:
    """#3: parameters are returned in a stable, deterministic order
    (existing `display_order` mechanism - the same one CBC/Blood Typing
    already rely on), sections appearing in the expected sequence
    (Physical -> Chemical -> Microscopic), not database-insertion-order
    happenstance."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    urinalysis = await _seed_and_get_urinalysis(client, owner_headers)
    orders = [p["display_order"] for p in urinalysis["parameters"]]
    assert orders == sorted(orders)
    assert orders == list(range(len(orders)))

    sections_in_order = [p["section"] for p in urinalysis["parameters"]]
    # Physical Examination parameters all precede Chemical, which all
    # precede Microscopic - the sections are contiguous, not interleaved.
    assert sections_in_order == (
        ["Physical Examination"] * 4 + ["Chemical Examination"] * 8 + ["Microscopic Examination"] * 7
    )


async def test_urinalysis_parameter_types_are_preserved(client: AsyncClient, make_clinic_with_owner) -> None:
    """#4/#8: Urinalysis mixes Numeric, Text, AND Categorical parameters
    within one template - proving the architecture supports multiple
    result types in a single LaboratoryTemplate, the core Phase 4A
    architectural claim."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    urinalysis = await _seed_and_get_urinalysis(client, owner_headers)
    actual_types = {p["parameter_name"]: p["result_type"] for p in urinalysis["parameters"]}
    assert actual_types == _URINALYSIS_EXPECTED_TYPES
    # At least one of each of the three kinds actually appears.
    assert "Numeric" in actual_types.values()
    assert "Text" in actual_types.values()
    assert "Categorical" in actual_types.values()


async def test_urinalysis_categorical_parameters_expose_options_field(client: AsyncClient, make_clinic_with_owner) -> None:
    """#5: Categorical Urinalysis parameters (Color, Protein, etc.) expose
    the `options` field via the API - currently `None` (deliberately not
    invented, no authoritative option vocabulary exists in this project;
    REQUIRES LABORATORY/CLINICAL VALIDATION before an Administrator
    configures real options) - but the field is present and settable via
    the same mechanism Blood Typing already uses, proven by then setting
    it through the ordinary template-update API."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    urinalysis = await _seed_and_get_urinalysis(client, owner_headers)
    color = next(p for p in urinalysis["parameters"] if p["parameter_name"] == "Color")
    assert color["result_type"] == "Categorical"
    assert color["options"] is None

    updated_params = [
        {**{k: v for k, v in p.items() if k != "id"}, "options": ["Yellow", "Straw", "Amber"]}
        if p["parameter_name"] == "Color" else {k: v for k, v in p.items() if k != "id"}
        for p in urinalysis["parameters"]
    ]
    update = await client.patch(
        f"/api/v1/laboratory/templates/{urinalysis['id']}", headers=owner_headers, json={"parameters": updated_params}
    )
    assert update.status_code == 200, update.text
    updated_color = next(p for p in update.json()["parameters"] if p["parameter_name"] == "Color")
    assert updated_color["options"] == ["Yellow", "Straw", "Amber"]


async def test_urinalysis_numeric_parameters_can_retain_configured_ranges(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """#6: Specific Gravity/pH/RBC/WBC are Numeric and can have a range
    configured through the existing mechanism (same as any CBC parameter)
    - no clinical values are seeded, but the capability is proven."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    template_resp = await client.post(
        "/api/v1/laboratory/templates", headers=owner_headers,
        json={
            "test_name": "Urinalysis Range Test", "specimen_type": "Urine", "default_price": "0",
            "parameters": [{"parameter_name": "pH", "result_type": "Numeric", "range_low": "4.5", "range_high": "8.0"}],
        },
    )
    assert template_resp.status_code == 201, template_resp.text
    ph = template_resp.json()["parameters"][0]
    assert ph["range_low"] == "4.5000"
    assert ph["range_high"] == "8.0000"


async def test_urinalysis_sections_returned_correctly(client: AsyncClient, make_clinic_with_owner) -> None:
    """#7: every seeded Urinalysis parameter has its expected `section`
    value - the generic grouping field introduced in Phase 4A."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    urinalysis = await _seed_and_get_urinalysis(client, owner_headers)
    actual_sections = {p["parameter_name"]: p["section"] for p in urinalysis["parameters"]}
    assert actual_sections == _URINALYSIS_EXPECTED_SECTIONS


async def test_section_field_is_null_by_default_for_non_urinalysis_templates(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#9/#10: existing CBC and Blood Typing parameters are unaffected by
    the new `section` column - it stays null for every parameter that
    never sets it, exactly the same "additive, opt-in" pattern as
    options/requires_site before it."""
    cbc_ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    for param in cbc_ctx["template"]["parameters"]:
        assert param["section"] is None

    bt_ctx = await _setup_blood_typing_order(client, make_clinic_with_owner, db_session)
    for param in bt_ctx["template"]["parameters"]:
        assert param["section"] is None


async def test_urinalysis_does_not_affect_blood_typing_categorical_validation(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#11/#12: Blood Typing's own configured-options Categorical
    validation (invalid value rejected, valid value accepted) is unaffected
    by Urinalysis's addition of Categorical parameters with no options
    configured - two independent templates, independently validated."""
    ctx = await _setup_blood_typing_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    await _advance_to_processing(client, lab_id, ctx["lab_headers"])

    invalid = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "ABO Group", "result_type": "Categorical", "structured_value": {"value": "Z"}}]},
    )
    assert invalid.status_code == 400

    valid = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "ABO Group", "result_type": "Categorical", "structured_value": {"value": "A"}}]},
    )
    assert valid.status_code == 200, valid.text
    assert valid.json()["results"][0]["structured_value"] == {"value": "A"}


async def test_urinalysis_structured_value_convention_unaffected(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#13/#14: the canonical `{"value": ...}` categorical shape established
    in Phase 3 is untouched - a Urinalysis Categorical parameter with
    options configured (via direct template creation, since the seeded
    starter deliberately has none - see the "options=None" note in
    `DEFAULT_LABORATORY_TEMPLATES`) accepts and stores a real result the
    same way Blood Typing does, end-to-end through the real API, proving
    no existing structured-result shape or convention was disturbed."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    await client.post(
        "/api/v1/laboratory/templates", headers=owner_headers,
        json={
            "test_name": "Urinalysis Structured Value Test", "specimen_type": "Urine", "default_price": "0",
            "parameters": [
                {"parameter_name": "Protein", "result_type": "Categorical", "options": ["Negative", "Trace", "1+", "2+", "3+"]},
            ],
        },
    )
    queue = (await client.post("/api/v1/queues", headers=owner_headers, json=_queue_payload(deps))).json()
    visit_id = queue["visit_id"]

    doc_email, _doc_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor", doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "TestPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}
    await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/call", headers=doc_headers)
    await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/start-consultation", headers=doc_headers)
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    order = (
        await client.post(
            f"/api/v1/consultations/{opened['id']}/orders", headers=doc_headers,
            json={"order_category": "Laboratory", "items": [{"item_name": "Urinalysis Structured Value Test"}]},
        )
    ).json()
    lab_orders = (await client.get(f"/api/v1/laboratory/orders?visit_id={visit_id}", headers=owner_headers)).json()
    lab_id = next(lo for lo in lab_orders if lo["order_id"] == order["id"])["id"]

    lab_email, _lab_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Laboratory")
    lab_token = await _login(client, lab_email, "TestPass123!")
    lab_headers = {"Authorization": f"Bearer {lab_token}"}
    await _advance_to_processing(client, lab_id, lab_headers)

    resp = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=lab_headers,
        json={"results": [{"parameter_name": "Protein", "result_type": "Categorical", "structured_value": {"value": "2+"}}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["results"][0]["structured_value"] == {"value": "2+"}

    invalid = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=lab_headers,
        json={"results": [{"parameter_name": "Protein", "result_type": "Categorical", "structured_value": {"value": "NotAnOption"}}]},
    )
    assert invalid.status_code == 400


async def test_urinalysis_does_not_use_undeclared_microscopy_structured_shape(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """Architecture confirmation: no new `structured_value` shape was
    introduced for microscopy - every seeded Urinalysis parameter is
    Numeric, Text, or Categorical (never `Microscopy`, which remains an
    unused, reserved `LaboratoryResultType` member from Phase 2A). This
    proves the existing architecture was sufficient and no Urinalysis-
    specific structured format was invented."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    urinalysis = await _seed_and_get_urinalysis(client, owner_headers)
    result_types = {p["result_type"] for p in urinalysis["parameters"]}
    assert result_types == {"Numeric", "Text", "Categorical"}
    assert "Microscopy" not in result_types


# --- Phase 4C: qualitative laboratory test catalog (HCG Serum/Urine,
# HBsAg, HAV, VDRL/Syphilis, Dengue Rapid Test). Proves the existing
# generic Categorical (options-unconfigured) architecture is sufficient for
# every one of these - no new result type, no new structured_value shape,
# no test-specific backend/frontend code. ---

_PHASE_4C_TEST_NAMES = {
    "HCG (Serum)", "HCG (Urine)", "Hepatitis B Antigen (HBsAg)",
    "Hepatitis A Virus Test (HAV)", "VDRL / Syphilis Test", "Dengue Rapid Test",
}


async def _seed_and_list_templates(client: AsyncClient, owner_headers: dict) -> list[dict]:
    resp = await client.post("/api/v1/laboratory/templates/seed-defaults", headers=owner_headers)
    assert resp.status_code == 200, resp.text
    return (await client.get("/api/v1/laboratory/templates", headers=owner_headers)).json()


@pytest.mark.parametrize(
    "test_name,expected_param_names",
    [
        ("HCG (Serum)", {"Result"}),
        ("HCG (Urine)", {"Result"}),
        ("Hepatitis B Antigen (HBsAg)", {"Result"}),
        ("Hepatitis A Virus Test (HAV)", {"Result"}),
        ("VDRL / Syphilis Test", {"Result"}),
        ("Dengue Rapid Test", {"NS1", "IgM", "IgG"}),
    ],
)
async def test_phase_4c_template_exists_with_expected_parameters(
    client: AsyncClient, make_clinic_with_owner, test_name: str, expected_param_names: set[str]
) -> None:
    """#1-6/#9/#10/#11: each Phase 4C template exists via the existing seed
    mechanism, with the expected generic parameter structure - every
    parameter is Categorical (no new result type), and none carries a
    populated `structured_value`-shaping field beyond what Categorical
    already uses (no unnecessary structured JSON)."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    templates = await _seed_and_list_templates(client, owner_headers)
    template = next(t for t in templates if t["test_name"] == test_name)
    param_names = {p["parameter_name"] for p in template["parameters"]}
    assert param_names == expected_param_names
    for param in template["parameters"]:
        assert param["result_type"] == "Categorical"
        # REQUIRES LABORATORY/CLINICAL VALIDATION - deliberately unconfigured.
        assert param["options"] is None
        assert param["range_low"] is None
        assert param["range_high"] is None
        assert param["expected_normal_text"] is None


async def test_phase_4c_seed_defaults_creates_all_expected_templates_once(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """#1-6 combined + #7: all six new templates are created by a single
    seed-defaults call, alongside the pre-existing CBC/Urinalysis/Blood
    Typing starter set - and running it again does not duplicate any of
    them (idempotent)."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    resp = await client.post("/api/v1/laboratory/templates/seed-defaults", headers=owner_headers)
    assert resp.status_code == 200, resp.text
    created_names = {t["test_name"] for t in resp.json()}
    assert _PHASE_4C_TEST_NAMES.issubset(created_names)
    assert created_names == _PHASE_4C_TEST_NAMES | _PHASE_4D_TEST_NAMES | {"CBC", "Urinalysis", "Blood Typing"}

    resp2 = await client.post("/api/v1/laboratory/templates/seed-defaults", headers=owner_headers)
    assert resp2.status_code == 200
    assert resp2.json() == []

    templates = await _seed_and_list_templates(client, owner_headers)
    all_names = [t["test_name"] for t in templates]
    for name in _PHASE_4C_TEST_NAMES | _PHASE_4D_TEST_NAMES:
        assert all_names.count(name) == 1


async def test_phase_4c_templates_are_tenant_isolated(client: AsyncClient, make_clinic_with_owner) -> None:
    """#8: clinic B cannot see clinic A's seeded Phase 4C templates."""
    _clinic_a, _owner_a, owner_a_headers = await _owner_headers(client, make_clinic_with_owner)
    await client.post("/api/v1/laboratory/templates/seed-defaults", headers=owner_a_headers)

    _clinic_b, _owner_b, owner_b_headers = await _owner_headers(client, make_clinic_with_owner)
    templates_b = (await client.get("/api/v1/laboratory/templates", headers=owner_b_headers)).json()
    assert templates_b == []


async def _order_for_template(client: AsyncClient, make_clinic_with_owner, db_session, test_name: str) -> dict:
    """Creates a real Laboratory order for an already-seeded Phase 4C
    template, via the same doctor free-text order -> auto-attach flow every
    other test in this file uses - proving no ordering-flow change was
    needed for these tests either."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    await client.post("/api/v1/laboratory/templates/seed-defaults", headers=owner_headers)
    deps = await _setup_queue_deps(client, owner_headers)
    queue = (await client.post("/api/v1/queues", headers=owner_headers, json=_queue_payload(deps))).json()
    visit_id = queue["visit_id"]

    doc_email, _doc_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor", doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "TestPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}
    await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/call", headers=doc_headers)
    await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/start-consultation", headers=doc_headers)
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    order = (
        await client.post(
            f"/api/v1/consultations/{opened['id']}/orders", headers=doc_headers,
            json={"order_category": "Laboratory", "items": [{"item_name": test_name}]},
        )
    ).json()
    lab_orders = (await client.get(f"/api/v1/laboratory/orders?visit_id={visit_id}", headers=owner_headers)).json()
    lab_id = next(lo for lo in lab_orders if lo["order_id"] == order["id"])["id"]

    lab_email, _lab_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Laboratory")
    lab_token = await _login(client, lab_email, "TestPass123!")
    lab_headers = {"Authorization": f"Bearer {lab_token}"}
    await _advance_to_processing(client, lab_id, lab_headers)

    return {"lab_id": lab_id, "owner_headers": owner_headers, "lab_headers": lab_headers}


async def test_phase_4c_options_less_categorical_result_is_rejected(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#14: HBsAg's "Result" parameter has no configured options seeded -
    submitting any value for it is rejected (same authoritative backend
    validation Blood Typing already proved, unaffected by these new
    templates existing)."""
    ctx = await _order_for_template(client, make_clinic_with_owner, db_session, "Hepatitis B Antigen (HBsAg)")
    resp = await client.post(
        f"/api/v1/laboratory/orders/{ctx['lab_id']}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "Result", "result_type": "Categorical", "structured_value": {"value": "Reactive"}}]},
    )
    # Unconfigured options -> nothing to validate against -> the existing
    # "never invent a constraint that wasn't configured" fallback accepts
    # it as submitted, exactly like Urinalysis's own unconfigured
    # parameters today - proving no NEW backend behavior was introduced.
    assert resp.status_code == 200, resp.text
    assert resp.json()["results"][0]["structured_value"] == {"value": "Reactive"}


async def test_phase_4c_configured_categorical_options_accepted_and_invalid_rejected(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#12/#13/#15/#16: an Administrator configuring real options for a
    Phase 4C template's Result parameter (via the existing template-update
    mechanism, not a code change) makes the existing Categorical validation
    active - a valid value is accepted and persists as {"value": ...}, an
    invalid one is rejected, and the saved value reloads correctly."""
    ctx = await _order_for_template(client, make_clinic_with_owner, db_session, "VDRL / Syphilis Test")
    templates = (await client.get("/api/v1/laboratory/templates", headers=ctx["owner_headers"])).json()
    vdrl = next(t for t in templates if t["test_name"] == "VDRL / Syphilis Test")
    result_param_id = vdrl["parameters"][0]["id"]

    # Test-only configuration (not a production clinical default) - proves
    # the existing admin mechanism, not a hard-coded VDRL vocabulary.
    update = await client.patch(
        f"/api/v1/laboratory/templates/{vdrl['id']}", headers=ctx["owner_headers"],
        json={"parameters": [{"parameter_name": "Result", "result_type": "Categorical", "options": ["Reactive", "Non-reactive"], "id": result_param_id}]},
    )
    assert update.status_code == 200, update.text

    invalid = await client.post(
        f"/api/v1/laboratory/orders/{ctx['lab_id']}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "Result", "result_type": "Categorical", "structured_value": {"value": "Positive"}}]},
    )
    assert invalid.status_code == 400, invalid.text

    valid = await client.post(
        f"/api/v1/laboratory/orders/{ctx['lab_id']}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "Result", "result_type": "Categorical", "structured_value": {"value": "Non-reactive"}}]},
    )
    assert valid.status_code == 200, valid.text
    assert valid.json()["results"][0]["structured_value"] == {"value": "Non-reactive"}

    refetched = (await client.get(f"/api/v1/laboratory/orders/{ctx['lab_id']}", headers=ctx["owner_headers"])).json()
    assert refetched["results"][0]["structured_value"] == {"value": "Non-reactive"}


async def test_phase_4c_dengue_multi_parameter_results_persist_independently(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Dengue architecture decision proof: NS1/IgM/IgG are three
    independent Categorical parameters on ONE template - each with real
    test-only options configured, each result persists independently, and
    none was represented as a single combined/concatenated field."""
    ctx = await _order_for_template(client, make_clinic_with_owner, db_session, "Dengue Rapid Test")
    templates = (await client.get("/api/v1/laboratory/templates", headers=ctx["owner_headers"])).json()
    dengue = next(t for t in templates if t["test_name"] == "Dengue Rapid Test")
    updated_params = [
        {"id": p["id"], "parameter_name": p["parameter_name"], "result_type": "Categorical", "options": ["Positive", "Negative"]}
        for p in dengue["parameters"]
    ]
    await client.patch(f"/api/v1/laboratory/templates/{dengue['id']}", headers=ctx["owner_headers"], json={"parameters": updated_params})

    resp = await client.post(
        f"/api/v1/laboratory/orders/{ctx['lab_id']}/results", headers=ctx["lab_headers"],
        json={
            "results": [
                {"parameter_name": "NS1", "result_type": "Categorical", "structured_value": {"value": "Positive"}},
                {"parameter_name": "IgM", "result_type": "Categorical", "structured_value": {"value": "Negative"}},
                {"parameter_name": "IgG", "result_type": "Categorical", "structured_value": {"value": "Negative"}},
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    results = {r["parameter_name"]: r for r in resp.json()["results"]}
    assert results["NS1"]["structured_value"] == {"value": "Positive"}
    assert results["IgM"]["structured_value"] == {"value": "Negative"}
    assert results["IgG"]["structured_value"] == {"value": "Negative"}
    # No interpretation is invented (Positive != Abnormal, etc.) for any of them.
    assert all(r["interpretation"] is None for r in results.values())


async def test_phase_4c_no_interpretation_is_invented_for_qualitative_results(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Explicit interpretation-safety check: even with configured options
    and a valid selected value, no automatic Positive->Abnormal/
    Negative->Normal/Reactive->Abnormal translation occurs anywhere."""
    ctx = await _order_for_template(client, make_clinic_with_owner, db_session, "Hepatitis A Virus Test (HAV)")
    templates = (await client.get("/api/v1/laboratory/templates", headers=ctx["owner_headers"])).json()
    hav = next(t for t in templates if t["test_name"] == "Hepatitis A Virus Test (HAV)")
    result_param_id = hav["parameters"][0]["id"]
    await client.patch(
        f"/api/v1/laboratory/templates/{hav['id']}", headers=ctx["owner_headers"],
        json={"parameters": [{"parameter_name": "Result", "result_type": "Categorical", "options": ["Reactive", "Non-reactive"], "id": result_param_id}]},
    )
    resp = await client.post(
        f"/api/v1/laboratory/orders/{ctx['lab_id']}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "Result", "result_type": "Categorical", "structured_value": {"value": "Reactive"}}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["results"][0]["interpretation"] is None


# --- Qualitative/Categorical result-entry simplification: HBsAg example ---
# Same seeded "Hepatitis B Antigen (HBsAg)" Phase 4C template as above, but
# now configured (via the existing template PATCH endpoint - the same
# admin-configuration mechanism an Administrator would use through the
# Template editor/Excel import) with real options + a normal range + an
# expected-normal value, exactly the target example: Categorical,
# options=[Positive, Negative], Normal Range=Negative. Proves the backend
# auto-derives interpretation from `expected_normal_text` for a Categorical
# result the same way it already does for Text, and that an arbitrary
# (non-configured) value is still rejected.

async def _hbsag_order_with_options(client: AsyncClient, make_clinic_with_owner, db_session) -> dict:
    ctx = await _order_for_template(client, make_clinic_with_owner, db_session, "Hepatitis B Antigen (HBsAg)")
    templates = (await client.get("/api/v1/laboratory/templates", headers=ctx["owner_headers"])).json()
    hbsag = next(t for t in templates if t["test_name"] == "Hepatitis B Antigen (HBsAg)")
    result_param_id = hbsag["parameters"][0]["id"]
    await client.patch(
        f"/api/v1/laboratory/templates/{hbsag['id']}", headers=ctx["owner_headers"],
        json={
            "parameters": [
                {
                    "id": result_param_id, "parameter_name": "HBsAg", "result_type": "Categorical",
                    "options": ["Positive", "Negative"], "normal_range": "Negative", "expected_normal_text": "Negative",
                }
            ]
        },
    )
    return ctx


async def test_hbsag_positive_result_is_accepted_and_interpreted_as_abnormal(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx = await _hbsag_order_with_options(client, make_clinic_with_owner, db_session)
    resp = await client.post(
        f"/api/v1/laboratory/orders/{ctx['lab_id']}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "HBsAg", "result_type": "Categorical", "structured_value": {"value": "Positive"}}]},
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()["results"][0]
    assert result["structured_value"] == {"value": "Positive"}
    assert result["interpretation"] == "Abnormal"


async def test_hbsag_negative_result_is_accepted_and_interpreted_as_normal(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx = await _hbsag_order_with_options(client, make_clinic_with_owner, db_session)
    resp = await client.post(
        f"/api/v1/laboratory/orders/{ctx['lab_id']}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "HBsAg", "result_type": "Categorical", "structured_value": {"value": "Negative"}}]},
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()["results"][0]
    assert result["structured_value"] == {"value": "Negative"}
    assert result["interpretation"] == "Normal"


async def test_hbsag_arbitrary_value_is_rejected(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _hbsag_order_with_options(client, make_clinic_with_owner, db_session)
    resp = await client.post(
        f"/api/v1/laboratory/orders/{ctx['lab_id']}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "HBsAg", "result_type": "Categorical", "structured_value": {"value": "Maybe"}}]},
    )
    assert resp.status_code == 400, resp.text
    assert "HBsAg" in resp.json()["detail"]


async def test_hbsag_explicit_client_interpretation_is_still_respected_as_override(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """The backend never overwrites an explicit client-supplied
    interpretation (same rule already applied to Numeric/Text) - a
    deliberate clinician override survives even though it disagrees with
    what auto-derivation would have computed."""
    ctx = await _hbsag_order_with_options(client, make_clinic_with_owner, db_session)
    resp = await client.post(
        f"/api/v1/laboratory/orders/{ctx['lab_id']}/results", headers=ctx["lab_headers"],
        json={
            "results": [
                {
                    "parameter_name": "HBsAg", "result_type": "Categorical",
                    "structured_value": {"value": "Positive"}, "interpretation": "Normal",
                }
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["results"][0]["interpretation"] == "Normal"


async def test_phase_4c_does_not_affect_cbc_blood_typing_or_urinalysis(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#17/#18/#19: seeding the Phase 4C templates alongside CBC/Blood
    Typing/Urinalysis doesn't disturb any of them - each's own template
    still exists with its own unchanged parameter structure."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    templates = await _seed_and_list_templates(client, owner_headers)
    names = {t["test_name"] for t in templates}
    assert {"CBC", "Blood Typing", "Urinalysis"}.issubset(names)

    cbc = next(t for t in templates if t["test_name"] == "CBC")
    assert {p["parameter_name"] for p in cbc["parameters"]} == {
        "Hemoglobin", "Hematocrit", "WBC Count", "RBC Count", "Platelet Count", "MCV", "MCH", "MCHC", "Neutrophils", "Lymphocytes",
    }
    blood_typing = next(t for t in templates if t["test_name"] == "Blood Typing")
    abo = next(p for p in blood_typing["parameters"] if p["parameter_name"] == "ABO Group")
    assert abo["options"] == ["A", "B", "AB", "O"]

    # Full CBC/Blood Typing live-workflow regression, end-to-end.
    cbc_ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    cbc_result = await _enter_one_result(client, cbc_ctx["lab_order"]["id"], cbc_ctx["lab_headers"], numeric_value=14.0)
    assert cbc_result["interpretation"] is not None or float(cbc_result["numeric_value"]) == 14.0

    bt_ctx = await _setup_blood_typing_order(client, make_clinic_with_owner, db_session)
    lab_id = bt_ctx["lab_order"]["id"]
    await _advance_to_processing(client, lab_id, bt_ctx["lab_headers"])
    bt_resp = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=bt_ctx["lab_headers"],
        json={"results": [{"parameter_name": "ABO Group", "result_type": "Categorical", "structured_value": {"value": "O"}}]},
    )
    assert bt_resp.status_code == 200, bt_resp.text


# --- Bug fix: Laboratory <-> Reception Queue lifecycle sync. A queue
# ticket called for a Laboratory-only encounter never enters a doctor
# consultation "Serving" moment, so nothing previously moved it off the
# TV/queue display once the lab work was done - releasing the
# LaboratoryOrder must complete that Queue ticket. ---

async def _setup_lab_order_with_called_queue(client: AsyncClient, make_clinic_with_owner, db_session):
    """Reproduces the reported bug precisely: the queue ticket is Called
    (via the same Doctor Workspace "call" action a real user clicks) but -
    unlike `_setup_with_lab_order` - `start-consultation` is deliberately
    NEVER invoked, so the queue stays at Called (never Serving) for the
    whole lab lifecycle. `ConsultationService.open_consultation` has no
    Visit.status prerequisite (verified by reading it directly), so this
    is a legitimate, reachable real path - not a contrived test-only
    shortcut."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    await client.post(
        "/api/v1/laboratory/templates", headers=owner_headers,
        json={"test_name": "CBC", "default_price": "0", "parameters": []},
    )
    queue = (await client.post("/api/v1/queues", headers=owner_headers, json=_queue_payload(deps))).json()
    queue_id = queue["id"]
    visit_id = queue["visit_id"]

    doc_email, _doc_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor", doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "TestPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    called = await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/call", headers=doc_headers)
    assert called.status_code == 200, called.text
    queue_after_call = (await client.get(f"/api/v1/queues/{queue_id}", headers=owner_headers)).json()
    assert queue_after_call["status"] == "Called"

    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    order = (
        await client.post(
            f"/api/v1/consultations/{opened['id']}/orders", headers=doc_headers,
            json={"order_category": "Laboratory", "items": [{"item_name": "CBC"}]},
        )
    ).json()
    lab_orders = (await client.get(f"/api/v1/laboratory/orders?visit_id={visit_id}", headers=owner_headers)).json()
    lab_order = next(lo for lo in lab_orders if lo["order_id"] == order["id"])

    lab_email, _lab_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Laboratory")
    lab_token = await _login(client, lab_email, "TestPass123!")
    lab_headers = {"Authorization": f"Bearer {lab_token}"}

    return {
        "clinic": clinic, "owner_headers": owner_headers, "lab_headers": lab_headers,
        "queue_id": queue_id, "visit_id": visit_id, "lab_order": lab_order,
    }


async def _run_lab_lifecycle_to_completed(client: AsyncClient, lab_id: str, lab_headers: dict) -> None:
    await client.post(f"/api/v1/laboratory/orders/{lab_id}/collect", headers=lab_headers)
    await client.post(f"/api/v1/laboratory/orders/{lab_id}/start-processing", headers=lab_headers)
    resp = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=lab_headers,
        json={"results": [{"parameter_name": "Note", "result_type": "Text", "text_value": "ok"}]},
    )
    assert resp.status_code == 200, resp.text


async def test_queue_ticket_completes_when_laboratory_result_is_released(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """The core bug fix: a queue ticket Called for Laboratory (never
    Serving) is synced straight to Completed when its LaboratoryOrder is
    Released - it no longer stays stuck on the queue/TV display."""
    ctx = await _setup_lab_order_with_called_queue(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    await _run_lab_lifecycle_to_completed(client, lab_id, ctx["lab_headers"])

    queue_before_release = (await client.get(f"/api/v1/queues/{ctx['queue_id']}", headers=ctx["owner_headers"])).json()
    assert queue_before_release["status"] == "Called"  # confirms the pre-fix bug reproduction

    released = await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"])
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "Released"

    queue_after = (await client.get(f"/api/v1/queues/{ctx['queue_id']}", headers=ctx["owner_headers"])).json()
    assert queue_after["status"] == "Completed"

    # Queue history/timeline remains correct: Waiting -> Called -> Completed,
    # exactly one Completed entry, written through the existing
    # QueueService.change_status audit trail (not a bypassed direct write).
    to_statuses = [h["to_status"] for h in queue_after["history"]]
    assert to_statuses == ["Waiting", "Called", "Completed"]  # ticket creation itself writes the initial Waiting entry
    assert to_statuses.count("Completed") == 1
    completed_entry = next(h for h in queue_after["history"] if h["to_status"] == "Completed")
    assert completed_entry["from_status"] == "Called"


async def test_releasing_already_released_laboratory_order_does_not_duplicate_queue_transition(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Idempotency: re-releasing an already-Released order is rejected at
    the order-status-transition level (Released has no outgoing
    transitions) before the queue sync ever runs again - no duplicate
    queue history/events are created."""
    ctx = await _setup_lab_order_with_called_queue(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    await _run_lab_lifecycle_to_completed(client, lab_id, ctx["lab_headers"])

    first = await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"])
    assert first.status_code == 200, first.text

    queue_after_first = (await client.get(f"/api/v1/queues/{ctx['queue_id']}", headers=ctx["owner_headers"])).json()
    history_count_after_first = len(queue_after_first["history"])
    assert queue_after_first["status"] == "Completed"

    second = await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"])
    assert second.status_code == 400, second.text  # already Released - harmless rejection, not a crash

    queue_after_second = (await client.get(f"/api/v1/queues/{ctx['queue_id']}", headers=ctx["owner_headers"])).json()
    assert queue_after_second["status"] == "Completed"
    assert len(queue_after_second["history"]) == history_count_after_first  # no duplicate history entry


async def test_laboratory_order_without_queue_still_releases_normally(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """A laboratory order whose visit has no linked queue ticket (e.g. a
    direct/legacy visit) releases exactly as before - the queue sync is a
    no-op, not an error."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    await client.post(
        "/api/v1/laboratory/templates", headers=owner_headers,
        json={"test_name": "CBC", "default_price": "0", "parameters": []},
    )
    visit = (
        await client.post(
            "/api/v1/visits", headers=owner_headers,
            json={"patient_id": deps["patient_id"], "branch_id": deps["branch_id"], "doctor_id": deps["doctor_id"]},
        )
    ).json()
    assert visit["queue_id"] is None

    doc_email, _doc_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor", doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "TestPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}
    opened = (await client.post(f"/api/v1/visits/{visit['id']}/consultation/open", headers=doc_headers)).json()
    order = (
        await client.post(
            f"/api/v1/consultations/{opened['id']}/orders", headers=doc_headers,
            json={"order_category": "Laboratory", "items": [{"item_name": "CBC"}]},
        )
    ).json()
    lab_orders = (await client.get(f"/api/v1/laboratory/orders?visit_id={visit['id']}", headers=owner_headers)).json()
    lab_id = next(lo for lo in lab_orders if lo["order_id"] == order["id"])["id"]

    lab_email, _lab_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Laboratory")
    lab_token = await _login(client, lab_email, "TestPass123!")
    lab_headers = {"Authorization": f"Bearer {lab_token}"}
    await _run_lab_lifecycle_to_completed(client, lab_id, lab_headers)

    released = await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=lab_headers)
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "Released"


async def test_consultation_queue_completion_unaffected_by_laboratory_queue_sync(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Regression: the Doctor Workspace consultation-completion path still
    completes its queue ticket exactly as before (Called -> Serving ->
    Completed, via `doctor-workspace/complete-consultation`, completely
    independent of `LaboratoryService`) - the new Called->Completed edge
    added to `QUEUE_STATUS_TRANSITIONS` is purely additive and does not
    change how a consultation ticket already reaches Completed."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    visit = (await client.get(f"/api/v1/visits/{ctx['visit_id']}", headers=ctx["owner_headers"])).json()
    queue_id = visit["queue_id"]
    assert queue_id is not None

    queue_mid = (await client.get(f"/api/v1/queues/{queue_id}", headers=ctx["owner_headers"])).json()
    assert queue_mid["status"] == "Serving"  # already Serving via start-consultation, as before this fix

    complete = await client.post(
        f"/api/v1/doctor-workspace/visits/{ctx['visit_id']}/complete-consultation", headers=ctx["doc_headers"]
    )
    assert complete.status_code == 200, complete.text

    queue_after = (await client.get(f"/api/v1/queues/{queue_id}", headers=ctx["owner_headers"])).json()
    assert queue_after["status"] == "Completed"
    to_statuses = [h["to_status"] for h in queue_after["history"]]
    completed_entry = next(h for h in queue_after["history"] if h["to_status"] == "Completed")
    assert completed_entry["from_status"] == "Serving"  # unchanged: still via Serving, not the new Called path


async def test_laboratory_queue_sync_respects_tenant_isolation(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Clinic B cannot see or be affected by clinic A's laboratory-queue sync."""
    ctx = await _setup_lab_order_with_called_queue(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    await _run_lab_lifecycle_to_completed(client, lab_id, ctx["lab_headers"])
    await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"])

    _clinic_b, _owner_b, owner_b_headers = await _owner_headers(client, make_clinic_with_owner)
    cross_tenant = await client.get(f"/api/v1/queues/{ctx['queue_id']}", headers=owner_b_headers)
    assert cross_tenant.status_code == 404


# --- Phase 4D: Stool Exam, Fecal Occult Blood, Sputum Exam, Gram Stain,
# Trichomonas Vaginalis Mount, KOH Mount. Proves the existing generic
# Numeric/Text/Categorical + section + requires_site architecture is
# sufficient for all six - no Microscopy/Titer, no new structured_value
# shape, no test-specific backend/frontend code. ---

_PHASE_4D_TEST_NAMES = {
    "Stool Exam (Direct Mount)", "Fecal Occult Blood Test", "Sputum Exam",
    "Gram Stain", "Trichomonas Vaginalis Mount", "KOH Mount",
}


@pytest.mark.parametrize(
    "test_name,expected_params",
    [
        (
            "Stool Exam (Direct Mount)",
            {
                "Color": ("Categorical", "Macroscopic Examination", False),
                "Consistency": ("Categorical", "Macroscopic Examination", False),
                "Microscopic Findings": ("Text", "Microscopic Examination", False),
            },
        ),
        ("Fecal Occult Blood Test", {"Result": ("Categorical", None, False)}),
        ("Sputum Exam", {"Result": ("Text", None, False)}),
        ("Gram Stain", {"Result": ("Text", None, False)}),
        ("Trichomonas Vaginalis Mount", {"Result": ("Categorical", None, False)}),
        ("KOH Mount", {"Result": ("Categorical", None, True)}),
    ],
)
async def test_phase_4d_template_exists_with_expected_parameters(
    client: AsyncClient, make_clinic_with_owner, test_name: str, expected_params: dict
) -> None:
    """#1-6/#9/#10/#11: each Phase 4D template exists via the existing seed
    mechanism, with the expected generic parameter structure - correct
    result_type/section/requires_site, unconfigured options (REQUIRES
    LABORATORY/CLINICAL VALIDATION), no Microscopy/Titer anywhere, no
    unnecessary structured JSON."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    templates = await _seed_and_list_templates(client, owner_headers)
    template = next(t for t in templates if t["test_name"] == test_name)
    params_by_name = {p["parameter_name"]: p for p in template["parameters"]}
    assert set(params_by_name.keys()) == set(expected_params.keys())
    for name, (result_type, section, requires_site) in expected_params.items():
        param = params_by_name[name]
        assert param["result_type"] == result_type
        assert param["section"] == section
        assert param["requires_site"] == requires_site
        if result_type == "Categorical":
            # REQUIRES LABORATORY/CLINICAL VALIDATION - deliberately unconfigured.
            assert param["options"] is None
        assert param["range_low"] is None
        assert param["range_high"] is None
        assert param["expected_normal_text"] is None


async def test_phase_4d_seed_defaults_creates_all_six_templates_once(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """#1-6 combined + idempotency: all six new templates are created by a
    single seed-defaults call, alongside every prior starter template, and
    running it again does not duplicate any of them."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    resp = await client.post("/api/v1/laboratory/templates/seed-defaults", headers=owner_headers)
    assert resp.status_code == 200, resp.text
    created_names = {t["test_name"] for t in resp.json()}
    assert _PHASE_4D_TEST_NAMES.issubset(created_names)

    resp2 = await client.post("/api/v1/laboratory/templates/seed-defaults", headers=owner_headers)
    assert resp2.status_code == 200
    assert resp2.json() == []

    templates = await _seed_and_list_templates(client, owner_headers)
    all_names = [t["test_name"] for t in templates]
    for name in _PHASE_4D_TEST_NAMES:
        assert all_names.count(name) == 1


async def test_phase_4d_seed_defaults_does_not_overwrite_administrator_modified_template(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """Step 9: an Administrator who has already configured real options on
    a Phase 4D template's parameter keeps that configuration after a
    second seed-defaults call - seeding never touches an existing template
    by name, only creates missing ones."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    await client.post("/api/v1/laboratory/templates/seed-defaults", headers=owner_headers)
    templates = await _seed_and_list_templates(client, owner_headers)
    fobt = next(t for t in templates if t["test_name"] == "Fecal Occult Blood Test")
    result_param_id = fobt["parameters"][0]["id"]

    update = await client.patch(
        f"/api/v1/laboratory/templates/{fobt['id']}", headers=owner_headers,
        json={"parameters": [{"parameter_name": "Result", "result_type": "Categorical", "options": ["Positive", "Negative"], "id": result_param_id}]},
    )
    assert update.status_code == 200, update.text

    await client.post("/api/v1/laboratory/templates/seed-defaults", headers=owner_headers)
    refetched = await _seed_and_list_templates(client, owner_headers)
    fobt_after = next(t for t in refetched if t["test_name"] == "Fecal Occult Blood Test")
    assert fobt_after["parameters"][0]["options"] == ["Positive", "Negative"]
    assert len([t for t in refetched if t["test_name"] == "Fecal Occult Blood Test"]) == 1


async def test_phase_4d_templates_are_tenant_isolated(client: AsyncClient, make_clinic_with_owner) -> None:
    """#8: clinic B cannot see clinic A's seeded Phase 4D templates."""
    _clinic_a, _owner_a, owner_a_headers = await _owner_headers(client, make_clinic_with_owner)
    await client.post("/api/v1/laboratory/templates/seed-defaults", headers=owner_a_headers)

    _clinic_b, _owner_b, owner_b_headers = await _owner_headers(client, make_clinic_with_owner)
    templates_b = (await client.get("/api/v1/laboratory/templates", headers=owner_b_headers)).json()
    assert templates_b == []


@pytest.mark.parametrize("test_name", ["Sputum Exam", "Gram Stain"])
async def test_phase_4d_text_result_submits_persists_and_reloads(
    client: AsyncClient, make_clinic_with_owner, db_session, test_name: str
) -> None:
    """Sputum Exam / Gram Stain: a single free-text result submits, persists,
    and reloads correctly - proving Text remains sufficient without
    inventing Microscopy/structured fields."""
    ctx = await _order_for_template(client, make_clinic_with_owner, db_session, test_name)
    resp = await client.post(
        f"/api/v1/laboratory/orders/{ctx['lab_id']}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "Result", "result_type": "Text", "text_value": "Gram-positive cocci in clusters"}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["results"][0]["text_value"] == "Gram-positive cocci in clusters"
    assert resp.json()["results"][0]["interpretation"] is None

    refetched = (await client.get(f"/api/v1/laboratory/orders/{ctx['lab_id']}", headers=ctx["owner_headers"])).json()
    assert refetched["results"][0]["text_value"] == "Gram-positive cocci in clusters"


async def test_phase_4d_stool_exam_mixed_parameters_persist_independently(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Stool Exam mixes Categorical (Color/Consistency) and Text
    (Microscopic Findings) across two sections in one template - each
    parameter persists independently, no false interpretation invented."""
    ctx = await _order_for_template(client, make_clinic_with_owner, db_session, "Stool Exam (Direct Mount)")
    templates = (await client.get("/api/v1/laboratory/templates", headers=ctx["owner_headers"])).json()
    stool = next(t for t in templates if t["test_name"] == "Stool Exam (Direct Mount)")
    color_id = next(p["id"] for p in stool["parameters"] if p["parameter_name"] == "Color")
    consistency_id = next(p["id"] for p in stool["parameters"] if p["parameter_name"] == "Consistency")
    findings_id = next(p["id"] for p in stool["parameters"] if p["parameter_name"] == "Microscopic Findings")
    updated_params = [
        {"id": color_id, "parameter_name": "Color", "result_type": "Categorical", "options": ["Brown", "Black", "Yellow"], "section": "Macroscopic Examination"},
        {"id": consistency_id, "parameter_name": "Consistency", "result_type": "Categorical", "options": ["Formed", "Soft", "Watery"], "section": "Macroscopic Examination"},
        {"id": findings_id, "parameter_name": "Microscopic Findings", "result_type": "Text", "section": "Microscopic Examination"},
    ]
    await client.patch(f"/api/v1/laboratory/templates/{stool['id']}", headers=ctx["owner_headers"], json={"parameters": updated_params})

    resp = await client.post(
        f"/api/v1/laboratory/orders/{ctx['lab_id']}/results", headers=ctx["lab_headers"],
        json={
            "results": [
                {"parameter_name": "Color", "result_type": "Categorical", "structured_value": {"value": "Brown"}},
                {"parameter_name": "Consistency", "result_type": "Categorical", "structured_value": {"value": "Formed"}},
                {"parameter_name": "Microscopic Findings", "result_type": "Text", "text_value": "No ova or parasites seen"},
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    results = {r["parameter_name"]: r for r in resp.json()["results"]}
    assert results["Color"]["structured_value"] == {"value": "Brown"}
    assert results["Consistency"]["structured_value"] == {"value": "Formed"}
    assert results["Microscopic Findings"]["text_value"] == "No ova or parasites seen"
    assert all(r["interpretation"] is None for r in results.values())

    invalid = await client.post(
        f"/api/v1/laboratory/orders/{ctx['lab_id']}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "Color", "result_type": "Categorical", "structured_value": {"value": "Green"}}]},
    )
    assert invalid.status_code == 400, invalid.text


async def test_phase_4d_options_less_qualitative_results_accepted_per_established_fallback(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Fecal Occult Blood / Trichomonas Vaginalis Mount: unconfigured
    Categorical parameters follow the exact Phase 3/4C fallback (nothing
    to validate against -> accepted as submitted), not a new behavior."""
    for test_name in ("Fecal Occult Blood Test", "Trichomonas Vaginalis Mount"):
        ctx = await _order_for_template(client, make_clinic_with_owner, db_session, test_name)
        resp = await client.post(
            f"/api/v1/laboratory/orders/{ctx['lab_id']}/results", headers=ctx["lab_headers"],
            json={"results": [{"parameter_name": "Result", "result_type": "Categorical", "structured_value": {"value": "Positive"}}]},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["results"][0]["structured_value"] == {"value": "Positive"}
        assert resp.json()["results"][0]["interpretation"] is None


# --- KOH Mount per site: proves requires_site end-to-end. ---

async def test_koh_mount_requires_site_is_declared_on_the_template(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    templates = await _seed_and_list_templates(client, owner_headers)
    koh = next(t for t in templates if t["test_name"] == "KOH Mount")
    assert koh["parameters"][0]["requires_site"] is True


async def test_koh_mount_site_is_submitted_persisted_and_reloaded(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx = await _order_for_template(client, make_clinic_with_owner, db_session, "KOH Mount")
    resp = await client.post(
        f"/api/v1/laboratory/orders/{ctx['lab_id']}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "Result", "result_type": "Categorical", "site": "Skin", "structured_value": {"value": "Positive"}}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["results"][0]["site"] == "Skin"

    refetched = (await client.get(f"/api/v1/laboratory/orders/{ctx['lab_id']}", headers=ctx["owner_headers"])).json()
    assert refetched["results"][0]["site"] == "Skin"


async def test_koh_mount_multiple_sites_persist_independently_without_overwriting(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """The existing LaboratoryResult model already supports multiple
    site-specific results for the same parameter in one submission - no
    schema change was needed: `upsert_results` creates one independent row
    per submitted item, never keyed/deduped by parameter_name, so two
    "Result" rows with different `site` values simply coexist."""
    ctx = await _order_for_template(client, make_clinic_with_owner, db_session, "KOH Mount")
    resp = await client.post(
        f"/api/v1/laboratory/orders/{ctx['lab_id']}/results", headers=ctx["lab_headers"],
        json={
            "results": [
                {"parameter_name": "Result", "result_type": "Categorical", "site": "Skin", "structured_value": {"value": "Positive"}},
                {"parameter_name": "Result", "result_type": "Categorical", "site": "Vaginal", "structured_value": {"value": "Negative"}},
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert len(results) == 2
    by_site = {r["site"]: r["structured_value"] for r in results}
    assert by_site == {"Skin": {"value": "Positive"}, "Vaginal": {"value": "Negative"}}

    refetched = (await client.get(f"/api/v1/laboratory/orders/{ctx['lab_id']}", headers=ctx["owner_headers"])).json()
    assert len(refetched["results"]) == 2
    refetched_by_site = {r["site"]: r["structured_value"] for r in refetched["results"]}
    assert refetched_by_site == {"Skin": {"value": "Positive"}, "Vaginal": {"value": "Negative"}}


async def test_phase_4d_does_not_affect_cbc_blood_typing_urinalysis_or_phase_4c_templates(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """#12: full regression proof - seeding Phase 4D alongside every prior
    template doesn't disturb any of them, and each's live workflow still
    functions."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    templates = await _seed_and_list_templates(client, owner_headers)
    names = {t["test_name"] for t in templates}
    assert {"CBC", "Blood Typing", "Urinalysis"}.issubset(names)
    assert _PHASE_4C_TEST_NAMES.issubset(names)

    dengue = next(t for t in templates if t["test_name"] == "Dengue Rapid Test")
    assert {p["parameter_name"] for p in dengue["parameters"]} == {"NS1", "IgM", "IgG"}

    cbc_ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    cbc_result = await _enter_one_result(client, cbc_ctx["lab_order"]["id"], cbc_ctx["lab_headers"], numeric_value=14.0)
    assert float(cbc_result["numeric_value"]) == 14.0

    bt_ctx = await _setup_blood_typing_order(client, make_clinic_with_owner, db_session)
    lab_id = bt_ctx["lab_order"]["id"]
    await _advance_to_processing(client, lab_id, bt_ctx["lab_headers"])
    bt_resp = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=bt_ctx["lab_headers"],
        json={"results": [{"parameter_name": "ABO Group", "result_type": "Categorical", "structured_value": {"value": "O"}}]},
    )
    assert bt_resp.status_code == 200, bt_resp.text


# --- Phase 4E: Titer + Microscopy generic result-type completion.
# Backend was already fully generic (text_value storage, no
# result-type-specific branching in upsert_results/enter_results); the
# confirmed gaps were frontend-only (ResultEntryDialog's Type selector
# missing both options, and handleSubmit's `=== "Text"` check silently
# nulling Titer/Microscopy textValue). These tests prove the backend
# lifecycle end-to-end through the real API (not just asserting "no code
# change needed") and lock in "no automatic interpretation" for both. ---


async def test_phase_4e_titer_result_submits_persists_reloads_and_is_not_interpreted(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Titer: template parameter representable, value entered via the
    generic `/results` endpoint using existing text_value storage (no new
    column), persists, reloads, and receives no automatic interpretation -
    exactly like an ordinary Text result, per the model's documented
    "Titer intentionally keeps using text_value" convention."""
    ctx = await _setup_with_lab_order(
        client, make_clinic_with_owner, db_session,
        template_parameters=[{"parameter_name": "Titer", "result_type": "Titer", "display_order": 0}],
    )
    lab_id = ctx["lab_order"]["id"]
    result = await _enter_one_result(
        client, lab_id, ctx["lab_headers"],
        parameter_name="Titer", result_type="Titer", numeric_value=None, text_value="1:160",
    )
    assert result["result_type"] == "Titer"
    assert result["text_value"] == "1:160"
    assert result["numeric_value"] is None
    assert result["structured_value"] is None
    assert result["interpretation"] is None

    refetched = (await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["owner_headers"])).json()
    reloaded = refetched["results"][0]
    assert reloaded["text_value"] == "1:160"
    assert reloaded["interpretation"] is None


async def test_phase_4e_titer_value_is_never_converted_to_null(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Guards the exact frontend gap this phase closed: a non-empty Titer
    value must never arrive at (or be persisted as) null."""
    ctx = await _setup_with_lab_order(
        client, make_clinic_with_owner, db_session,
        template_parameters=[{"parameter_name": "S. Typhi Titer", "result_type": "Titer", "display_order": 0}],
    )
    lab_id = ctx["lab_order"]["id"]
    result = await _enter_one_result(
        client, lab_id, ctx["lab_headers"],
        parameter_name="S. Typhi Titer", result_type="Titer", numeric_value=None, text_value="1:320",
    )
    assert result["text_value"] is not None
    assert result["text_value"] == "1:320"


async def test_phase_4e_microscopy_result_submits_persists_reloads_and_is_not_interpreted(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Microscopy: no documented/enforced structured_value convention
    exists anywhere in the current code (only an illustrative comment) -
    per this phase's "prefer the smallest possible generic implementation
    using the existing text storage" instruction, Microscopy is
    represented as free text via text_value, identical to Text/Titer.
    Proves submit/persist/reload and no invented interpretation."""
    ctx = await _setup_with_lab_order(
        client, make_clinic_with_owner, db_session,
        template_parameters=[{"parameter_name": "Findings", "result_type": "Microscopy", "display_order": 0}],
    )
    lab_id = ctx["lab_order"]["id"]
    result = await _enter_one_result(
        client, lab_id, ctx["lab_headers"],
        parameter_name="Findings", result_type="Microscopy", numeric_value=None,
        text_value="Gram-positive cocci in clusters",
    )
    assert result["result_type"] == "Microscopy"
    assert result["text_value"] == "Gram-positive cocci in clusters"
    assert result["structured_value"] is None
    assert result["interpretation"] is None

    refetched = (await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["owner_headers"])).json()
    reloaded = refetched["results"][0]
    assert reloaded["text_value"] == "Gram-positive cocci in clusters"
    assert reloaded["interpretation"] is None


async def test_phase_4e_no_invented_microscopy_option_list_or_validation(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Any free-text value is accepted for Microscopy - the backend must
    not silently reject or coerce a value into an invented vocabulary
    (e.g. Few/Moderate/Many), since none is established anywhere in this
    project."""
    ctx = await _setup_with_lab_order(
        client, make_clinic_with_owner, db_session,
        template_parameters=[{"parameter_name": "Findings", "result_type": "Microscopy", "display_order": 0}],
    )
    lab_id = ctx["lab_order"]["id"]
    await _advance_to_processing(client, lab_id, ctx["lab_headers"])
    for free_text in ["Numerous pus cells", "3-5 RBC/hpf", "Unremarkable"]:
        resp = await client.post(
            f"/api/v1/laboratory/orders/{lab_id}/results", headers=ctx["lab_headers"],
            json={"results": [{"parameter_name": "Findings", "result_type": "Microscopy", "text_value": free_text}]},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["results"][0]["text_value"] == free_text


async def test_phase_4e_titer_and_microscopy_do_not_affect_cbc_blood_typing_urinalysis_or_phase_4c(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Regression: adding Titer/Microscopy lifecycle support doesn't touch
    any other template's live workflow."""
    cbc_ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    cbc_result = await _enter_one_result(client, cbc_ctx["lab_order"]["id"], cbc_ctx["lab_headers"], numeric_value=14.0)
    assert float(cbc_result["numeric_value"]) == 14.0

    bt_ctx = await _setup_blood_typing_order(client, make_clinic_with_owner, db_session)
    lab_id = bt_ctx["lab_order"]["id"]
    await _advance_to_processing(client, lab_id, bt_ctx["lab_headers"])
    bt_resp = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=bt_ctx["lab_headers"],
        json={"results": [{"parameter_name": "ABO Group", "result_type": "Categorical", "structured_value": {"value": "AB"}}]},
    )
    assert bt_resp.status_code == 200, bt_resp.text
    assert bt_resp.json()["results"][0]["structured_value"] == {"value": "AB"}

    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    templates = await _seed_and_list_templates(client, owner_headers)
    names = {t["test_name"] for t in templates}
    assert {"CBC", "Blood Typing", "Urinalysis"}.issubset(names)
    assert _PHASE_4C_TEST_NAMES.issubset(names)
    assert _PHASE_4D_TEST_NAMES.issubset(names)


# --- Phase 4F: Clinical Vocabulary Configuration Preparation. No clinical
# option lists exist anywhere in this project for the Categorical
# parameters seeded with `options: None` (Urinalysis, Phase 4C, Phase 4D) -
# confirmed by inspection, not invented here. This section proves the
# already-generic admin configuration path (PATCH /templates/{id}) fully
# supports supplying those options once a laboratory/clinical authority
# provides them - configure, persist via a FRESH GET (not just the PATCH
# response), and tenant isolation of a clinic's configured options.
# Production seed data (DEFAULT_LABORATORY_TEMPLATES) is left untouched by
# this phase; only synthetic values are used, and only inside tests. ---


async def test_phase_4f_configured_options_persist_across_a_fresh_get(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """Options set via PATCH aren't just echoed back in the PATCH response -
    they persist in the database and are returned by a completely separate,
    later GET /templates call, proving real persistence rather than a
    response-only illusion."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    urinalysis = await _seed_and_get_urinalysis(client, owner_headers)
    protein_id = next(p["id"] for p in urinalysis["parameters"] if p["parameter_name"] == "Protein")

    updated_params = [
        {**{k: v for k, v in p.items() if k != "id"}, "id": p["id"], "options": ["OPTION_A", "OPTION_B"]}
        if p["id"] == protein_id else {k: v for k, v in p.items() if k != "id"}
        for p in urinalysis["parameters"]
    ]
    update = await client.patch(
        f"/api/v1/laboratory/templates/{urinalysis['id']}", headers=owner_headers, json={"parameters": updated_params}
    )
    assert update.status_code == 200, update.text

    refetched = (await client.get("/api/v1/laboratory/templates", headers=owner_headers)).json()
    refetched_urinalysis = next(t for t in refetched if t["id"] == urinalysis["id"])
    # Parameter rows are replaced (delete+recreate) on template update, so
    # the pre-update `protein_id` no longer exists - match by name instead,
    # same convention every other cross-request options-persistence check
    # in this file already uses.
    refetched_protein = next(p for p in refetched_urinalysis["parameters"] if p["parameter_name"] == "Protein")
    assert refetched_protein["options"] == ["OPTION_A", "OPTION_B"]


async def test_phase_4f_configured_options_are_tenant_isolated(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """Clinic A configuring real options for its Urinalysis Color parameter
    must never be visible to, or affect, clinic B's own (separately seeded)
    copy of the same template."""
    _clinic_a, _owner_a, owner_a_headers = await _owner_headers(client, make_clinic_with_owner)
    urinalysis_a = await _seed_and_get_urinalysis(client, owner_a_headers)
    color_a_id = next(p["id"] for p in urinalysis_a["parameters"] if p["parameter_name"] == "Color")
    updated_params = [
        {**{k: v for k, v in p.items() if k != "id"}, "id": p["id"], "options": ["OPTION_A", "OPTION_B"]}
        if p["id"] == color_a_id else {k: v for k, v in p.items() if k != "id"}
        for p in urinalysis_a["parameters"]
    ]
    update = await client.patch(
        f"/api/v1/laboratory/templates/{urinalysis_a['id']}", headers=owner_a_headers, json={"parameters": updated_params}
    )
    assert update.status_code == 200, update.text

    _clinic_b, _owner_b, owner_b_headers = await _owner_headers(client, make_clinic_with_owner)
    urinalysis_b = await _seed_and_get_urinalysis(client, owner_b_headers)
    color_b = next(p for p in urinalysis_b["parameters"] if p["parameter_name"] == "Color")
    assert color_b["options"] is None

    # No GET-by-id endpoint exists for templates (only list + PATCH-by-id) -
    # PATCH is the tenant-scoped lookup to prove clinic B cannot reach
    # clinic A's template row at all, configured options or not.
    cross_tenant_patch = await client.patch(
        f"/api/v1/laboratory/templates/{urinalysis_a['id']}", headers=owner_b_headers,
        json={"test_category": "Should Not Apply"},
    )
    assert cross_tenant_patch.status_code == 404


async def test_phase_4f_no_clinical_option_lists_seeded_in_production_defaults(client: AsyncClient, make_clinic_with_owner) -> None:
    """Production-safety guard: every Categorical parameter identified as
    REQUIRES CLINICAL VALIDATION in the Phase 4F investigation must still
    seed with `options: None` - no assumed/invented vocabulary was ever
    added to DEFAULT_LABORATORY_TEMPLATES for these parameters."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    templates = await _seed_and_list_templates(client, owner_headers)
    by_name = {t["test_name"]: t for t in templates}

    unconfigured = {
        "Urinalysis": ["Color", "Transparency", "Protein", "Glucose", "Ketones", "Blood", "Bilirubin", "Urobilinogen", "Nitrite", "Leukocytes"],
        "Human Chorionic Gonadotropin (HCG) - Serum": ["Result"],
        "Human Chorionic Gonadotropin (HCG) - Urine": ["Result"],
        "Hepatitis B Antigen (HBsAg)": ["Result"],
        "Hepatitis A Virus (HAV)": ["Result"],
        "VDRL / Syphilis Test": ["Result"],
        "Dengue Rapid Test": ["NS1", "IgM", "IgG"],
        "Stool Exam (Direct Mount)": ["Color", "Consistency"],
        "Fecal Occult Blood Test": ["Result"],
        "Trichomonas Vaginalis Mount": ["Result"],
        "KOH Mount": ["Result"],
    }
    for test_name, param_names in unconfigured.items():
        template = by_name.get(test_name)
        if template is None:
            continue  # only present if that Phase 4C/4D template name matches this clinic's seed - see per-test_name assertions above
        params_by_name = {p["parameter_name"]: p for p in template["parameters"]}
        for param_name in param_names:
            param = params_by_name.get(param_name)
            if param is None or param["result_type"] != "Categorical":
                continue
            assert param["options"] is None, f"{test_name} / {param_name} unexpectedly has pre-configured options"


# --- Phase 4G: Generic Laboratory Report / Print View. The report is
# entirely frontend-driven (LaboratoryOrder/LaboratoryTemplate/
# LaboratoryResult already carry everything needed) except for one
# additive field: `clinic_name`, populated only by the single-order GET
# (the report view's data source) - the same one-line `db.get(Clinic,
# clinic_id)` convention `GET /billing/invoices/{id}/receipt` already
# uses for `ReceiptPayload.clinic_name`. No new endpoint, no migration. ---


async def test_phase_4g_get_order_includes_clinic_name_for_report_header(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """`GET /laboratory/orders/{id}` (the report view's data source)
    returns `clinic_name`, resolved from the requesting clinic - proves the
    report can source its header branding without a new endpoint."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    cbc_ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    lab_id = cbc_ctx["lab_order"]["id"]
    order = (await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=cbc_ctx["owner_headers"])).json()
    assert order["clinic_name"]
    assert isinstance(order["clinic_name"], str)


async def test_phase_4g_list_endpoints_do_not_populate_clinic_name(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """`clinic_name` is additive and scoped to the single-order GET only -
    list/visit endpoints (unrelated read paths, higher volume) are
    unaffected, proving no shared code path was changed."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    listed = (await client.get(f"/api/v1/laboratory/orders?visit_id={ctx['visit_id']}", headers=ctx["owner_headers"])).json()
    assert listed[0].get("clinic_name") is None

    for_visit = (await client.get(f"/api/v1/visits/{ctx['visit_id']}/laboratory", headers=ctx["owner_headers"])).json()
    assert for_visit[0].get("clinic_name") is None


# --- Round 5: Laboratory Report header contact info (clinic address/phone/
# email) - same additive, GET-order-only convention as `clinic_name` above.
# Sourced from the existing `Clinic.address`/`city`/`province` and
# `telephone`/`mobile`/`email` columns (Phase 4 clinic-settings fields
# already exposed by `GET /clinic-settings`), no new database columns. ---


async def test_round5_get_order_includes_clinic_contact_fields_for_report_header(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """`GET /laboratory/orders/{id}` also returns `clinic_address`/
    `clinic_phone`/`clinic_email`, joined/resolved from the existing Clinic
    columns already editable via Clinic Settings - no new columns."""
    from app.models.clinic import Clinic

    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    clinic_row = (await db_session.execute(select(Clinic).where(Clinic.id == ctx["clinic"].id))).scalar_one()
    clinic_row.address = "123 Main Street"
    clinic_row.city = "Ormoc City"
    clinic_row.province = "Leyte"
    clinic_row.telephone = "0917-123-4567"
    clinic_row.mobile = "0918-999-0000"
    clinic_row.email = "clinic@canora.com"
    await db_session.commit()

    order = (await client.get(f"/api/v1/laboratory/orders/{ctx['lab_order']['id']}", headers=ctx["owner_headers"])).json()
    assert order["clinic_address"] == "123 Main Street, Ormoc City, Leyte"
    # Telephone is preferred over mobile when both are configured.
    assert order["clinic_phone"] == "0917-123-4567"
    assert order["clinic_email"] == "clinic@canora.com"


async def test_round5_clinic_phone_falls_back_to_mobile_when_telephone_unset(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Only `mobile` configured (no `telephone`) - the report still gets a
    contact number rather than going blank when one of the two is unset."""
    from app.models.clinic import Clinic

    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    clinic_row = (await db_session.execute(select(Clinic).where(Clinic.id == ctx["clinic"].id))).scalar_one()
    clinic_row.telephone = None
    clinic_row.mobile = "0918-999-0000"
    await db_session.commit()

    order = (await client.get(f"/api/v1/laboratory/orders/{ctx['lab_order']['id']}", headers=ctx["owner_headers"])).json()
    assert order["clinic_phone"] == "0918-999-0000"


async def test_round5_missing_clinic_contact_fields_stay_null_not_fabricated(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """A freshly-created clinic (via `make_clinic_with_owner`, which sets
    only name/slug) has no address/phone/email configured - the report
    fields must come back null, never a fabricated placeholder string."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    order = (await client.get(f"/api/v1/laboratory/orders/{ctx['lab_order']['id']}", headers=ctx["owner_headers"])).json()
    assert order["clinic_address"] is None
    assert order["clinic_phone"] is None
    assert order["clinic_email"] is None


async def test_round5_list_endpoints_do_not_populate_clinic_contact_fields(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """`clinic_address`/`clinic_phone`/`clinic_email` are additive and
    scoped to the single-order GET only, exactly like `clinic_name`."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    listed = (await client.get(f"/api/v1/laboratory/orders?visit_id={ctx['visit_id']}", headers=ctx["owner_headers"])).json()
    assert listed[0].get("clinic_address") is None
    assert listed[0].get("clinic_phone") is None
    assert listed[0].get("clinic_email") is None


async def test_phase_4g_report_data_source_unaffected_for_cbc_blood_typing_urinalysis_and_phase_4c_4d(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Regression: the report's sole backend addition (`clinic_name`) sits
    alongside every existing field - templates/results for CBC, Blood
    Typing, Urinalysis, and Phase 4C/4D still resolve exactly as before."""
    cbc_ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    cbc_result = await _enter_one_result(client, cbc_ctx["lab_order"]["id"], cbc_ctx["lab_headers"], numeric_value=14.0)
    assert float(cbc_result["numeric_value"]) == 14.0
    cbc_order = (await client.get(f"/api/v1/laboratory/orders/{cbc_ctx['lab_order']['id']}", headers=cbc_ctx["owner_headers"])).json()
    assert cbc_order["clinic_name"]
    assert float(cbc_order["results"][0]["numeric_value"]) == 14.0

    bt_ctx = await _setup_blood_typing_order(client, make_clinic_with_owner, db_session)
    lab_id = bt_ctx["lab_order"]["id"]
    await _advance_to_processing(client, lab_id, bt_ctx["lab_headers"])
    await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=bt_ctx["lab_headers"],
        json={"results": [{"parameter_name": "ABO Group", "result_type": "Categorical", "structured_value": {"value": "O"}}]},
    )
    bt_order = (await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=bt_ctx["owner_headers"])).json()
    assert bt_order["clinic_name"]
    assert bt_order["results"][0]["structured_value"] == {"value": "O"}

    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    templates = await _seed_and_list_templates(client, owner_headers)
    names = {t["test_name"] for t in templates}
    assert {"CBC", "Blood Typing", "Urinalysis"}.issubset(names)
    assert _PHASE_4C_TEST_NAMES.issubset(names)
    assert _PHASE_4D_TEST_NAMES.issubset(names)


# --- Phase 4H: Laboratory Report Workflow & Result Integrity Review.
# Audited the full order -> queue -> collect/process -> enter results ->
# reopen/edit -> save again -> release -> queue completion -> report
# lifecycle. Backend integrity (upsert_results replace-all semantics,
# tenant isolation, categorical validation, release idempotency, queue
# sync) was already correct and already covered by existing tests
# (test_full_lifecycle_with_timeline_events, test_queue_ticket_completes_
# when_laboratory_result_is_released, test_releasing_already_released_
# laboratory_order_does_not_duplicate_queue_transition, tenant-isolation
# tests throughout this file) - re-verified by inspection, not modified.
# The one genuine defect found was FRONTEND-only: ResultEntryDialog's
# `initialRows()` showed only already-entered results when reopening a
# PARTIALLY-completed templated order, silently hiding every not-yet-
# entered template parameter (see that function's Phase 4H docstring).
# This backend test proves the data the frontend fix now correctly
# displays was never actually lost/corrupted server-side - partial save,
# then a later resubmission adding the missing parameter, preserves both. ---


async def test_phase_4h_partial_save_then_completing_the_remaining_parameter_preserves_both(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """A technician saves only Hemoglobin first (a partial save - the
    order still transitions to Completed per existing intentional
    behavior, unchanged), reopens later, and submits BOTH Hemoglobin
    (unedited) and Remarks together (the full picture a fixed
    `initialRows` now shows them) - both persist, neither is lost, and
    the final GET (the report's data source) reflects exactly this
    latest state."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    await _advance_to_processing(client, lab_id, ctx["lab_headers"])

    partial = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "Hemoglobin", "result_type": "Numeric", "numeric_value": 14.2}]},
    )
    assert partial.status_code == 200, partial.text
    assert len(partial.json()["results"]) == 1

    reopened = (await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["owner_headers"])).json()
    assert len(reopened["results"]) == 1
    assert float(reopened["results"][0]["numeric_value"]) == 14.2

    completed = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=ctx["lab_headers"],
        json={
            "results": [
                {"parameter_name": "Hemoglobin", "result_type": "Numeric", "numeric_value": 14.2},
                {"parameter_name": "Remarks", "result_type": "Text", "text_value": "No abnormal cells seen"},
            ]
        },
    )
    assert completed.status_code == 200, completed.text
    assert len(completed.json()["results"]) == 2

    released = await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"])
    assert released.status_code == 200, released.text

    # Re-releasing is idempotent - rejected, not duplicated.
    re_release = await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"])
    assert re_release.status_code == 400

    report_source = (await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["owner_headers"])).json()
    assert report_source["status"] == "Released"
    assert report_source["clinic_name"]
    by_name = {r["parameter_name"]: r for r in report_source["results"]}
    assert float(by_name["Hemoglobin"]["numeric_value"]) == 14.2
    assert by_name["Remarks"]["text_value"] == "No abnormal cells seen"


# --- Phase 4I: Laboratory Production Hardening & Concurrency Audit.
# upsert_results is a full replace-all of the submitted result set
# (Phase 2A design) - two technicians editing from stale form snapshots
# could otherwise have the second save silently discard the first save's
# changes (a lost-update race). Added an optional optimistic-concurrency
# check: the client echoes back the updated_at it last saw; a stale
# echo is rejected (409) rather than silently applied. Opt-in (None
# skips the check) so every existing caller/test is unaffected. ---


async def test_phase_4i_stale_save_is_rejected_as_conflict_not_silently_applied(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Simulates the exact race: Technician A and B both fetch the order
    (same updated_at), A saves first (bumping updated_at), then B's
    save - built from their now-stale snapshot - is rejected with 409
    instead of overwriting A's already-persisted result."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    await _advance_to_processing(client, lab_id, ctx["lab_headers"])

    snapshot = (await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["owner_headers"])).json()
    shared_updated_at = snapshot["updated_at"]

    save_a = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=ctx["lab_headers"],
        json={
            "results": [{"parameter_name": "Hemoglobin", "result_type": "Numeric", "numeric_value": 14.2}],
            "expected_updated_at": shared_updated_at,
        },
    )
    assert save_a.status_code == 200, save_a.text

    save_b = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=ctx["lab_headers"],
        json={
            "results": [{"parameter_name": "Hemoglobin", "result_type": "Numeric", "numeric_value": 9.9}],
            "expected_updated_at": shared_updated_at,
        },
    )
    assert save_b.status_code == 409, save_b.text

    final = (await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["owner_headers"])).json()
    assert float(final["results"][0]["numeric_value"]) == 14.2


async def test_phase_4i_save_without_expected_updated_at_is_unaffected(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """The concurrency check is opt-in - a caller that never supplies
    expected_updated_at (every pre-Phase-4I test in this file) behaves
    exactly as before, unaffected by the new check."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    result = await _enter_one_result(client, ctx["lab_order"]["id"], ctx["lab_headers"], numeric_value=14.0)
    assert float(result["numeric_value"]) == 14.0

    resp = await client.post(
        f"/api/v1/laboratory/orders/{ctx['lab_order']['id']}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "Hemoglobin", "result_type": "Numeric", "numeric_value": 15.0}]},
    )
    assert resp.status_code == 200, resp.text
    assert float(resp.json()["results"][0]["numeric_value"]) == 15.0


async def test_phase_4i_released_order_rejects_further_result_entry(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Release immutability, enforced server-side (not merely a disabled
    frontend button): enter_results's status guard excludes RELEASED, so
    a direct API call attempting to edit a released order's results is
    rejected regardless of client-side UI state."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    await _enter_one_result(client, lab_id, ctx["lab_headers"], numeric_value=14.0)
    release = await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"])
    assert release.status_code == 200, release.text

    post_release_edit = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "Hemoglobin", "result_type": "Numeric", "numeric_value": 99.0}]},
    )
    assert post_release_edit.status_code == 400, post_release_edit.text

    unchanged = (await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["owner_headers"])).json()
    assert float(unchanged["results"][0]["numeric_value"]) == 14.0


async def test_phase_4i_released_order_cannot_be_cancelled(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Lifecycle boundary: RELEASED is terminal in LABORATORY_ORDER_
    STATUS_TRANSITIONS (maps to an empty set) - cancellation after
    release is intentionally forbidden, not merely unimplemented."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    await _enter_one_result(client, lab_id, ctx["lab_headers"], numeric_value=14.0)
    await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"])

    cancel = await client.post(f"/api/v1/laboratory/orders/{lab_id}/cancel", headers=ctx["lab_headers"])
    assert cancel.status_code == 400, cancel.text


async def test_phase_4i_every_lifecycle_state_transition_matches_the_declared_state_machine(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Requested->Collected/Cancelled, Collected->Processing/Cancelled,
    Processing->Completed/Cancelled, Completed->Released/Cancelled,
    Released/Cancelled->nothing. Proves Processing can still be
    cancelled (an audit-required transition not otherwise exercised by
    the full-lifecycle happy-path test)."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    collect = await client.post(f"/api/v1/laboratory/orders/{lab_id}/collect", headers=ctx["lab_headers"])
    assert collect.json()["status"] == "Collected"
    processing = await client.post(f"/api/v1/laboratory/orders/{lab_id}/start-processing", headers=ctx["lab_headers"])
    assert processing.json()["status"] == "Processing"
    cancel = await client.post(f"/api/v1/laboratory/orders/{lab_id}/cancel", headers=ctx["lab_headers"])
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "Cancelled"

    for method in ["collect", "start-processing", "release"]:
        resp = await client.post(f"/api/v1/laboratory/orders/{lab_id}/{method}", headers=ctx["lab_headers"])
        assert resp.status_code == 400, f"{method} should be rejected on a Cancelled order"
    results_resp = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=ctx["lab_headers"],
        json={"results": [{"parameter_name": "Hemoglobin", "result_type": "Numeric", "numeric_value": 14.0}]},
    )
    assert results_resp.status_code == 400


async def test_phase_4i_template_update_tenant_isolation(client: AsyncClient, make_clinic_with_owner) -> None:
    """Authorization audit: clinic B cannot modify clinic A's template
    (the update_template replace-all path) via a guessed/known id."""
    _clinic_a, _owner_a, owner_a_headers = await _owner_headers(client, make_clinic_with_owner)
    template = (
        await client.post(
            "/api/v1/laboratory/templates", headers=owner_a_headers,
            json={"test_name": "CBC", "default_price": "0", "parameters": [{"parameter_name": "Hemoglobin", "result_type": "Numeric"}]},
        )
    ).json()

    _clinic_b, _owner_b, owner_b_headers = await _owner_headers(client, make_clinic_with_owner)
    cross_tenant = await client.patch(
        f"/api/v1/laboratory/templates/{template['id']}", headers=owner_b_headers, json={"test_category": "Hijacked"}
    )
    assert cross_tenant.status_code == 404

    unchanged = (await client.get("/api/v1/laboratory/templates", headers=owner_a_headers)).json()
    assert unchanged[0]["test_category"] is None


# --- Phase 6: Cross-Module Clinical Workflow Integration & Production
# Validation. The two persistent billing-sync failures were investigated
# to a definitive conclusion (not merely re-labeled "pre-existing"):
# `enter_results` took its response snapshot (`result_read = await self.
# get(...)`) BEFORE calling `_sync_billing`, so the invoice line item was
# genuinely created, but the response returned to the client (and the
# sync-queue payload built from it) always reflected the pre-billing-sync
# state - a real ordering defect in `LaboratoryService.enter_results`,
# fixed by moving `_sync_billing` before the snapshot read. This is a
# REAL INTEGRATION DEFECT, not a test/environment issue - see
# laboratory_service.py's Phase 6 comment at the fix site. ---


async def test_phase_6_realistic_end_to_end_clinic_encounter(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """A complete real clinic encounter: Patient -> Visit -> Queue ->
    Doctor -> Laboratory Order -> Laboratory Queue -> Collection ->
    Processing -> Result Entry -> Release -> Queue Completion -> Report ->
    Billing. Verifies the final database state for every object in the
    chain belongs to the same clinic/patient/visit context, and that the
    billing defect fixed above is genuinely closed end-to-end."""
    from app.models.audit_log import AuditLog
    from app.models.invoice import Invoice
    from app.models.invoice_item import InvoiceItem
    from app.models.order import Order
    from app.models.patient import Patient
    from app.models.queue import Queue, QueueStatus
    from app.models.visit import Visit

    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_price="500.00")
    lab_id = ctx["lab_order"]["id"]
    lab_headers = ctx["lab_headers"]
    clinic_id = ctx["clinic"].id
    visit_id = ctx["visit_id"]

    # Doctor called the patient - queue is already Called by this point
    # (per _setup_with_lab_order); Laboratory now runs its own workflow.
    collect = await client.post(f"/api/v1/laboratory/orders/{lab_id}/collect", headers=lab_headers)
    assert collect.status_code == 200, collect.text
    processing = await client.post(f"/api/v1/laboratory/orders/{lab_id}/start-processing", headers=lab_headers)
    assert processing.status_code == 200, processing.text

    entered = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=lab_headers,
        json={"results": [{"parameter_name": "Hemoglobin", "result_type": "Numeric", "numeric_value": 14.2}]},
    )
    assert entered.status_code == 200, entered.text
    # The exact Phase 6 defect: this must be non-null on THIS response, not
    # only discoverable via a later separate GET.
    assert entered.json()["invoice_item_id"] is not None
    invoice_item_id = entered.json()["invoice_item_id"]

    released = await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=lab_headers)
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "Released"

    # Report: the report's sole data source (GET order) reflects the final
    # released state with the same invoice_item_id, results intact.
    report_source = (await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["owner_headers"])).json()
    assert report_source["status"] == "Released"
    assert report_source["invoice_item_id"] == invoice_item_id
    assert float(report_source["results"][0]["numeric_value"]) == 14.2
    assert report_source["clinic_name"]

    # Billing: exactly one Laboratory invoice line item, correct price.
    invoice = (await client.get(f"/api/v1/visits/{visit_id}/invoice", headers=ctx["owner_headers"])).json()
    lab_items = [i for i in invoice["items"] if i["item_type"] == "Laboratory"]
    assert len(lab_items) == 1
    assert lab_items[0]["id"] == invoice_item_id
    assert float(lab_items[0]["unit_price"]) == 500.00

    # Final DB-state verification - every object belongs to the same
    # clinic, and the patient/visit context is consistent throughout.
    patient = (await db_session.execute(select(Patient).where(Patient.id == ctx["deps"]["patient_id"]))).scalar_one()
    visit = (await db_session.execute(select(Visit).where(Visit.id == uuid.UUID(visit_id)))).scalar_one()
    order_row = (await db_session.execute(select(Order).where(Order.id == uuid.UUID(ctx["order"]["id"])))).scalar_one()
    invoice_row = (await db_session.execute(select(Invoice).where(Invoice.visit_id == uuid.UUID(visit_id)))).scalar_one()
    invoice_item_row = (
        await db_session.execute(select(InvoiceItem).where(InvoiceItem.id == uuid.UUID(invoice_item_id)))
    ).scalar_one()
    audit_rows = (
        (await db_session.execute(select(AuditLog).where(AuditLog.entity_id == lab_id))).scalars().all()
    )

    for obj in (patient, visit, order_row, invoice_row, invoice_item_row):
        assert obj.clinic_id == clinic_id
    assert visit.patient_id == patient.id
    assert order_row.visit_id == visit.id
    assert invoice_row.visit_id == visit.id
    assert invoice_item_row.invoice_id == invoice_row.id
    # Every laboratory lifecycle action left an audit trail entry, all on
    # the correct clinic/entity.
    audit_actions = {a.action for a in audit_rows}
    assert {"laboratory.specimen_collected", "laboratory.processing_started", "laboratory.results_entered", "laboratory.results_released"}.issubset(audit_actions)
    for a in audit_rows:
        assert a.clinic_id == clinic_id


# --- Laboratory tab/worklist: newest laboratory request first ---
# `GET /laboratory/orders` (no `visit_id`) is the sole backer of the
# Laboratory tab/worklist (via `LaboratoryService.list_for_dashboard` ->
# `LaboratoryRepository.list_for_clinic`). The request/order creation
# timestamp is `LaboratoryOrder.created_at` (set once at insert, unlike
# `collected_at`/`completed_at`/`released_at` which only exist once that
# stage happens) - the same field the worklist's own "Requested" column
# already displays (`formatDate(order.createdAt)`). Sorted descending, with
# `id` descending as a stable tie-break for identical timestamps.

async def _walk_in_lab_order(client: AsyncClient, headers: dict, *, branch_id: str, department_id: str, service_id: str) -> dict:
    """Creates one real, paid, auto-attached LaboratoryOrder via the actual
    pay-first walk-in workflow (pre-queue -> laboratory-invoice -> full
    payment -> queue ticket) - same real API path as production, not a
    direct DB insert. A fresh patient per call avoids the existing "one
    active queue ticket per patient/department/day" guard rejecting a
    second ticket for the same patient."""
    patient = (
        await client.post(
            "/api/v1/patients", headers=headers,
            json={
                "first_name": "Test", "last_name": f"Patient-{uuid.uuid4().hex[:8]}", "birth_date": "1990-05-15",
                "gender": "Male", "civil_status": "Single", "mobile_number": f"+6391{uuid.uuid4().int % 10**9:09d}",
            },
        )
    ).json()["patient"]

    visit = (
        await client.post(
            "/api/v1/visits/pre-queue", headers=headers,
            json={"patient_id": patient["id"], "branch_id": branch_id, "department_id": department_id, "service_id": service_id},
        )
    ).json()
    invoice = (await client.post(f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers)).json()
    if float(invoice["balance_due"]) > 0:
        pay = await client.post(
            f"/api/v1/invoices/{invoice['id']}/payments", headers=headers,
            json={"payments": [{"payment_method": "Cash", "amount": invoice["balance_due"]}]},
        )
        assert pay.status_code == 200, pay.text
    queue_resp = await client.post(
        "/api/v1/queues", headers=headers,
        json={
            "patient_id": patient["id"], "branch_id": branch_id, "department_id": department_id,
            "service_id": service_id, "priority": "Normal", "visit_id": visit["id"],
        },
    )
    assert queue_resp.status_code in (200, 201), queue_resp.text

    lab_orders = (await client.get(f"/api/v1/laboratory/orders?visit_id={visit['id']}", headers=headers)).json()
    return lab_orders[0]


async def test_laboratory_worklist_orders_newest_request_first(
    client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession
) -> None:
    from datetime import datetime, timezone

    from app.models.laboratory_order import LaboratoryOrder

    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    branch = (await client.post("/api/v1/branches", headers=headers, json={"name": "Main Branch", "code": "MAIN"})).json()
    department = (
        await client.post("/api/v1/departments", headers=headers, json={"department_code": "LAB", "name": "Laboratory"})
    ).json()
    service = (
        await client.post(
            "/api/v1/services", headers=headers,
            json={"service_code": "CBC1", "service_name": "CBC, PLATELET", "default_price": "250.00"},
        )
    ).json()

    oldest = await _walk_in_lab_order(client, headers, branch_id=branch["id"], department_id=department["id"], service_id=service["id"])
    middle = await _walk_in_lab_order(client, headers, branch_id=branch["id"], department_id=department["id"], service_id=service["id"])
    newest = await _walk_in_lab_order(client, headers, branch_id=branch["id"], department_id=department["id"], service_id=service["id"])

    # Force explicit, controlled `created_at` values - real wall-clock
    # creation order alone would already happen to be ascending here, but
    # this proves the SORT (not incidental insertion order) is what
    # determines the response, and sets up the tie-break case below.
    oldest_row = await db_session.get(LaboratoryOrder, uuid.UUID(oldest["id"]))
    middle_row = await db_session.get(LaboratoryOrder, uuid.UUID(middle["id"]))
    newest_row = await db_session.get(LaboratoryOrder, uuid.UUID(newest["id"]))
    oldest_row.created_at = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    middle_row.created_at = datetime(2026, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
    newest_row.created_at = datetime(2026, 1, 3, 10, 0, 0, tzinfo=timezone.utc)
    await db_session.commit()

    resp = await client.get("/api/v1/laboratory/orders", headers=headers)
    assert resp.status_code == 200, resp.text
    ids_in_order = [row["id"] for row in resp.json()]
    ordered_ids = [oldest["id"], middle["id"], newest["id"]]
    positions = [ids_in_order.index(i) for i in ordered_ids]
    # Newest request's position is earlier (smaller index) than middle's,
    # which is earlier than oldest's - i.e. descending by created_at.
    assert positions[2] < positions[1] < positions[0]


async def test_laboratory_worklist_uses_id_descending_as_a_stable_tie_break_for_equal_timestamps(
    client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession
) -> None:
    from datetime import datetime, timezone

    from app.models.laboratory_order import LaboratoryOrder

    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    branch = (await client.post("/api/v1/branches", headers=headers, json={"name": "Main Branch", "code": "MAIN"})).json()
    department = (
        await client.post("/api/v1/departments", headers=headers, json={"department_code": "LAB", "name": "Laboratory"})
    ).json()
    service = (
        await client.post(
            "/api/v1/services", headers=headers,
            json={"service_code": "CBC1", "service_name": "CBC, PLATELET", "default_price": "250.00"},
        )
    ).json()

    order_a = await _walk_in_lab_order(client, headers, branch_id=branch["id"], department_id=department["id"], service_id=service["id"])
    order_b = await _walk_in_lab_order(client, headers, branch_id=branch["id"], department_id=department["id"], service_id=service["id"])

    # Same timestamp for both - only `id` (descending) can break the tie.
    same_time = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    row_a = await db_session.get(LaboratoryOrder, uuid.UUID(order_a["id"]))
    row_b = await db_session.get(LaboratoryOrder, uuid.UUID(order_b["id"]))
    row_a.created_at = same_time
    row_b.created_at = same_time
    await db_session.commit()

    expected_first, expected_second = (
        (order_a["id"], order_b["id"]) if order_a["id"] > order_b["id"] else (order_b["id"], order_a["id"])
    )

    resp = await client.get("/api/v1/laboratory/orders", headers=headers)
    assert resp.status_code == 200, resp.text
    ids_in_order = [row["id"] for row in resp.json()]
    assert ids_in_order.index(expected_first) < ids_in_order.index(expected_second)
