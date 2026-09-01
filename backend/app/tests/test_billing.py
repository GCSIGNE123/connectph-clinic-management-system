"""Integration tests for Phase 9 Billing & Cashier: consultation-completion
auto-creates a Draft->PendingPayment invoice with a priced Consultation Fee
line item, item add/edit/remove recomputes totals, discounts (percentage
and fixed) recompute correctly with reason/approver, full payment ->
invoice Paid + the Payment->Visit-status-sync decision (the critical
Phase-7/8-lesson check, mirrored here for Phase 9's own new sync), partial
payment -> PartiallyPaid, split payments across methods, void-payment
recomputes backward, receipt payload + print audit, role gating (Cashier
writes, Doctor view-only 403 on write, Reception read-only), tenant
isolation, and idempotent invoice creation on double-complete.
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


async def _setup_queue_deps(client: AsyncClient, headers: dict, *, consultation_fee: str = "500.00") -> dict:
    branch = (await client.post("/api/v1/branches", headers=headers, json={"name": "Main Branch", "code": "MAIN"})).json()
    department = (
        await client.post("/api/v1/departments", headers=headers, json={"department_code": "GEN", "name": "General Medicine"})
    ).json()
    doctor = (
        await client.post(
            "/api/v1/doctors", headers=headers,
            json={"first_name": "Jose", "last_name": "Rizal", "consultation_fee": consultation_fee},
        )
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


async def _complete_consultation_flow(client, make_clinic_with_owner, db_session, *, consultation_fee="500.00"):
    """Sets up a clinic, doctor, patient, queue->visit, calls/starts/opens/
    completes a consultation, returning enough context for billing tests."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers, consultation_fee=consultation_fee)
    queue = (await client.post("/api/v1/queues", headers=owner_headers, json=_queue_payload(deps))).json()
    visit_id = queue["visit_id"]

    doc_email, _doc_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor", doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "TestPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/call", headers=doc_headers)
    await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/start-consultation", headers=doc_headers)
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    cid = opened["id"]
    complete_resp = await client.post(f"/api/v1/consultations/{cid}/complete", headers=doc_headers)
    assert complete_resp.status_code == 200, complete_resp.text

    cashier_email, _cashier_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Cashier")
    cashier_token = await _login(client, cashier_email, "TestPass123!")
    cashier_headers = {"Authorization": f"Bearer {cashier_token}"}

    return clinic, owner_headers, doc_headers, cashier_headers, deps, visit_id, cid


async def test_complete_consultation_auto_creates_draft_invoice_with_consultation_fee(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, owner_headers, _doc_headers, _cashier_headers, _deps, visit_id, _cid = await _complete_consultation_flow(
        client, make_clinic_with_owner, db_session, consultation_fee="500.00"
    )
    resp = await client.get(f"/api/v1/visits/{visit_id}/invoice", headers=owner_headers)
    assert resp.status_code == 200, resp.text
    invoice = resp.json()
    assert invoice["status"] == "PendingPayment"
    assert len(invoice["items"]) == 1
    assert invoice["items"][0]["item_type"] == "ConsultationFee"
    assert float(invoice["items"][0]["unit_price"]) == 500.00
    assert float(invoice["grand_total"]) == 500.00


async def test_invoice_creation_idempotent_on_double_complete(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, owner_headers, doc_headers, _cashier_headers, _deps, visit_id, cid = await _complete_consultation_flow(
        client, make_clinic_with_owner, db_session
    )
    resp2 = await client.post(f"/api/v1/consultations/{cid}/complete", headers=doc_headers)
    assert resp2.status_code == 200, resp2.text

    resp = await client.get(f"/api/v1/visits/{visit_id}/invoice", headers=owner_headers)
    invoice_id = resp.json()["id"]

    list_resp = await client.get("/api/v1/invoices", headers=owner_headers, params={"q": resp.json()["invoice_number"]})
    items = list_resp.json()["items"]
    matching = [i for i in items if i["id"] == invoice_id]
    assert len(matching) == 1, "Double-completing a consultation must not create a duplicate invoice"


async def test_add_update_remove_item_recomputes_totals(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, owner_headers, _doc_headers, cashier_headers, _deps, visit_id, _cid = await _complete_consultation_flow(
        client, make_clinic_with_owner, db_session, consultation_fee="500.00"
    )
    invoice = (await client.get(f"/api/v1/visits/{visit_id}/invoice", headers=owner_headers)).json()
    invoice_id = invoice["id"]

    add = await client.post(
        f"/api/v1/invoices/{invoice_id}/items", headers=cashier_headers,
        json={"description": "Medical Certificate", "item_type": "MedicalCertificate", "quantity": 1, "unit_price": 200},
    )
    assert add.status_code == 200, add.text
    body = add.json()
    assert len(body["items"]) == 2
    assert float(body["grand_total"]) == 700.00

    item_id = body["items"][1]["id"]
    upd = await client.patch(f"/api/v1/invoices/{invoice_id}/items/{item_id}", headers=cashier_headers, json={"unit_price": 250})
    assert upd.status_code == 200
    assert float(upd.json()["grand_total"]) == 750.00

    rem = await client.delete(f"/api/v1/invoices/{invoice_id}/items/{item_id}", headers=cashier_headers)
    assert rem.status_code == 200
    assert len(rem.json()["items"]) == 1
    assert float(rem.json()["grand_total"]) == 500.00


async def test_apply_percentage_and_fixed_discounts(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, owner_headers, _doc_headers, cashier_headers, _deps, visit_id, _cid = await _complete_consultation_flow(
        client, make_clinic_with_owner, db_session, consultation_fee="1000.00"
    )
    invoice = (await client.get(f"/api/v1/visits/{visit_id}/invoice", headers=owner_headers)).json()
    invoice_id = invoice["id"]

    pct = await client.post(
        f"/api/v1/invoices/{invoice_id}/discounts", headers=cashier_headers,
        json={"discount_type": "SeniorCitizen", "calculation_type": "Percentage", "value": 20, "reason": "Senior ID verified"},
    )
    assert pct.status_code == 200, pct.text
    body = pct.json()
    assert len(body["discounts"]) == 1
    assert body["discounts"][0]["amount"] == "200.00"
    assert body["discounts"][0]["reason"] == "Senior ID verified"
    assert body["discounts"][0]["approved_by"] is not None
    assert float(body["grand_total"]) == 800.00

    fixed = await client.post(
        f"/api/v1/invoices/{invoice_id}/discounts", headers=cashier_headers,
        json={"discount_type": "Employee", "calculation_type": "FixedAmount", "value": 50},
    )
    assert fixed.status_code == 200
    body2 = fixed.json()
    assert float(body2["discount_total"]) == 250.00
    assert float(body2["grand_total"]) == 750.00


async def test_full_payment_transitions_to_paid_and_syncs_visit(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """The critical Phase-7/8-lesson check applied to Phase 9: recording a
    full payment must transition Invoice->Paid, and per this phase's
    documented Payment->Visit sync decision, the Visit must reflect Completed
    (it already is, from Phase 8's Consultation->Visit sync - this asserts
    that stays true and the sync path doesn't error/regress it)."""
    _clinic, owner_headers, _doc_headers, cashier_headers, _deps, visit_id, _cid = await _complete_consultation_flow(
        client, make_clinic_with_owner, db_session, consultation_fee="500.00"
    )
    invoice = (await client.get(f"/api/v1/visits/{visit_id}/invoice", headers=owner_headers)).json()
    invoice_id = invoice["id"]

    visit_before = await client.get(f"/api/v1/visits/{visit_id}", headers=owner_headers)
    assert visit_before.json()["status"] == "Completed"

    pay = await client.post(
        f"/api/v1/invoices/{invoice_id}/payments", headers=cashier_headers,
        json={"payments": [{"payment_method": "Cash", "amount": 500}]},
    )
    assert pay.status_code == 200, pay.text
    body = pay.json()
    assert body["status"] == "Paid"
    assert float(body["amount_paid"]) == 500.00
    assert float(body["balance_due"]) == 0.00

    visit_after = await client.get(f"/api/v1/visits/{visit_id}", headers=owner_headers)
    assert visit_after.json()["status"] == "Completed"


async def test_partial_payment_transitions_to_partially_paid(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, owner_headers, _doc_headers, cashier_headers, _deps, visit_id, _cid = await _complete_consultation_flow(
        client, make_clinic_with_owner, db_session, consultation_fee="500.00"
    )
    invoice_id = (await client.get(f"/api/v1/visits/{visit_id}/invoice", headers=owner_headers)).json()["id"]

    pay = await client.post(
        f"/api/v1/invoices/{invoice_id}/payments", headers=cashier_headers,
        json={"payments": [{"payment_method": "Cash", "amount": 200}]},
    )
    assert pay.status_code == 200
    body = pay.json()
    assert body["status"] == "PartiallyPaid"
    assert float(body["balance_due"]) == 300.00


async def test_split_payments_across_methods_sum_correctly(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, owner_headers, _doc_headers, cashier_headers, _deps, visit_id, _cid = await _complete_consultation_flow(
        client, make_clinic_with_owner, db_session, consultation_fee="500.00"
    )
    invoice_id = (await client.get(f"/api/v1/visits/{visit_id}/invoice", headers=owner_headers)).json()["id"]

    pay = await client.post(
        f"/api/v1/invoices/{invoice_id}/payments", headers=cashier_headers,
        json={"payments": [
            {"payment_method": "GCash", "amount": 200, "reference_number": "GC-123"},
            {"payment_method": "Cash", "amount": 300},
        ]},
    )
    assert pay.status_code == 200, pay.text
    body = pay.json()
    assert body["status"] == "Paid"
    assert float(body["amount_paid"]) == 500.00
    assert len(body["payments"]) == 2


async def test_void_payment_recomputes_backward(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, owner_headers, _doc_headers, cashier_headers, _deps, visit_id, _cid = await _complete_consultation_flow(
        client, make_clinic_with_owner, db_session, consultation_fee="500.00"
    )
    invoice_id = (await client.get(f"/api/v1/visits/{visit_id}/invoice", headers=owner_headers)).json()["id"]

    pay = await client.post(
        f"/api/v1/invoices/{invoice_id}/payments", headers=cashier_headers,
        json={"payments": [{"payment_method": "Cash", "amount": 500}]},
    )
    payment_id = pay.json()["payments"][0]["id"]
    assert pay.json()["status"] == "Paid"

    void = await client.post(f"/api/v1/payments/{payment_id}/void", headers=cashier_headers)
    assert void.status_code == 200, void.text
    body = void.json()
    assert body["status"] == "PendingPayment"
    assert float(body["amount_paid"]) == 0.00
    assert float(body["balance_due"]) == 500.00


async def test_receipt_payload_and_print_audit(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, owner_headers, _doc_headers, cashier_headers, _deps, visit_id, _cid = await _complete_consultation_flow(
        client, make_clinic_with_owner, db_session, consultation_fee="500.00"
    )
    invoice_id = (await client.get(f"/api/v1/visits/{visit_id}/invoice", headers=owner_headers)).json()["id"]
    await client.post(
        f"/api/v1/invoices/{invoice_id}/payments", headers=cashier_headers,
        json={"payments": [{"payment_method": "Cash", "amount": 500}]},
    )

    receipt = await client.get(f"/api/v1/invoices/{invoice_id}/receipt", headers=cashier_headers)
    assert receipt.status_code == 200, receipt.text
    payload = receipt.json()
    for field in ("invoice_number", "receipt_number", "clinic_name", "patient_name", "visit_number", "items", "grand_total", "payments"):
        assert field in payload

    printed = await client.post(f"/api/v1/invoices/{invoice_id}/receipt/print", headers=cashier_headers)
    assert printed.status_code == 200

    from app.models.audit_log import AuditLog

    result = await db_session.execute(select(AuditLog).where(AuditLog.action == "invoice.receipt_printed"))
    assert result.scalars().first() is not None


async def test_role_gating_cashier_doctor_reception(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """Phase 7 (P7-2): this test previously asserted Doctor/Receptionist
    get 403 on `POST /invoices/{id}/discounts`, which encoded an OLD,
    superseded permission round. `BILLING_DISCOUNT_ROLES` in
    `app/core/dependencies.py` documents its own history in a code
    comment: Round 1 (+Receptionist), Round 2 (-Receptionist, +Doctor),
    Round 3 - the CURRENT, live-verified, docs/TESTING.md-documented final
    state - (+Receptionist, +Cashier, Doctor/Owner/Administrator kept).
    The live final role set is "all five clinic-staff roles can apply
    discounts"; only `BILLING_REFUND_ROLES` (Administrator/Owner only)
    stays narrow. This test was simply never updated after that Round 3
    reversal - a stale test expectation (Option B), not an application
    defect; the previous 400 failure (not even 403) was itself proof the
    role layer already allowed the write and a downstream invoice-editable
    check fired first, since the test applied the payment (making the
    invoice non-editable) before attempting the writes it meant to gate.
    Reordered so the editability precondition doesn't mask what's being
    tested, and updated the expected status codes to match the current,
    documented, correct RBAC state."""
    clinic, owner_headers, doc_headers, cashier_headers, _deps, visit_id, _cid = await _complete_consultation_flow(
        client, make_clinic_with_owner, db_session
    )
    invoice_id = (await client.get(f"/api/v1/visits/{visit_id}/invoice", headers=owner_headers)).json()["id"]

    recept_email, _u = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Receptionist")
    recept_token = await _login(client, recept_email, "TestPass123!")
    recept_headers = {"Authorization": f"Bearer {recept_token}"}

    # Doctor: view ok, and per the current (Round 3) role set, write
    # succeeds too - Doctor is one of the five roles with discount
    # authority. Applied while the invoice is still editable (Draft/
    # PendingPayment), so this isolates the role check from the separate
    # invoice-editable-state business rule.
    doc_view = await client.get(f"/api/v1/invoices/{invoice_id}", headers=doc_headers)
    assert doc_view.status_code == 200
    doc_write = await client.post(
        f"/api/v1/invoices/{invoice_id}/discounts", headers=doc_headers,
        json={"discount_type": "Custom", "calculation_type": "FixedAmount", "value": 10},
    )
    assert doc_write.status_code == 200, doc_write.text

    # Reception: read succeeds, and write succeeds too under the current
    # Round 3 role set (Receptionist has discount authority, same as
    # Doctor above).
    recept_view = await client.get(f"/api/v1/invoices/{invoice_id}", headers=recept_headers)
    assert recept_view.status_code == 200
    recept_write = await client.post(
        f"/api/v1/invoices/{invoice_id}/discounts", headers=recept_headers,
        json={"discount_type": "Custom", "calculation_type": "FixedAmount", "value": 10},
    )
    assert recept_write.status_code == 200, recept_write.text

    # Cashier can pay - unaffected by any of the above, still verified.
    pay = await client.post(
        f"/api/v1/invoices/{invoice_id}/payments", headers=cashier_headers,
        json={"payments": [{"payment_method": "Cash", "amount": 100}]},
    )
    assert pay.status_code == 200, pay.text

    # Once the invoice is no longer editable (payment applied), a further
    # discount write is correctly rejected - but with the true business
    # reason (400 "not editable"), not conflated with a role check.
    doc_write_after_payment = await client.post(
        f"/api/v1/invoices/{invoice_id}/discounts", headers=doc_headers,
        json={"discount_type": "Custom", "calculation_type": "FixedAmount", "value": 5},
    )
    assert doc_write_after_payment.status_code == 400


async def test_tenant_isolation(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic_a, owner_headers_a, _doc_a, _cashier_a, _deps_a, visit_id_a, _cid_a = await _complete_consultation_flow(
        client, make_clinic_with_owner, db_session
    )
    invoice_id = (await client.get(f"/api/v1/visits/{visit_id_a}/invoice", headers=owner_headers_a)).json()["id"]

    _clinic_b, _owner_b, owner_headers_b = await _owner_headers(client, make_clinic_with_owner)
    resp = await client.get(f"/api/v1/invoices/{invoice_id}", headers=owner_headers_b)
    assert resp.status_code == 404

    list_resp = await client.get("/api/v1/invoices", headers=owner_headers_b)
    assert all(i["id"] != invoice_id for i in list_resp.json()["items"])


# --- Recent-records convention: newest invoice_date first, date-range filter ---

async def _second_invoice_same_clinic(client, db_session, *, clinic, owner_headers, deps) -> tuple[str, str]:
    """Creates one more patient -> queue -> consultation -> complete cycle
    in the SAME clinic/doctor as `_complete_consultation_flow` already set
    up, so a test can end up with two invoices in one clinic. Returns
    (visit_id, invoice_id)."""
    patient = (
        await client.post(
            "/api/v1/patients", headers=owner_headers,
            json={
                "first_name": "Maria", "last_name": "Santos", "birth_date": "1985-03-20",
                "gender": "Female", "civil_status": "Single", "mobile_number": "+639171234599",
            },
        )
    ).json()["patient"]
    queue = (
        await client.post(
            "/api/v1/queues", headers=owner_headers,
            json={
                "patient_id": patient["id"], "branch_id": deps["branch_id"], "department_id": deps["department_id"],
                "doctor_id": deps["doctor_id"], "service_id": deps["service_id"], "priority": "Normal",
            },
        )
    ).json()
    visit_id = queue["visit_id"]

    doc_email, _doc_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor", doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "TestPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}
    await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/call", headers=doc_headers)
    await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/start-consultation", headers=doc_headers)
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    complete_resp = await client.post(f"/api/v1/consultations/{opened['id']}/complete", headers=doc_headers)
    assert complete_resp.status_code == 200, complete_resp.text

    invoice = (await client.get(f"/api/v1/visits/{visit_id}/invoice", headers=owner_headers)).json()
    return visit_id, invoice["id"]


async def test_invoice_list_sorts_by_invoice_date_descending_not_created_at(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """The primary sort must match the field the date filter itself applies
    to (invoice_date) - an invoice created later but with an earlier
    invoice_date (e.g. backdated) must still sort as the OLDER record."""
    from datetime import date

    from app.models.invoice import Invoice

    clinic, owner_headers, _doc_headers, _cashier_headers, deps, visit_id_a, _cid = await _complete_consultation_flow(
        client, make_clinic_with_owner, db_session
    )
    invoice_a_id = (await client.get(f"/api/v1/visits/{visit_id_a}/invoice", headers=owner_headers)).json()["id"]
    _visit_id_b, invoice_b_id = await _second_invoice_same_clinic(
        client, db_session, clinic=clinic, owner_headers=owner_headers, deps=deps
    )

    invoice_a = await db_session.get(Invoice, uuid.UUID(invoice_a_id))
    invoice_b = await db_session.get(Invoice, uuid.UUID(invoice_b_id))
    invoice_a.invoice_date = date(2026, 6, 10)
    invoice_b.invoice_date = date(2026, 6, 1)
    await db_session.commit()

    resp = await client.get("/api/v1/invoices", headers=owner_headers)
    assert resp.status_code == 200, resp.text
    ids = [i["id"] for i in resp.json()["items"]]
    assert ids == [invoice_a_id, invoice_b_id]


async def test_invoice_date_range_filter_excludes_invoices_outside_the_range(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    from datetime import date

    from app.models.invoice import Invoice

    clinic, owner_headers, _doc_headers, _cashier_headers, deps, visit_id_a, _cid = await _complete_consultation_flow(
        client, make_clinic_with_owner, db_session
    )
    invoice_a_id = (await client.get(f"/api/v1/visits/{visit_id_a}/invoice", headers=owner_headers)).json()["id"]
    _visit_id_b, invoice_b_id = await _second_invoice_same_clinic(
        client, db_session, clinic=clinic, owner_headers=owner_headers, deps=deps
    )

    (await db_session.get(Invoice, uuid.UUID(invoice_a_id))).invoice_date = date(2026, 6, 15)
    (await db_session.get(Invoice, uuid.UUID(invoice_b_id))).invoice_date = date(2026, 7, 1)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/invoices", headers=owner_headers, params={"date_from": "2026-06-01", "date_to": "2026-06-30"}
    )
    assert resp.status_code == 200, resp.text
    ids = [i["id"] for i in resp.json()["items"]]
    assert ids == [invoice_a_id]


async def test_invoice_date_range_with_no_matches_returns_empty(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, owner_headers, _doc_headers, _cashier_headers, _deps, _visit_id, _cid = await _complete_consultation_flow(
        client, make_clinic_with_owner, db_session
    )
    resp = await client.get(
        "/api/v1/invoices", headers=owner_headers, params={"date_from": "2020-01-01", "date_to": "2020-01-31"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []


async def test_invoice_date_range_combines_with_status_filter(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    from datetime import date

    _clinic, owner_headers, _doc_headers, _cashier_headers, _deps, visit_id, _cid = await _complete_consultation_flow(
        client, make_clinic_with_owner, db_session
    )
    invoice = (await client.get(f"/api/v1/visits/{visit_id}/invoice", headers=owner_headers)).json()
    today = date.fromisoformat(invoice["invoice_date"])

    matching = await client.get(
        "/api/v1/invoices", headers=owner_headers,
        params={"status": "PendingPayment", "date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    assert matching.json()["items"] != []

    wrong_status = await client.get(
        "/api/v1/invoices", headers=owner_headers,
        params={"status": "Paid", "date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    assert wrong_status.json()["items"] == []


async def test_invoice_list_uses_id_as_stable_tie_break_for_identical_invoice_date_and_created_at(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    from datetime import UTC, date, datetime

    from app.models.invoice import Invoice

    clinic, owner_headers, _doc_headers, _cashier_headers, deps, visit_id_a, _cid = await _complete_consultation_flow(
        client, make_clinic_with_owner, db_session
    )
    invoice_a_id = (await client.get(f"/api/v1/visits/{visit_id_a}/invoice", headers=owner_headers)).json()["id"]
    _visit_id_b, invoice_b_id = await _second_invoice_same_clinic(
        client, db_session, clinic=clinic, owner_headers=owner_headers, deps=deps
    )

    invoice_a = await db_session.get(Invoice, uuid.UUID(invoice_a_id))
    invoice_b = await db_session.get(Invoice, uuid.UUID(invoice_b_id))
    same_date = date(2026, 6, 1)
    same_time = datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC)
    invoice_a.invoice_date = same_date
    invoice_b.invoice_date = same_date
    invoice_a.created_at = same_time
    invoice_b.created_at = same_time
    await db_session.commit()

    expected_first, expected_second = (
        (invoice_a_id, invoice_b_id) if invoice_a_id > invoice_b_id else (invoice_b_id, invoice_a_id)
    )
    resp = await client.get("/api/v1/invoices", headers=owner_headers)
    ids = [i["id"] for i in resp.json()["items"]]
    assert ids.index(expected_first) < ids.index(expected_second)
