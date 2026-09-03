"""Laboratory pay-first workflow: a Laboratory queue ticket must not be
created/activated until its invoice is paid in full.

Flow: POST /visits/pre-queue (draft visit, no queue yet)
   -> POST /visits/{visit_id}/laboratory-invoice (idempotent invoice create)
   -> POST /invoices/{invoice_id}/payments (existing PaymentService)
   -> POST /queues (visit_id=... - QueueService._create_queue_for_paid_lab_visit)

See `QueueService.create_queue`'s `_is_laboratory_department` branch for the
backend enforcement point (a direct API call with no prior payment is
rejected there, not merely hidden behind a disabled frontend button), and
`InvoiceService.create_draft_invoice_for_laboratory_visit` for the invoice
side. `test_walk_in_laboratory_queue.py` covers the lab-order-auto-creation/
template-matching behavior itself, routed through this same real workflow;
this file covers the payment gate, PAID queue slip, doctor optionality, and
idempotency."""

import asyncio
import uuid

import pytest
from httpx import AsyncClient
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


async def _enter_vitals(client: AsyncClient, headers: dict, visit_id: str) -> None:
    """Pre-existing, unrelated requirement (Reception Queue Workflow
    Improvements): `QueueService.get_slip` rejects printing ANY non-
    Laboratory ticket until its visit has vitals recorded - Laboratory
    tickets are the only department exempted. Needed here purely as test
    setup for the non-Laboratory regression/slip tests below, not something
    this feature changes."""
    consultation = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open-for-reception", headers=headers)).json()
    resp = await client.put(
        f"/api/v1/consultations/{consultation['id']}/soap/subjective-objective", headers=headers,
        json={
            "blood_pressure": "120/80", "pulse_rate": 72, "respiratory_rate": 18,
            "temperature": 36.8, "height_cm": 170, "weight_kg": 65, "oxygen_saturation": 98,
        },
    )
    assert resp.status_code == 200, resp.text


async def _setup(
    client: AsyncClient, headers: dict, *, department_name: str = "Laboratory",
    department_code: str | None = None, price: str = "250.00",
) -> dict:
    # Defaults to the seeded "LAB" code for a Laboratory-named department -
    # historically `QueueService.get_slip`'s vitals-exemption check keyed
    # off `department_code == "LAB"` specifically, which was a latent bug
    # (a clinic with its own custom-coded Laboratory department was not
    # exempted - see `test_lab_payment_first_queue_slip_with_custom_department_code`
    # below, which uses a non-"LAB" code deliberately). `get_slip` now
    # shares the same NAME-based `_is_laboratory_department` convention
    # `_is_laboratory_department`/lab-order-auto-creation already used, so
    # the department code no longer matters for either path - kept
    # defaulting to "LAB" here only to match a real seeded clinic's data,
    # not because it's required for correctness anymore.
    resolved_code = department_code or ("LAB" if department_name == "Laboratory" else f"D{uuid.uuid4().hex[:4]}")
    branch = (await client.post("/api/v1/branches", headers=headers, json={"name": "Main Branch", "code": "MAIN"})).json()
    department = (
        await client.post(
            "/api/v1/departments", headers=headers,
            json={"department_code": resolved_code, "name": department_name},
        )
    ).json()
    service = (
        await client.post(
            "/api/v1/services", headers=headers,
            json={"service_code": f"S{uuid.uuid4().hex[:6]}", "service_name": "BLOOD CHEMISTRY", "default_price": price},
        )
    ).json()
    patient = (
        await client.post(
            "/api/v1/patients", headers=headers,
            json={
                "first_name": "Maria", "last_name": "Santos", "birth_date": "1985-03-20",
                "gender": "Female", "civil_status": "Single", "mobile_number": f"+6391{uuid.uuid4().int % 10**7:07d}",
            },
        )
    ).json()["patient"]
    return {"branch_id": branch["id"], "department_id": department["id"], "service_id": service["id"], "patient_id": patient["id"]}


async def _create_draft_visit(client: AsyncClient, headers: dict, deps: dict, *, doctor_id: str | None = None) -> dict:
    resp = await client.post(
        "/api/v1/visits/pre-queue", headers=headers,
        json={
            "patient_id": deps["patient_id"], "branch_id": deps["branch_id"],
            "doctor_id": doctor_id, "department_id": deps["department_id"], "service_id": deps["service_id"],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _queue_payload(deps: dict, visit_id: str, *, doctor_id: str | None = None) -> dict:
    return {
        "patient_id": deps["patient_id"], "branch_id": deps["branch_id"], "department_id": deps["department_id"],
        "doctor_id": doctor_id, "service_id": deps["service_id"], "priority": "Normal", "visit_id": visit_id,
    }


# --- 1 & 3: happy path - payment first, then queue creation; slip shows PAID ---

async def test_lab_payment_first_happy_path_and_paid_queue_slip(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers)
    visit = await _create_draft_visit(client, headers, deps)

    invoice_resp = await client.post(f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers)
    assert invoice_resp.status_code == 200, invoice_resp.text
    invoice = invoice_resp.json()
    assert invoice["status"] == "PendingPayment"
    assert float(invoice["balance_due"]) == 250.00
    assert invoice["items"][0]["item_type"] == "Laboratory"
    assert invoice["items"][0]["description"] == "BLOOD CHEMISTRY"

    pay_resp = await client.post(
        f"/api/v1/invoices/{invoice['id']}/payments", headers=headers,
        json={"payments": [{"payment_method": "Cash", "amount": "250.00"}]},
    )
    assert pay_resp.status_code == 200, pay_resp.text
    assert pay_resp.json()["status"] == "Paid"

    queue_resp = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, visit["id"]))
    assert queue_resp.status_code == 201, queue_resp.text
    queue = queue_resp.json()
    assert queue["status"] == "Waiting"
    assert queue["visit_id"] == visit["id"]

    slip_resp = await client.get(f"/api/v1/queues/{queue['id']}/slip", headers=headers)
    assert slip_resp.status_code == 200, slip_resp.text
    slip = slip_resp.json()
    assert slip["is_paid"] is True


async def test_lab_payment_first_queue_slip_with_custom_department_code(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """Regression: `get_slip`'s Laboratory vitals-exemption used to check
    `department.department_code == "LAB"` directly - which only matches the
    *seeded* default Laboratory department. A clinic that creates its own
    Laboratory department manually (a real, observed case - e.g. one live
    clinic's Laboratory department has code "D03") was NOT exempted, so a
    freshly-created Laboratory Pay-First queue ticket (genuinely no
    vitals - Laboratory has no consultation/SOAP note) would 400 with
    "Vital signs must be taken before printing the queue ticket." on its
    very first print, right after payment succeeded. `get_slip` now shares
    the same NAME-based `_is_laboratory_department` helper queue creation's
    payment gate already used, so this must succeed regardless of the
    department's code - proven here with a deliberately non-"LAB" code."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers, department_code="D03")
    visit = await _create_draft_visit(client, headers, deps)

    invoice = (await client.post(f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers)).json()
    pay_resp = await client.post(
        f"/api/v1/invoices/{invoice['id']}/payments", headers=headers,
        json={"payments": [{"payment_method": "Cash", "amount": "250.00"}]},
    )
    assert pay_resp.status_code == 200, pay_resp.text

    queue = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, visit["id"]))).json()

    slip_resp = await client.get(f"/api/v1/queues/{queue['id']}/slip", headers=headers)
    assert slip_resp.status_code == 200, slip_resp.text
    slip = slip_resp.json()
    assert slip["is_paid"] is True
    # No vitals were ever recorded for this Laboratory visit - `vitals_taken`
    # correctly stays False (it means "complete", not "printable"); only the
    # print-blocking 400 is what the Laboratory exemption removes.
    assert slip["vitals_taken"] is False

    # Queue viewing (the list endpoint) must also not choke on this ticket -
    # same batched vitals-completeness computation `get_slip` mirrors.
    list_resp = await client.get("/api/v1/queues", headers=headers)
    assert list_resp.status_code == 200, list_resp.text
    listed = next(q for q in list_resp.json()["items"] if q["id"] == queue["id"])
    assert listed["vitals_taken"] is False


# --- 2: unpaid path rejected, no queue created ---

async def test_lab_queue_creation_rejected_when_invoice_unpaid(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers)
    visit = await _create_draft_visit(client, headers, deps)

    invoice_resp = await client.post(f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers)
    assert invoice_resp.status_code == 200, invoice_resp.text
    assert invoice_resp.json()["status"] == "PendingPayment"

    queue_resp = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, visit["id"]))
    assert queue_resp.status_code == 400, queue_resp.text
    assert "paid in full" in queue_resp.json()["detail"]

    worklist = await client.get(
        f"/api/v1/queues?department_id={deps['department_id']}&status=Waiting", headers=headers
    )
    assert worklist.status_code == 200, worklist.text
    assert worklist.json()["total"] == 0


async def test_lab_queue_creation_rejected_with_no_prior_invoice_at_all(client: AsyncClient, make_clinic_with_owner) -> None:
    """A direct API call skipping the invoice-creation step entirely (not
    just skipping payment) must also be rejected - the enforcement point
    checks for a genuinely Paid invoice, not merely "an invoice exists"."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers)
    visit = await _create_draft_visit(client, headers, deps)

    queue_resp = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, visit["id"]))
    assert queue_resp.status_code == 400, queue_resp.text
    assert "paid in full" in queue_resp.json()["detail"]


async def test_lab_queue_creation_rejected_with_no_visit_id_at_all(client: AsyncClient, make_clinic_with_owner) -> None:
    """Bypassing the draft-visit step entirely (the old direct-creation
    shape) is rejected up front with a clear message, not a generic 404/500."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers)

    queue_resp = await client.post(
        "/api/v1/queues", headers=headers,
        json={
            "patient_id": deps["patient_id"], "branch_id": deps["branch_id"], "department_id": deps["department_id"],
            "doctor_id": None, "service_id": deps["service_id"], "priority": "Normal",
        },
    )
    assert queue_resp.status_code == 400, queue_resp.text
    assert "payment first" in queue_resp.json()["detail"]


async def test_lab_queue_creation_rejected_when_only_partially_paid(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers)
    visit = await _create_draft_visit(client, headers, deps)
    invoice = (await client.post(f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers)).json()

    pay_resp = await client.post(
        f"/api/v1/invoices/{invoice['id']}/payments", headers=headers,
        json={"payments": [{"payment_method": "Cash", "amount": "100.00"}]},
    )
    assert pay_resp.status_code == 200, pay_resp.text
    assert pay_resp.json()["status"] == "PartiallyPaid"

    queue_resp = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, visit["id"]))
    assert queue_resp.status_code == 400, queue_resp.text
    assert "paid in full" in queue_resp.json()["detail"]


# --- 4: doctor rule - Laboratory queue can be created with no doctor ---

async def test_lab_queue_creation_succeeds_with_no_doctor(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers)
    visit = await _create_draft_visit(client, headers, deps, doctor_id=None)
    assert visit["doctor_id"] is None

    invoice = (await client.post(f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers)).json()
    await client.post(
        f"/api/v1/invoices/{invoice['id']}/payments", headers=headers,
        json={"payments": [{"payment_method": "Cash", "amount": invoice["balance_due"]}]},
    )

    queue_resp = await client.post(
        "/api/v1/queues", headers=headers, json=_queue_payload(deps, visit["id"], doctor_id=None)
    )
    assert queue_resp.status_code == 201, queue_resp.text
    assert queue_resp.json()["doctor_id"] is None


# --- 5: non-Laboratory regression - unchanged doctor-assignment behavior ---

async def test_non_laboratory_department_queue_unaffected_by_payment_gate(client: AsyncClient, make_clinic_with_owner) -> None:
    """A Consultation-style ticket for a non-Laboratory department still
    creates immediately via the direct, no-invoice-required path - it never
    touches the Laboratory payment gate at all."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers, department_name="Internal Medicine")
    doctor = (await client.post("/api/v1/doctors", headers=headers, json={"first_name": "Ana", "last_name": "Reyes"})).json()

    queue_resp = await client.post(
        "/api/v1/queues", headers=headers,
        json={
            "patient_id": deps["patient_id"], "branch_id": deps["branch_id"], "department_id": deps["department_id"],
            "doctor_id": doctor["id"], "service_id": deps["service_id"], "priority": "Normal",
        },
    )
    assert queue_resp.status_code == 201, queue_resp.text
    queue = queue_resp.json()
    assert queue["status"] == "Waiting"
    assert queue["doctor_id"] == doctor["id"]

    await _enter_vitals(client, headers, queue["visit_id"])
    slip_resp = await client.get(f"/api/v1/queues/{queue['id']}/slip", headers=headers)
    assert slip_resp.status_code == 200, slip_resp.text
    # Regression (item 8): no invoice was ever created for this ticket, so
    # the slip must never print a false PAID line.
    assert slip_resp.json()["is_paid"] is False


# --- 6: idempotency - retrying invoice creation / payment / queue creation ---

async def test_retrying_invoice_creation_does_not_duplicate_invoice(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers)
    visit = await _create_draft_visit(client, headers, deps)

    first = await client.post(f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers)
    second = await client.post(f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

    invoices = await client.get(f"/api/v1/visits/{visit['id']}/invoice", headers=headers)
    assert invoices.status_code == 200, invoices.text
    assert invoices.json()["id"] == first.json()["id"]


async def test_truly_concurrent_invoice_creation_does_not_500_or_duplicate(
    client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession, engine
) -> None:
    """Regression: `create_draft_invoice_for_laboratory_visit`'s existence
    check (`get_latest_for_visit`) is a plain SELECT with no row lock, so
    two REAL simultaneous requests for the same visit (e.g. React 18
    StrictMode's dev-mode double-effect-invocation in `LabPaymentStep`, a
    double-click, or two browser tabs) can both see "no invoice yet" and
    both attempt to create one. `uq_invoices_active_per_visit` (migration
    0033) then lets only one INSERT win - the loser must return that
    winner's invoice instead of surfacing a raw IntegrityError/500 (which
    can even reach the browser as a bare, message-less CORS/network
    failure).

    The `client`/`db_session` fixtures share a single `AsyncSession` across
    every request in a test (see conftest's `_override_get_db`), and
    `AsyncSession` itself forbids concurrent use ("Session is already
    flushing") - so firing two requests through `client` with
    `asyncio.gather` never reaches the DB concurrently at all, it just
    trips that guard. To actually exercise the race, this test commits the
    setup data (so it's visible across connections) and then drives
    `InvoiceService.create_draft_invoice_for_laboratory_visit` directly from
    two independent sessions/connections on the same engine.

    The test database is also built via `Base.metadata.create_all` (see
    conftest's `engine` fixture), which only creates what's declared on the
    ORM models - it does NOT run alembic migrations, so
    `uq_invoices_active_per_visit` (raw DDL in migration 0033, not mirrored
    on the `Invoice` model) doesn't exist here by default. Create it
    directly so this test actually exercises the same constraint a real
    (migrated) database enforces."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.services.invoice_service import InvoiceService

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_invoices_active_per_visit "
                "ON invoices (clinic_id, visit_id) WHERE is_deleted = false AND status != 'Cancelled'"
            )
        )

    clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers)
    visit = await _create_draft_visit(client, headers, deps)
    await db_session.commit()

    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with session_maker() as session_a, session_maker() as session_b:
        results = await asyncio.gather(
            InvoiceService(session_a).create_draft_invoice_for_laboratory_visit(
                clinic_id=clinic.id, visit_id=uuid.UUID(visit["id"]), actor_id=_owner.id,
            ),
            InvoiceService(session_b).create_draft_invoice_for_laboratory_visit(
                clinic_id=clinic.id, visit_id=uuid.UUID(visit["id"]), actor_id=_owner.id,
            ),
        )
        await session_a.commit()
        await session_b.commit()

    assert str(results[0].id) == str(results[1].id)

    invoices = await client.get(f"/api/v1/visits/{visit['id']}/invoice", headers=headers)
    assert invoices.status_code == 200, invoices.text
    assert invoices.json()["id"] == str(results[0].id)


async def test_retrying_payment_after_already_paid_does_not_double_pay(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers)
    visit = await _create_draft_visit(client, headers, deps)
    invoice = (await client.post(f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers)).json()

    first_pay = await client.post(
        f"/api/v1/invoices/{invoice['id']}/payments", headers=headers,
        json={"payments": [{"payment_method": "Cash", "amount": "250.00"}]},
    )
    assert first_pay.status_code == 200, first_pay.text
    assert first_pay.json()["status"] == "Paid"

    # A retried payment attempt (e.g. client double-submit / retry after a
    # dropped response) against an already-fully-paid invoice is rejected -
    # the existing balance-exceeded guard in `PaymentService.record_payment`
    # already prevents this, unchanged by this feature.
    retry_pay = await client.post(
        f"/api/v1/invoices/{invoice['id']}/payments", headers=headers,
        json={"payments": [{"payment_method": "Cash", "amount": "250.00"}]},
    )
    assert retry_pay.status_code == 400, retry_pay.text

    final = await client.get(f"/api/v1/invoices/{invoice['id']}", headers=headers)
    assert final.json()["amount_paid"] == "250.00"
    assert len(final.json()["payments"]) == 1


async def test_retrying_queue_creation_does_not_duplicate_queue_or_lab_order(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers)
    visit = await _create_draft_visit(client, headers, deps)
    invoice = (await client.post(f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers)).json()
    await client.post(
        f"/api/v1/invoices/{invoice['id']}/payments", headers=headers,
        json={"payments": [{"payment_method": "Cash", "amount": invoice["balance_due"]}]},
    )

    first = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, visit["id"]))
    assert first.status_code == 201, first.text

    # Retrying with the SAME (now already-queued) draft visit is rejected by
    # `_create_queue_for_paid_lab_visit`'s own DRAFT_VITALS-status check
    # before it ever reaches the duplicate-active-ticket guard - the visit
    # was already transitioned to Waiting by the first call, so it is no
    # longer "awaiting queue creation". Either way, no second queue ticket
    # or LaboratoryOrder is created.
    retry = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, visit["id"]))
    assert retry.status_code == 400, retry.text
    assert "not awaiting queue creation" in retry.json()["detail"]

    orders_resp = await client.get(f"/api/v1/laboratory/orders?visit_id={visit['id']}", headers=headers)
    assert len(orders_resp.json()) == 1


async def test_lab_order_billing_sync_does_not_double_charge_after_pay_first(
    client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession
) -> None:
    """Idempotency across the *existing* Laboratory result workflow: once
    results are entered (unchanged - `LaboratoryService.enter_results` ->
    `_sync_billing`), the already-paid invoice must not gain a SECOND
    Laboratory line item for the same test - `_create_queue_for_paid_lab_visit`
    pre-links `invoice_item_id` specifically to prevent this."""
    from sqlalchemy import select

    from app.models.laboratory_order import LaboratoryOrder
    from app.models.laboratory_template import LaboratoryTemplate, LaboratoryTemplateParameter

    clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers)
    visit = await _create_draft_visit(client, headers, deps)
    invoice = (await client.post(f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers)).json()
    await client.post(
        f"/api/v1/invoices/{invoice['id']}/payments", headers=headers,
        json={"payments": [{"payment_method": "Cash", "amount": invoice["balance_due"]}]},
    )
    queue = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, visit["id"]))).json()

    # Link a priced template to the auto-created lab order so `_sync_billing`
    # actually has something to sync (it no-ops without a template_id).
    template = LaboratoryTemplate(
        clinic_id=clinic.id, test_name="BLOOD CHEMISTRY", test_category="Chemistry",
        specimen_type="Blood", default_price="250.00", is_active=True,
    )
    db_session.add(template)
    await db_session.flush()
    db_session.add(LaboratoryTemplateParameter(
        clinic_id=clinic.id, template_id=template.id, parameter_name="Glucose",
        unit="mg/dL", result_type="Numeric", display_order=1,
    ))
    await db_session.commit()

    lab_order_row = (
        await db_session.execute(select(LaboratoryOrder).where(LaboratoryOrder.visit_id == uuid.UUID(visit["id"])))
    ).scalar_one()
    lab_order_row.template_id = template.id
    await db_session.commit()

    order_id = str(lab_order_row.id)
    await client.post(f"/api/v1/laboratory/orders/{order_id}/collect", headers=headers)
    await client.post(f"/api/v1/laboratory/orders/{order_id}/start-processing", headers=headers)
    results_resp = await client.post(
        f"/api/v1/laboratory/orders/{order_id}/results", headers=headers,
        json={"results": [{"parameter_name": "Glucose", "result_type": "Numeric", "numeric_value": "95"}]},
    )
    assert results_resp.status_code == 200, results_resp.text

    final_invoice = await client.get(f"/api/v1/visits/{visit['id']}/invoice", headers=headers)
    assert final_invoice.status_code == 200, final_invoice.text
    lab_items = [i for i in final_invoice.json()["items"] if i["item_type"] == "Laboratory"]
    assert len(lab_items) == 1, "must update the existing paid line item, not add a second one"


# --- 7: existing Laboratory lifecycle unchanged after the new gate ---

async def test_lab_order_lifecycle_unchanged_after_payment_gate(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers)
    visit = await _create_draft_visit(client, headers, deps)
    invoice = (await client.post(f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers)).json()
    await client.post(
        f"/api/v1/invoices/{invoice['id']}/payments", headers=headers,
        json={"payments": [{"payment_method": "Cash", "amount": invoice["balance_due"]}]},
    )
    queue = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, visit["id"]))).json()

    orders = (await client.get(f"/api/v1/laboratory/orders?visit_id={visit['id']}", headers=headers)).json()
    order_id = orders[0]["order_id"] or orders[0]["id"]

    collect = await client.post(f"/api/v1/laboratory/orders/{order_id}/collect", headers=headers)
    assert collect.status_code == 200, collect.text
    assert collect.json()["status"] == "Collected"

    processing = await client.post(f"/api/v1/laboratory/orders/{order_id}/start-processing", headers=headers)
    assert processing.status_code == 200, processing.text
    assert processing.json()["status"] == "Processing"

    results = await client.post(
        f"/api/v1/laboratory/orders/{order_id}/results", headers=headers,
        json={"results": [{"parameter_name": "Glucose", "result_type": "Numeric", "numeric_value": "95"}]},
    )
    assert results.status_code == 200, results.text
    assert results.json()["status"] == "Completed"

    # Pathologist selection is now MANDATORY at release (product decision).
    pathologist_resp = await client.post(
        "/api/v1/pathologists",
        headers=headers, json={"name": "Dr. Maria Santos", "license_number": "PRC-12345"},
    )
    assert pathologist_resp.status_code == 201, pathologist_resp.text
    released = await client.post(
        f"/api/v1/laboratory/orders/{order_id}/release",
        headers=headers, json={"pathologist_id": pathologist_resp.json()["id"]},
    )
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "Released"

    del queue  # only needed to drive the setup above


# --- 8: existing Queue Slip behavior for non-Laboratory queues unchanged ---

async def test_non_laboratory_queue_slip_unaffected(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, headers, department_name="Internal Medicine")
    doctor = (await client.post("/api/v1/doctors", headers=headers, json={"first_name": "Ana", "last_name": "Reyes"})).json()
    queue = (
        await client.post(
            "/api/v1/queues", headers=headers,
            json={
                "patient_id": deps["patient_id"], "branch_id": deps["branch_id"], "department_id": deps["department_id"],
                "doctor_id": doctor["id"], "service_id": deps["service_id"], "priority": "Normal",
            },
        )
    ).json()
    await _enter_vitals(client, headers, queue["visit_id"])

    slip = await client.get(f"/api/v1/queues/{queue['id']}/slip", headers=headers)
    assert slip.status_code == 200, slip.text
    body = slip.json()
    assert body["is_paid"] is False
    assert body["vitals_taken"] is True
    assert body["doctor_name"]
