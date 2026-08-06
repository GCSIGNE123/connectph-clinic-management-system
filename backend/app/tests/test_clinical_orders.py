"""Integration tests for Phase 9 Clinical Orders & Prescriptions: order
creation per category with correct order-number sequencing, order status
update, procedures/referrals as their own tables, prescriptions with
unlimited items, validation warnings (duplicate medicine / missing dosage /
missing duration - non-blocking), timeline events for each creation type,
role gating (assigned doctor edits, other doctor/Reception read-only,
Laboratory role scoped to Laboratory orders only), patient-prescriptions
and visit-orders/visit-prescriptions read endpoints, and tenant isolation.
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


def _queue_payload(deps: dict, **overrides) -> dict:
    payload = {
        "patient_id": deps["patient_id"], "branch_id": deps["branch_id"],
        "department_id": deps["department_id"], "doctor_id": deps["doctor_id"],
        "service_id": deps["service_id"], "priority": "Normal",
    }
    payload.update(overrides)
    return payload


async def _make_role_login(db_session: AsyncSession, *, clinic_id, role_name: str, doctor_id=None, password: str):
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


async def _create_visit(client, headers, deps) -> dict:
    queue = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()
    assert queue.get("visit_id"), queue
    return queue


async def _advance_to_in_consultation(client, doc_headers, visit_id) -> None:
    r1 = await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/call", headers=doc_headers)
    assert r1.status_code == 200, r1.text
    r2 = await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/start-consultation", headers=doc_headers)
    assert r2.status_code == 200, r2.text


async def _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session):
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    queue = await _create_visit(client, owner_headers, deps)
    visit_id = queue["visit_id"]

    doc_email, _doc_user = await _make_role_login(
        db_session, clinic_id=clinic.id, role_name="Doctor", doctor_id=deps["doctor_id"], password="DoctorPass123!"
    )
    doc_token = await _login(client, doc_email, "DoctorPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}
    await _advance_to_in_consultation(client, doc_headers, visit_id)

    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    cid = opened["id"]
    return clinic, owner_headers, doc_headers, deps, visit_id, cid


# --- Order creation, per category, with correct numbering ---

async def test_create_laboratory_order(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)

    resp = await client.post(
        f"/api/v1/consultations/{cid}/orders", headers=doc_headers,
        json={"order_category": "Laboratory", "priority": "Routine", "items": [{"item_name": "CBC"}, {"item_name": "Urinalysis"}]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["order_category"] == "Laboratory"
    assert body["order_number"].startswith("ORD-")
    assert len(body["items"]) == 2


async def test_create_radiology_order_with_imaging_fields(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)

    resp = await client.post(
        f"/api/v1/consultations/{cid}/orders", headers=doc_headers,
        json={
            "order_category": "Radiology", "priority": "STAT",
            "items": [{"item_name": "Chest X-Ray", "exam_type": "X-Ray", "body_part": "Chest", "clinical_indication": "Cough"}],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"][0]["exam_type"] == "X-Ray"
    assert body["items"][0]["body_part"] == "Chest"


async def test_order_number_sequencing(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)

    numbers = []
    for category in ("Laboratory", "Vaccination", "Custom"):
        resp = await client.post(
            f"/api/v1/consultations/{cid}/orders", headers=doc_headers,
            json={"order_category": category, "items": [{"item_name": "Item"}]},
        )
        assert resp.status_code == 200, resp.text
        numbers.append(resp.json()["order_number"])
    assert len(set(numbers)) == 3, "Order numbers must be unique/sequential"


async def test_order_status_update(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)

    order = (await client.post(
        f"/api/v1/consultations/{cid}/orders", headers=doc_headers,
        json={"order_category": "Laboratory", "items": [{"item_name": "CBC"}]},
    )).json()

    resp = await client.patch(f"/api/v1/orders/{order['id']}/status", headers=doc_headers, json={"status": "Collected"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "Collected"

    resp2 = await client.patch(f"/api/v1/orders/{order['id']}/status", headers=doc_headers, json={"status": "Completed"})
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "Completed"


# --- Procedures / Referrals as separate tables ---

async def test_create_procedure(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)

    resp = await client.post(
        f"/api/v1/consultations/{cid}/procedures", headers=doc_headers,
        json={"procedure_name": "Wound Dressing", "notes": "Left arm"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["procedure_name"] == "Wound Dressing"
    assert body["status"] == "Requested"
    assert "order_number" not in body  # Procedures have no order number, per spec


async def test_create_referral(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)

    resp = await client.post(
        f"/api/v1/consultations/{cid}/referrals", headers=doc_headers,
        json={"referred_to": "Dr. Cardio Specialist", "reason": "Chest pain evaluation"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["referred_to"] == "Dr. Cardio Specialist"


# --- Prescriptions: unlimited items + non-blocking validation warnings ---

async def test_create_prescription_with_many_items(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)

    items = [
        {"medicine": f"Medicine {i}", "dosage": "500mg", "frequency": "BID", "duration": "5 days", "quantity": "10"}
        for i in range(6)
    ]
    resp = await client.post(f"/api/v1/consultations/{cid}/prescriptions", headers=doc_headers, json={"items": items})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["prescription"]["items"]) == 6, "Prescriptions must support unlimited (6+) line items"
    assert body["warnings"] == []
    assert body["prescription"]["prescription_number"].startswith("RX-")


async def test_prescription_validation_warnings_do_not_block_save(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)

    items = [
        {"medicine": "Amoxicillin", "dosage": "500mg", "frequency": "TID", "duration": "7 days"},
        {"medicine": "Amoxicillin", "dosage": "500mg", "frequency": "BID", "duration": "5 days"},  # duplicate
        {"medicine": "Paracetamol", "frequency": "PRN"},  # missing dosage + duration
    ]
    resp = await client.post(f"/api/v1/consultations/{cid}/prescriptions", headers=doc_headers, json={"items": items})
    assert resp.status_code == 200, resp.text  # not blocked
    body = resp.json()
    assert len(body["prescription"]["items"]) == 3
    warnings = " | ".join(body["warnings"])
    assert "Duplicate medicine" in warnings
    assert "Missing dosage" in warnings
    assert "Missing duration" in warnings


# --- Timeline events ---

async def test_timeline_events_recorded_for_each_creation_type(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)

    await client.post(f"/api/v1/consultations/{cid}/orders", headers=doc_headers, json={"order_category": "Laboratory", "items": [{"item_name": "CBC"}]})
    await client.post(f"/api/v1/consultations/{cid}/procedures", headers=doc_headers, json={"procedure_name": "Dressing"})
    await client.post(f"/api/v1/consultations/{cid}/referrals", headers=doc_headers, json={"referred_to": "Specialist"})
    await client.post(f"/api/v1/consultations/{cid}/prescriptions", headers=doc_headers, json={"items": [{"medicine": "Amoxicillin", "dosage": "500mg", "duration": "7 days"}]})

    timeline = await client.get(f"/api/v1/consultations/{cid}/timeline", headers=doc_headers)
    event_types = {e["event_type"] for e in timeline.json()["events"]}
    assert {"OrderCreated", "ProcedureCreated", "ReferralCreated", "PrescriptionCreated"} <= event_types


# --- Role gating ---

async def test_other_doctor_and_reception_are_read_only(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, owner_headers, doc_headers, _deps, _visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)

    other_doctor = (await client.post("/api/v1/doctors", headers=owner_headers, json={"first_name": "Ana", "last_name": "Lopez"})).json()
    other_email, _ = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor", doctor_id=other_doctor["id"], password="DoctorPass123!")
    other_token = await _login(client, other_email, "DoctorPass123!")
    other_headers = {"Authorization": f"Bearer {other_token}"}

    # A different doctor may view but not create.
    view_resp = await client.get(f"/api/v1/consultations/{cid}/orders", headers=other_headers)
    assert view_resp.status_code == 200
    create_resp = await client.post(f"/api/v1/consultations/{cid}/procedures", headers=other_headers, json={"procedure_name": "X"})
    assert create_resp.status_code == 403

    # Reception: explicit read-only per this phase's spec (view allowed, edit denied).
    rec_email, _ = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Receptionist", password="ReceptPass123!")
    rec_token = await _login(client, rec_email, "ReceptPass123!")
    rec_headers = {"Authorization": f"Bearer {rec_token}"}

    rec_view = await client.get(f"/api/v1/consultations/{cid}/orders", headers=rec_headers)
    assert rec_view.status_code == 200
    rec_create = await client.post(f"/api/v1/consultations/{cid}/procedures", headers=rec_headers, json={"procedure_name": "X"})
    assert rec_create.status_code == 403


async def test_laboratory_role_scoped_to_laboratory_orders(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, _owner_headers, doc_headers, _deps, visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)

    await client.post(f"/api/v1/consultations/{cid}/orders", headers=doc_headers, json={"order_category": "Laboratory", "items": [{"item_name": "CBC"}]})
    await client.post(f"/api/v1/consultations/{cid}/orders", headers=doc_headers, json={"order_category": "Radiology", "items": [{"item_name": "X-Ray"}]})

    lab_email, _ = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Laboratory", password="LabPass123!")
    lab_token = await _login(client, lab_email, "LabPass123!")
    lab_headers = {"Authorization": f"Bearer {lab_token}"}

    # NOTE (Phase 10): `GET /laboratory/orders` is now owned by the full
    # Laboratory Management module (`api/v1/laboratory.py`), returning the
    # richer `LaboratoryOrderRead` shape (no `order_category` field, since
    # every row it returns is implicitly Laboratory-category by
    # construction - only Laboratory-category Orders get a `laboratory_orders`
    # row attached at all, see `ClinicalOrdersService.create_order`).
    resp = await client.get(f"/api/v1/laboratory/orders", headers=lab_headers, params={"visit_id": visit_id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["test_type"] == "CBC"

    # Laboratory role has no access to prescriptions.
    prescriptions_resp = await client.get(f"/api/v1/consultations/{cid}/prescriptions", headers=lab_headers)
    assert prescriptions_resp.status_code == 403


# --- Read endpoints ---

async def test_visit_and_patient_read_endpoints(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, deps, visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)

    await client.post(f"/api/v1/consultations/{cid}/orders", headers=doc_headers, json={"order_category": "Laboratory", "items": [{"item_name": "CBC"}]})
    await client.post(f"/api/v1/consultations/{cid}/prescriptions", headers=doc_headers, json={"items": [{"medicine": "Amoxicillin", "dosage": "500mg", "duration": "7 days"}]})

    visit_orders = await client.get(f"/api/v1/visits/{visit_id}/orders", headers=doc_headers)
    assert visit_orders.status_code == 200
    assert len(visit_orders.json()) == 1

    visit_prescriptions = await client.get(f"/api/v1/visits/{visit_id}/prescriptions", headers=doc_headers)
    assert visit_prescriptions.status_code == 200
    assert len(visit_prescriptions.json()) == 1

    patient_prescriptions = await client.get(f"/api/v1/patients/{deps['patient_id']}/prescriptions", headers=doc_headers)
    assert patient_prescriptions.status_code == 200
    assert len(patient_prescriptions.json()) == 1


# --- Tenant isolation ---

async def test_tenant_isolation(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic1, _owner1, doc1_headers, _deps1, _visit1_id, cid1 = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)
    _clinic2, _owner2, doc2_headers, _deps2, _visit2_id, _cid2 = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)

    resp = await client.get(f"/api/v1/consultations/{cid1}/orders", headers=doc2_headers)
    assert resp.status_code in (403, 404)
