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
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    result = await _enter_one_result(client, ctx["lab_order"]["id"], ctx["lab_headers"], numeric_value=14.0, range_low=None, range_high="16.0")
    assert result["interpretation"] is None


async def test_numeric_result_missing_upper_bound_stays_uninterpreted(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    result = await _enter_one_result(client, ctx["lab_order"]["id"], ctx["lab_headers"], numeric_value=14.0, range_low="12.0", range_high=None)
    assert result["interpretation"] is None


async def test_numeric_result_missing_range_entirely_stays_uninterpreted(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session, template_parameters=_RANGED_TEMPLATE_PARAMETERS)
    result = await _enter_one_result(client, ctx["lab_order"]["id"], ctx["lab_headers"], numeric_value=14.0, range_low=None, range_high=None)
    assert result["interpretation"] is None


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

async def test_seed_default_templates_creates_cbc_and_urinalysis_structure_only(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)

    resp = await client.post("/api/v1/laboratory/templates/seed-defaults", headers=owner_headers)
    assert resp.status_code == 200, resp.text
    created = resp.json()
    names = {t["test_name"] for t in created}
    assert names == {"CBC", "Urinalysis"}

    for template in created:
        for param in template["parameters"]:
            # Structure only - no clinical reference range values seeded.
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
