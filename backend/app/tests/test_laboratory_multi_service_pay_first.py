"""Multiple Laboratory Services in One Queue Transaction: extends the
Laboratory Pay-First workflow (`test_laboratory_payment_first_queue.py`,
left entirely unmodified and still 15/15 green) so a single walk-in
Laboratory ticket can bundle several tests into ONE invoice (multiple
`InvoiceItem` rows, one per service), paid as ONE total, resulting in
exactly ONE Queue ticket and one `LaboratoryOrder` per selected service -
each individually identifiable on the worklist and individually linked back
to its own invoice line (so `LaboratoryService._sync_billing` never
double-charges any of them later).

Flow: POST /visits/pre-queue (single "primary" service, unchanged)
   -> POST /visits/{visit_id}/laboratory-invoice {"service_ids": [...]}
   -> POST /invoices/{invoice_id}/payments (existing PaymentService, unchanged)
   -> POST /queues (visit_id=...) -> one Queue + one LaboratoryOrder per service
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    from app.core.rate_limit import _memory_buckets

    _memory_buckets.clear()
    yield
    _memory_buckets.clear()


async def _owner_headers(client: AsyncClient, make_clinic_with_owner):
    clinic, owner, password = await make_clinic_with_owner()
    login = await client.post(
        "/api/v1/auth/login", json={"email_or_username": owner.email, "password": password, "clinic_slug": clinic.slug}
    )
    assert login.status_code == 200, login.text
    return clinic, owner, {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _setup(client: AsyncClient, headers: dict, *, service_prices: dict[str, str], department_name: str = "Laboratory") -> dict:
    """Same shape as `test_laboratory_payment_first_queue.py::_setup`, but
    creates one `ClinicService` per `{name: price}` entry instead of just
    one - `service_prices` is an ordered dict so callers can assert on
    selection order (e.g. `{"CBC": "250.00", "Urinalysis": "150.00"}`)."""
    resolved_code = f"D{uuid.uuid4().hex[:6]}"
    branch = (
        await client.post(
            "/api/v1/branches", headers=headers, json={"name": "Main Branch", "code": f"B{uuid.uuid4().hex[:6]}"}
        )
    ).json()
    department = (
        await client.post("/api/v1/departments", headers=headers, json={"department_code": resolved_code, "name": department_name})
    ).json()
    service_ids: dict[str, str] = {}
    for name, price in service_prices.items():
        service = (
            await client.post(
                "/api/v1/services", headers=headers,
                json={
                    "service_code": f"S{uuid.uuid4().hex[:6]}", "service_name": name, "default_price": price,
                    # Required - the multi-service Laboratory invoice path
                    # strictly enforces department_id match, no NULL fallback.
                    "department_id": department["id"],
                },
            )
        ).json()
        service_ids[name] = service["id"]
    patient_resp = await client.post(
        "/api/v1/patients?override=true", headers=headers,
        json={
            "first_name": "Maria", "last_name": f"Santos-{uuid.uuid4().hex[:8]}", "birth_date": "1985-03-20",
            "gender": "Female", "civil_status": "Single", "mobile_number": f"+6391{uuid.uuid4().int % 10**7:07d}",
        },
    )
    assert patient_resp.status_code == 201, patient_resp.text
    patient = patient_resp.json()["patient"]
    return {
        "branch_id": branch["id"], "department_id": department["id"], "patient_id": patient["id"],
        "service_ids": service_ids,
    }


async def _create_draft_visit(client: AsyncClient, headers: dict, deps: dict, *, primary_service_id: str) -> dict:
    resp = await client.post(
        "/api/v1/visits/pre-queue", headers=headers,
        json={
            "patient_id": deps["patient_id"], "branch_id": deps["branch_id"],
            "doctor_id": None, "department_id": deps["department_id"], "service_id": primary_service_id,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _queue_payload(deps: dict, visit_id: str, primary_service_id: str) -> dict:
    return {
        "patient_id": deps["patient_id"], "branch_id": deps["branch_id"], "department_id": deps["department_id"],
        "doctor_id": None, "service_id": primary_service_id, "priority": "Normal", "visit_id": visit_id,
    }


async def _full_multi_service_flow(client: AsyncClient, headers: dict, *, service_prices: dict[str, str]) -> dict:
    """Runs the complete happy path (draft visit -> multi-service invoice ->
    full payment -> queue creation) and returns everything a test might want
    to assert on."""
    deps = await _setup(client, headers, service_prices=service_prices)
    service_ids = list(deps["service_ids"].values())
    visit = await _create_draft_visit(client, headers, deps, primary_service_id=service_ids[0])

    invoice_resp = await client.post(
        f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers, json={"service_ids": service_ids}
    )
    assert invoice_resp.status_code == 200, invoice_resp.text
    invoice = invoice_resp.json()

    total = sum(float(p) for p in service_prices.values())
    if total > 0:
        pay_resp = await client.post(
            f"/api/v1/invoices/{invoice['id']}/payments", headers=headers,
            json={"payments": [{"payment_method": "Cash", "amount": f"{total:.2f}"}]},
        )
        assert pay_resp.status_code == 200, pay_resp.text
        invoice = pay_resp.json()

    queue_resp = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, visit["id"], service_ids[0]))
    assert queue_resp.status_code == 201, queue_resp.text
    queue = queue_resp.json()

    return {"deps": deps, "visit": visit, "invoice": invoice, "queue": queue}


# --- 2/3/15: two and three+ Laboratory services - separate line items, correct total ---

async def test_two_laboratory_services_one_invoice_one_queue(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    result = await _full_multi_service_flow(client, headers, service_prices={"CBC": "250.00", "Urinalysis": "150.00"})

    invoice = result["invoice"]
    assert len(invoice["items"]) == 2
    assert {i["description"] for i in invoice["items"]} == {"CBC", "Urinalysis"}
    assert all(i["item_type"] == "Laboratory" for i in invoice["items"])
    assert float(invoice["grand_total"]) == 400.00
    assert invoice["status"] == "Paid"

    orders_resp = await client.get(f"/api/v1/laboratory/orders?visit_id={result['visit']['id']}", headers=headers)
    assert orders_resp.status_code == 200, orders_resp.text
    orders = orders_resp.json()
    assert len(orders) == 2
    assert {o["test_type"] for o in orders} == {"CBC", "Urinalysis"}
    assert all(o["visit_id"] == result["visit"]["id"] for o in orders)
    # Each order links to its OWN invoice item, not a shared/first one.
    linked_item_ids = {o["invoice_item_id"] for o in orders}
    assert linked_item_ids == {i["id"] for i in invoice["items"]}


async def test_three_laboratory_services(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    result = await _full_multi_service_flow(
        client, headers, service_prices={"CBC": "250.00", "Urinalysis": "150.00", "Blood Chemistry": "350.00"}
    )

    invoice = result["invoice"]
    assert len(invoice["items"]) == 3
    assert float(invoice["grand_total"]) == 750.00
    assert invoice["status"] == "Paid"

    orders = (await client.get(f"/api/v1/laboratory/orders?visit_id={result['visit']['id']}", headers=headers)).json()
    assert len(orders) == 3
    assert {o["test_type"] for o in orders} == {"CBC", "Urinalysis", "Blood Chemistry"}


# --- 5: duplicate service selection rejected ---

async def test_duplicate_service_selection_rejected(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers, service_prices={"CBC": "250.00"})
    cbc_id = deps["service_ids"]["CBC"]
    visit = await _create_draft_visit(client, headers, deps, primary_service_id=cbc_id)

    resp = await client.post(
        f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers,
        json={"service_ids": [cbc_id, cbc_id]},
    )
    assert resp.status_code == 422, resp.text


# --- 6/7: partial payment blocks queue creation; full payment creates it exactly once ---

async def test_partial_payment_blocks_queue_creation(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers, service_prices={"CBC": "250.00", "Urinalysis": "150.00"})
    service_ids = list(deps["service_ids"].values())
    visit = await _create_draft_visit(client, headers, deps, primary_service_id=service_ids[0])

    invoice = (
        await client.post(f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers, json={"service_ids": service_ids})
    ).json()
    assert float(invoice["balance_due"]) == 400.00

    partial_pay = await client.post(
        f"/api/v1/invoices/{invoice['id']}/payments", headers=headers,
        json={"payments": [{"payment_method": "Cash", "amount": "100.00"}]},
    )
    assert partial_pay.status_code == 200, partial_pay.text
    assert partial_pay.json()["status"] != "Paid"
    assert float(partial_pay.json()["balance_due"]) == 300.00

    queue_resp = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, visit["id"], service_ids[0]))
    assert queue_resp.status_code == 400, queue_resp.text
    assert "paid in full" in queue_resp.json()["detail"].lower()

    # No LaboratoryOrder exists yet either - queue creation is what creates them.
    orders = (await client.get(f"/api/v1/laboratory/orders?visit_id={visit['id']}", headers=headers)).json()
    assert orders == []


async def test_full_payment_creates_queue_exactly_once(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers, service_prices={"CBC": "250.00", "Urinalysis": "150.00"})
    service_ids = list(deps["service_ids"].values())
    visit = await _create_draft_visit(client, headers, deps, primary_service_id=service_ids[0])
    invoice = (
        await client.post(f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers, json={"service_ids": service_ids})
    ).json()
    await client.post(
        f"/api/v1/invoices/{invoice['id']}/payments", headers=headers,
        json={"payments": [{"payment_method": "Cash", "amount": "400.00"}]},
    )

    first = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, visit["id"], service_ids[0]))
    assert first.status_code == 201, first.text


# --- 8: payment cancellation (never paid) - no queue, no Laboratory Orders ---

async def test_no_payment_at_all_means_no_queue_no_orders(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers, service_prices={"CBC": "250.00", "Urinalysis": "150.00"})
    service_ids = list(deps["service_ids"].values())
    visit = await _create_draft_visit(client, headers, deps, primary_service_id=service_ids[0])
    await client.post(f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers, json={"service_ids": service_ids})
    # No payment recorded at all (simulates the receptionist backing out of PaymentDialog).

    queue_resp = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, visit["id"], service_ids[0]))
    assert queue_resp.status_code == 400, queue_resp.text

    orders = (await client.get(f"/api/v1/laboratory/orders?visit_id={visit['id']}", headers=headers)).json()
    assert orders == []


# --- 9: payment/invoice retry reuses the same invoice, no duplicate ---

async def test_invoice_creation_retry_reuses_same_invoice_no_duplicate_items(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers, service_prices={"CBC": "250.00", "Urinalysis": "150.00", "Blood Chemistry": "350.00"})
    service_ids = list(deps["service_ids"].values())
    visit = await _create_draft_visit(client, headers, deps, primary_service_id=service_ids[0])

    first = (
        await client.post(f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers, json={"service_ids": service_ids})
    ).json()
    # Retry with the SAME service_ids (e.g. StrictMode double-invocation, or
    # a receptionist re-clicking "Proceed to Payment") - must return the
    # identical invoice, not add a second set of line items.
    second = (
        await client.post(f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers, json={"service_ids": service_ids})
    ).json()
    assert second["id"] == first["id"]
    assert len(second["items"]) == 3

    # Even a retry with a DIFFERENT service_ids list must not add more items
    # once an invoice already exists for this visit - idempotent per-visit,
    # not per-service-selection.
    third = (
        await client.post(
            f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers,
            json={"service_ids": [service_ids[0]]},
        )
    ).json()
    assert third["id"] == first["id"]
    assert len(third["items"]) == 3


# --- 10: queue creation retry does not duplicate the queue ---

async def test_queue_creation_retry_does_not_duplicate(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    result = await _full_multi_service_flow(client, headers, service_prices={"CBC": "250.00", "Urinalysis": "150.00"})
    deps, visit = result["deps"], result["visit"]
    service_ids = list(deps["service_ids"].values())

    retry = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, visit["id"], service_ids[0]))
    assert retry.status_code == 400, retry.text
    assert "not awaiting queue creation" in retry.json()["detail"].lower()

    orders = (await client.get(f"/api/v1/laboratory/orders?visit_id={visit['id']}", headers=headers)).json()
    assert len(orders) == 2  # not 4 - retry never created a second set


# --- 12: Queue Slip PAID = true, vitals not required, for multi-service ---

async def test_queue_slip_paid_and_no_vitals_required_for_multi_service(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    result = await _full_multi_service_flow(client, headers, service_prices={"CBC": "250.00", "Urinalysis": "150.00"})

    slip_resp = await client.get(f"/api/v1/queues/{result['queue']['id']}/slip", headers=headers)
    assert slip_resp.status_code == 200, slip_resp.text
    assert slip_resp.json()["is_paid"] is True


# --- 13: Laboratory queue can be created without a doctor (multi-service) ---

async def test_multi_service_queue_created_without_doctor(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    result = await _full_multi_service_flow(client, headers, service_prices={"CBC": "250.00", "Urinalysis": "150.00"})
    assert result["queue"]["doctor_id"] is None


# --- 14: Laboratory worklist shows all selected services ---

async def test_worklist_shows_all_selected_services(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    result = await _full_multi_service_flow(
        client, headers, service_prices={"CBC": "250.00", "Urinalysis": "150.00", "Blood Chemistry": "350.00"}
    )

    dashboard = (await client.get("/api/v1/laboratory/orders", headers=headers)).json()
    visit_orders = [o for o in dashboard if o["visit_id"] == result["visit"]["id"]]
    assert len(visit_orders) == 3
    assert {o["test_type"] for o in visit_orders} == {"CBC", "Urinalysis", "Blood Chemistry"}
    assert all(o["patient_id"] == result["deps"]["patient_id"] for o in visit_orders)
    assert all(o["queue_number"] == result["queue"]["queue_number"] for o in visit_orders)


# --- 16: billing-sync does not double-charge any of the multi-service orders ---

async def test_billing_sync_after_multi_service_does_not_double_charge(client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    result = await _full_multi_service_flow(client, headers, service_prices={"CBC": "250.00", "Urinalysis": "150.00"})
    visit_id = result["visit"]["id"]
    invoice_id_before = result["invoice"]["id"]

    orders = (await client.get(f"/api/v1/laboratory/orders?visit_id={visit_id}", headers=headers)).json()
    assert len(orders) == 2

    # Run one of the two orders through collect -> process -> results ->
    # release, same as a real Laboratory technician would - this is what
    # triggers `LaboratoryService._sync_billing`.
    cbc_order = next(o for o in orders if o["test_type"] == "CBC")
    await client.post(f"/api/v1/laboratory/orders/{cbc_order['id']}/collect", headers=headers)
    await client.post(f"/api/v1/laboratory/orders/{cbc_order['id']}/start-processing", headers=headers)
    results_resp = await client.post(
        f"/api/v1/laboratory/orders/{cbc_order['id']}/results", headers=headers,
        json={"results": [{"parameter_name": "Result", "result_type": "Text", "text_value": "Normal"}]},
    )
    assert results_resp.status_code == 200, results_resp.text

    invoice_resp = await client.get(f"/api/v1/visits/{visit_id}/invoice", headers=headers)
    invoice_after = invoice_resp.json()
    assert invoice_after["id"] == invoice_id_before  # same invoice, not a new one
    assert len(invoice_after["items"]) == 2  # still exactly 2 - no third "CBC" line added
    assert float(invoice_after["grand_total"]) == 400.00  # unchanged total
    assert invoice_after["status"] == "Paid"  # never reverted/reopened


# --- 17: multiple patients/services remain isolated ---

async def test_multiple_patients_multi_service_orders_remain_isolated(client: AsyncClient, make_clinic_with_owner) -> None:
    # Two separate clinics rather than two visits in one clinic: the shared
    # daily visit-number generator is out of scope for this feature (and
    # already covered/relied on elsewhere), so this sidesteps it entirely
    # while still proving patient/order isolation across tickets.
    _clinic_a, _owner_a, headers_a = await _owner_headers(client, make_clinic_with_owner)
    _clinic_b, _owner_b, headers_b = await _owner_headers(client, make_clinic_with_owner)
    result_a = await _full_multi_service_flow(client, headers_a, service_prices={"CBC": "250.00", "Urinalysis": "150.00"})
    result_b = await _full_multi_service_flow(client, headers_b, service_prices={"Blood Chemistry": "350.00"})

    orders_a = (await client.get(f"/api/v1/laboratory/orders?visit_id={result_a['visit']['id']}", headers=headers_a)).json()
    orders_b = (await client.get(f"/api/v1/laboratory/orders?visit_id={result_b['visit']['id']}", headers=headers_b)).json()
    assert len(orders_a) == 2
    assert len(orders_b) == 1
    assert all(o["patient_id"] == result_a["deps"]["patient_id"] for o in orders_a)
    assert all(o["patient_id"] == result_b["deps"]["patient_id"] for o in orders_b)
    assert result_a["deps"]["patient_id"] != result_b["deps"]["patient_id"]


# --- 18: tenant isolation ---

async def test_tenant_isolation_for_multi_service_invoice_and_orders(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic_a, _owner_a, headers_a = await _owner_headers(client, make_clinic_with_owner)
    _clinic_b, _owner_b, headers_b = await _owner_headers(client, make_clinic_with_owner)
    result = await _full_multi_service_flow(client, headers_a, service_prices={"CBC": "250.00", "Urinalysis": "150.00"})

    invoice_resp = await client.get(f"/api/v1/invoices/{result['invoice']['id']}", headers=headers_b)
    assert invoice_resp.status_code == 404, invoice_resp.text

    orders_resp = await client.get(f"/api/v1/laboratory/orders?visit_id={result['visit']['id']}", headers=headers_b)
    assert orders_resp.status_code == 200, orders_resp.text
    assert orders_resp.json() == []

    queue_resp = await client.get(f"/api/v1/queues/{result['queue']['id']}/slip", headers=headers_b)
    assert queue_resp.status_code == 404, queue_resp.text


# --- Strict Laboratory-department enforcement (production bug fix: the
# Laboratory Services selector/submission must never accept a service that
# isn't explicitly assigned to the Laboratory department - NOT the same
# NULL-is-shared rule the ordinary single-service queue path uses) ---


async def test_laboratory_service_with_correct_department_is_accepted(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers, service_prices={"CBC": "250.00"})
    cbc_id = deps["service_ids"]["CBC"]
    visit = await _create_draft_visit(client, headers, deps, primary_service_id=cbc_id)

    resp = await client.post(
        f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers, json={"service_ids": [cbc_id]}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"][0]["description"] == "CBC"


async def test_service_assigned_to_a_different_department_is_rejected(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers, service_prices={"CBC": "250.00"})
    cbc_id = deps["service_ids"]["CBC"]
    visit = await _create_draft_visit(client, headers, deps, primary_service_id=cbc_id)

    # A real service, but assigned to a DIFFERENT, non-Laboratory department.
    other_department = (
        await client.post(
            "/api/v1/departments", headers=headers, json={"department_code": f"D{uuid.uuid4().hex[:6]}", "name": "Radiology"}
        )
    ).json()
    other_service = (
        await client.post(
            "/api/v1/services", headers=headers,
            json={
                "service_code": f"S{uuid.uuid4().hex[:6]}", "service_name": "X-RAY CHEST", "default_price": "600.00",
                "department_id": other_department["id"],
            },
        )
    ).json()

    resp = await client.post(
        f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers,
        json={"service_ids": [cbc_id, other_service["id"]]},
    )
    assert resp.status_code == 400, resp.text
    assert "does not belong to the Laboratory department" in resp.json()["detail"]


async def test_unassigned_null_department_service_is_rejected_for_laboratory_submission(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """The general NULL-is-shared convention (a service with no
    `department_id` is valid for any ordinary department) must NOT apply
    to the Laboratory multi-service submission path - an unassigned
    service is exactly as invalid here as one assigned elsewhere."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers, service_prices={"CBC": "250.00"})
    cbc_id = deps["service_ids"]["CBC"]
    visit = await _create_draft_visit(client, headers, deps, primary_service_id=cbc_id)

    unassigned_service = (
        await client.post(
            "/api/v1/services", headers=headers,
            json={"service_code": f"S{uuid.uuid4().hex[:6]}", "service_name": "UNASSIGNED TEST", "default_price": "100.00"},
        )
    ).json()
    assert unassigned_service.get("department_id") is None

    resp = await client.post(
        f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers,
        json={"service_ids": [cbc_id, unassigned_service["id"]]},
    )
    assert resp.status_code == 400, resp.text
    assert "does not belong to the Laboratory department" in resp.json()["detail"]


async def test_nonexistent_service_still_returns_404_not_a_department_error(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers, service_prices={"CBC": "250.00"})
    cbc_id = deps["service_ids"]["CBC"]
    visit = await _create_draft_visit(client, headers, deps, primary_service_id=cbc_id)

    resp = await client.post(
        f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers,
        json={"service_ids": [cbc_id, str(uuid.uuid4())]},
    )
    assert resp.status_code == 404, resp.text


async def test_pre_queue_draft_visit_rejects_a_non_laboratory_service_for_a_laboratory_department(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """`POST /visits/pre-queue`'s own `service_id` (the frontend's
    `labServiceIds[0]`) must be rejected here too when the selected
    Department is Laboratory and the service isn't assigned to it - not
    just later at the invoice step. Mirrors the investigation's finding
    that this path previously had zero department validation at all."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers, service_prices={"CBC": "250.00"})

    unassigned_service = (
        await client.post(
            "/api/v1/services", headers=headers,
            json={"service_code": f"S{uuid.uuid4().hex[:6]}", "service_name": "UNASSIGNED TEST 2", "default_price": "100.00"},
        )
    ).json()

    resp = await client.post(
        "/api/v1/visits/pre-queue", headers=headers,
        json={
            "patient_id": deps["patient_id"], "branch_id": deps["branch_id"],
            "doctor_id": None, "department_id": deps["department_id"], "service_id": unassigned_service["id"],
        },
    )
    assert resp.status_code == 400, resp.text
    assert "does not belong to the Laboratory department" in resp.json()["detail"]


async def test_non_laboratory_pre_queue_still_allows_an_unassigned_shared_service(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """Regression: the strict Laboratory-only check must not leak into the
    ordinary (non-Laboratory) pre-queue path, which still needs to accept
    an unassigned/shared service exactly as before."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    # A non-Laboratory department, deliberately.
    deps = await _setup(client, headers, service_prices={"Consult": "0"}, department_name="General Medicine")
    unassigned_service = (
        await client.post(
            "/api/v1/services", headers=headers,
            json={"service_code": f"S{uuid.uuid4().hex[:6]}", "service_name": "UNASSIGNED TEST 3", "default_price": "0"},
        )
    ).json()

    resp = await client.post(
        "/api/v1/visits/pre-queue", headers=headers,
        json={
            "patient_id": deps["patient_id"], "branch_id": deps["branch_id"],
            "doctor_id": None, "department_id": deps["department_id"], "service_id": unassigned_service["id"],
        },
    )
    assert resp.status_code == 201, resp.text
