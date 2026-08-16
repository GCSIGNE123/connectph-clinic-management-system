"""Integration tests for Phase 9 Clinical Orders & Prescriptions: order
creation per category with correct order-number sequencing, order status
update, procedures/referrals as their own tables, prescriptions with
unlimited items, validation warnings (duplicate medicine / missing dosage /
missing duration - non-blocking), timeline events for each creation type,
role gating (assigned doctor edits, other doctor/Reception read-only,
Laboratory role scoped to Laboratory orders only), patient-prescriptions
and visit-orders/visit-prescriptions read endpoints, and tenant isolation.
"""

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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


# --- Atomic order creation / partial-order-state regression tests ---
#
# Regression coverage for the bug where `ClinicalOrdersService.create_order()`
# committed the parent `Order` in its own transaction BEFORE creating the
# Laboratory/Vaccination-category child record in a SEPARATE follow-up
# commit. Any failure in that follow-up step (most concretely: the shared
# daily order-number counter's first-of-day race, see
# `clinical_number_generator.py`) could leave a durably committed `Order`
# with no matching `LaboratoryOrder` - the doctor saw the Order after a
# refresh, but the Laboratory Technician's worklist correctly showed
# nothing, because the row genuinely never existed. NOTE: because this
# test file's `client` fixture overrides `get_db` to hand out the shared
# `db_session` directly (no automatic commit/rollback wrapper like the
# real `get_session()` dependency provides in production), a request that
# fails mid-transaction leaves `db_session` sitting on that same aborted/
# uncommitted transaction until we explicitly roll it back - exactly what
# `get_session()` would have done automatically for a real client.

async def test_laboratory_order_creation_creates_both_order_and_laboratory_order(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """The core "no split state" invariant this fix guarantees: a
    successful Laboratory order creation always produces BOTH rows
    together - the generic Order (what the doctor's Orders tab reads) and
    the LaboratoryOrder (what the Laboratory Technician's worklist
    reads)."""
    _clinic, _owner_headers, doc_headers, _deps, visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)

    resp = await client.post(
        f"/api/v1/consultations/{cid}/orders", headers=doc_headers,
        json={"order_category": "Laboratory", "items": [{"item_name": "CBC"}]},
    )
    assert resp.status_code == 200, resp.text
    order = resp.json()

    visit_orders = await client.get(f"/api/v1/visits/{visit_id}/orders", headers=doc_headers)
    assert any(o["id"] == order["id"] for o in visit_orders.json()), "parent Order must exist"

    lab_orders = await client.get("/api/v1/laboratory/orders", headers=doc_headers, params={"visit_id": visit_id})
    assert any(lo["order_id"] == order["id"] for lo in lab_orders.json()), "LaboratoryOrder child must exist alongside it"


async def test_forced_failure_in_laboratory_child_creation_rolls_back_parent_order(
    client: AsyncClient, make_clinic_with_owner, db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If anything fails while creating the Laboratory-specific child
    record, the parent Order must NOT survive as an orphan - this is the
    exact split state (Order committed, LaboratoryOrder missing) the bug
    produced. Forces the failure via `LaboratoryService.create_from_order`
    itself so the test doesn't depend on any particular trigger (e.g. the
    counter race, covered separately below) actually firing."""
    _clinic, _owner_headers, doc_headers, _deps, visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)

    from app.services.laboratory_service import LaboratoryService

    async def _boom(self, order, *, clinic_id, actor_id):
        raise RuntimeError("simulated failure creating the LaboratoryOrder child record")

    monkeypatch.setattr(LaboratoryService, "create_from_order", _boom)

    # httpx's `ASGITransport` re-raises unhandled app exceptions to the
    # caller by default (`raise_app_exceptions=True`) instead of only
    # returning the clean 500 `JSONResponse` a real deployed server would
    # send - so the failure surfaces here as a raised exception, not a
    # response with `status_code == 500`.
    with pytest.raises(RuntimeError, match="simulated failure creating the LaboratoryOrder child record"):
        await client.post(
            f"/api/v1/consultations/{cid}/orders", headers=doc_headers,
            json={"order_category": "Laboratory", "items": [{"item_name": "CBC"}]},
        )

    # Simulates the automatic rollback the real `get_session()` dependency
    # performs on an unhandled exception - see module-level note above.
    await db_session.rollback()
    monkeypatch.undo()

    visit_orders = await client.get(f"/api/v1/visits/{visit_id}/orders", headers=doc_headers)
    assert visit_orders.json() == [], "the parent Order must not survive when the child creation failed"

    lab_orders = await client.get("/api/v1/laboratory/orders", headers=doc_headers, params={"visit_id": visit_id})
    assert lab_orders.json() == []


async def test_non_laboratory_order_categories_remain_atomic_on_unrelated_failure(
    client: AsyncClient, make_clinic_with_owner, db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The transaction-boundary fix isn't Laboratory-specific: forcing a
    failure in a step every category goes through (the timeline event,
    written before the Laboratory/Vaccination branch even runs) must roll
    back a Radiology order just as completely as a Laboratory one - no
    special-casing by category."""
    _clinic, _owner_headers, doc_headers, _deps, visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)

    from app.repositories.visit_repository import VisitRepository

    async def _boom(self, **kwargs):
        raise RuntimeError("simulated failure recording the timeline event")

    monkeypatch.setattr(VisitRepository, "add_timeline_event", _boom)

    # See the note in `test_forced_failure_in_laboratory_child_creation_rolls_back_parent_order`
    # on why this surfaces as a raised exception rather than a 500 response.
    with pytest.raises(RuntimeError, match="simulated failure recording the timeline event"):
        await client.post(
            f"/api/v1/consultations/{cid}/orders", headers=doc_headers,
            json={"order_category": "Radiology", "items": [{"item_name": "Chest X-Ray"}]},
        )

    await db_session.rollback()
    monkeypatch.undo()

    visit_orders = await client.get(f"/api/v1/visits/{visit_id}/orders", headers=doc_headers)
    assert visit_orders.json() == [], "a non-Laboratory order must roll back completely too, not just the Order row"


async def test_sync_queue_payload_failure_does_not_turn_success_into_500(
    client: AsyncClient, make_clinic_with_owner, db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`sync_queue_service.enqueue_lazy()`'s whole point: a payload-
    construction failure (e.g. `build_sync_payload()` raising) must never
    turn an already-committed, fully successful order creation into a 500
    - the create already committed before this step even runs."""
    _clinic, _owner_headers, doc_headers, _deps, visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)

    from app.services import laboratory_service

    def _boom(lab_order):
        raise RuntimeError("simulated sync-payload serialization failure")

    monkeypatch.setattr(laboratory_service, "build_sync_payload", _boom)

    resp = await client.post(
        f"/api/v1/consultations/{cid}/orders", headers=doc_headers,
        json={"order_category": "Laboratory", "items": [{"item_name": "CBC"}]},
    )
    assert resp.status_code == 200, resp.text
    order = resp.json()

    lab_orders = await client.get("/api/v1/laboratory/orders", headers=doc_headers, params={"visit_id": visit_id})
    assert any(lo["order_id"] == order["id"] for lo in lab_orders.json()), (
        "the LaboratoryOrder must still exist - only the best-effort sync-queue enqueue failed"
    )


async def test_order_number_counter_concurrent_first_of_day_creation_is_race_safe(
    engine, make_clinic_with_owner
) -> None:
    """Regression test for the shared daily counter's first-of-day race
    (BUG-013's own writeup explicitly flagged this shared Order/
    Prescription counter as left unfixed: "the shared Phase 9 counter
    implementation itself (also used by Orders/Prescriptions) was not
    touched"). Fires N genuinely concurrent `OrderNumberGenerator
    .next_number()` calls - each its own independent AsyncSession/
    connection/transaction via `asyncio.gather` - for a brand-new clinic
    with no counter row yet for today. All must succeed with distinct,
    gap-free numbers; none may surface a raw IntegrityError/500."""
    clinic, _owner, _password = await make_clinic_with_owner()
    clinic_id = clinic.id

    from app.services.clinical_number_generator import OrderNumberGenerator

    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    async def _issue_one() -> str:
        async with session_maker() as session:
            number = await OrderNumberGenerator(session).next_number(clinic_id)
            await session.commit()
            return number

    results = await asyncio.gather(*(_issue_one() for _ in range(20)))
    assert len(results) == len(set(results)) == 20, f"expected 20 unique order numbers, got: {results}"
    assert sorted(results) == [f"ORD-{results[0].split('-')[1]}-{str(i).zfill(6)}" for i in range(1, 21)]


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
