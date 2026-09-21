"""Task #4: YAKAP Billing Report.

Population rule under test: invoices of patients with
`Patient.is_yakap_beneficiary = true` (patient-level status). The per-visit
`Queue.visit_classification` must NEVER decide inclusion. Date basis is
`Invoice.invoice_date`. Totals are computed server-side over the whole
filtered population (never one page), and an invoice with several items is
counted once.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient

from app.models.invoice import Invoice, InvoiceStatus
from app.models.invoice_item import InvoiceItem, InvoiceItemType
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.queue import Queue, VisitClassification
from app.models.visit import Visit
from app.services.yakap_billing_report_service import resolve_period
from app.tests.test_billing import _login, _setup_queue_deps

pytestmark = pytest.mark.asyncio

D = Decimal
CONSULT = InvoiceItemType.CONSULTATION_FEE
LAB = InvoiceItemType.LABORATORY


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    from app.core.rate_limit import _memory_buckets

    _memory_buckets.clear()
    yield
    _memory_buckets.clear()


_seq = {"n": 0}


def _next() -> int:
    _seq["n"] += 1
    return _seq["n"]


async def _setup(client: AsyncClient, make_clinic_with_owner):
    clinic, owner, password = await make_clinic_with_owner()
    headers = {"Authorization": f"Bearer {await _login(client, owner.email, password)}"}
    deps = await _setup_queue_deps(client, headers)
    return clinic, headers, deps


async def _patient(client: AsyncClient, headers, first: str, *, yakap: bool) -> str:
    n = _next()
    resp = await client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "first_name": first, "last_name": "Reportee", "birth_date": f"19{60 + n % 30}-01-15",
            "gender": "Male", "civil_status": "Single", "mobile_number": f"+63917{n:07d}",
            "is_yakap_beneficiary": yakap,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["patient"]["id"]


async def _invoice(
    db,
    clinic,
    deps,
    patient_id: str,
    *,
    when: date,
    items: list[tuple[InvoiceItemType, str, str]],
    paid: list[str] | None = None,
    status: InvoiceStatus | None = None,
    queue_class: VisitClassification | None = None,
    number: str | None = None,
) -> Invoice:
    """Builds Visit -> (optional Queue with the given classification) -> Invoice
    -> InvoiceItems -> Payments straight through the ORM (billing math mirrors
    the service: total = sum(items), paid = sum(completed payments))."""
    n = _next()
    visit = Visit(
        clinic_id=clinic.id, branch_id=uuid.UUID(deps["branch_id"]), patient_id=uuid.UUID(patient_id),
        visit_number=f"VIS-T-{n:06d}", visit_date=when,
    )
    db.add(visit)
    await db.flush()
    if queue_class is not None:
        db.add(
            Queue(
                clinic_id=clinic.id, branch_id=uuid.UUID(deps["branch_id"]), patient_id=uuid.UUID(patient_id),
                department_id=uuid.UUID(deps["department_id"]), service_id=uuid.UUID(deps["service_id"]),
                visit_id=visit.id, queue_number=f"A{n:03d}", queue_prefix="A", queue_date=when,
                visit_classification=queue_class,
            )
        )
    total = sum((D(a) for _t, _d, a in items), D("0"))
    paid_total = sum((D(p) for p in (paid or [])), D("0"))
    if status is None:
        status = (
            InvoiceStatus.PAID if paid_total >= total and total > 0
            else InvoiceStatus.PARTIALLY_PAID if paid_total > 0
            else InvoiceStatus.PENDING_PAYMENT
        )
    inv = Invoice(
        clinic_id=clinic.id, visit_id=visit.id, branch_id=uuid.UUID(deps["branch_id"]), patient_id=uuid.UUID(patient_id),
        invoice_number=number or f"INV-T-{n:06d}", invoice_date=when, status=status,
        subtotal=total, discount_total=D("0"), grand_total=total, amount_paid=paid_total, balance_due=total - paid_total,
    )
    db.add(inv)
    await db.flush()
    for item_type, description, amount in items:
        db.add(
            InvoiceItem(
                clinic_id=clinic.id, invoice_id=inv.id, item_type=item_type, description=description,
                quantity=D("1"), unit_price=D(amount), discount_amount=D("0"), line_total=D(amount),
            )
        )
    for amount in paid or []:
        db.add(
            Payment(
                clinic_id=clinic.id, invoice_id=inv.id, payment_method=PaymentMethod.CASH, amount=D(amount),
                status=PaymentStatus.COMPLETED, paid_at=datetime.now(UTC),
            )
        )
    await db.commit()
    return inv


async def _report(client, headers, **params):
    resp = await client.get("/api/v1/billing/reports/yakap", headers=headers, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _custom(start: date, end: date, **extra) -> dict:
    return {"period": "custom", "start": start.isoformat(), "end": end.isoformat(), **extra}


JUNE = (date(2026, 6, 1), date(2026, 6, 30))


# --- Population: patient-level YAKAP, independent of visit classification ----


async def test_yakap_patient_included_regular_patient_excluded(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup(client, make_clinic_with_owner)
    yak = await _patient(client, headers, "Yak", yakap=True)
    reg = await _patient(client, headers, "Reg", yakap=False)
    y_inv = await _invoice(db_session, clinic, deps, yak, when=date(2026, 6, 10), items=[(CONSULT, "Consultation", "300.00")])
    await _invoice(db_session, clinic, deps, reg, when=date(2026, 6, 10), items=[(CONSULT, "Consultation", "300.00")])

    body = await _report(client, headers, **_custom(*JUNE))
    assert [r["invoice_number"] for r in body["items"]] == [y_inv.invoice_number]
    assert body["summary"]["total_yakap_patients"] == 1
    assert body["total"] == 1


@pytest.mark.parametrize(
    "patient_yakap, visit_class, included",
    [
        (True, VisitClassification.REGULAR, True),   # CASE 1: YAKAP patient + Regular visit -> INCLUDED
        (False, VisitClassification.YAKAP, False),   # CASE 2: non-YAKAP patient + Yakap visit -> EXCLUDED
        (True, VisitClassification.YAKAP, True),     # CASE 3: YAKAP patient + Yakap visit -> INCLUDED
        (False, VisitClassification.REGULAR, False), # CASE 4: Regular patient + Regular visit -> EXCLUDED
    ],
)
async def test_population_uses_patient_flag_not_visit_classification(
    client, make_clinic_with_owner, db_session, patient_yakap, visit_class, included
) -> None:
    clinic, headers, deps = await _setup(client, make_clinic_with_owner)
    pid = await _patient(client, headers, "Case", yakap=patient_yakap)
    inv = await _invoice(
        db_session, clinic, deps, pid, when=date(2026, 6, 10), items=[(CONSULT, "Consultation", "300.00")],
        queue_class=visit_class,
    )
    body = await _report(client, headers, **_custom(*JUNE))
    numbers = [r["invoice_number"] for r in body["items"]]
    assert (inv.invoice_number in numbers) is included
    assert body["summary"]["total_invoices"] == (1 if included else 0)


# --- Period presets / dates ------------------------------------------------


def test_resolve_period_weekly_monthly_yearly_custom_are_pure_calendar_ranges() -> None:
    wed = date(2026, 9, 16)  # a Wednesday
    assert resolve_period("weekly", wed, None, None) == (date(2026, 9, 14), date(2026, 9, 20))  # Mon-Sun
    assert resolve_period("weekly", date(2026, 9, 20), None, None) == (date(2026, 9, 14), date(2026, 9, 20))  # Sunday
    assert resolve_period("monthly", wed, None, None) == (date(2026, 9, 1), date(2026, 9, 30))
    assert resolve_period("monthly", date(2028, 2, 10), None, None) == (date(2028, 2, 1), date(2028, 2, 29))
    assert resolve_period("yearly", wed, None, None) == (date(2026, 1, 1), date(2026, 12, 31))
    assert resolve_period("custom", wed, date(2026, 3, 1), date(2026, 3, 5)) == (date(2026, 3, 1), date(2026, 3, 5))
    with pytest.raises(ValueError):
        resolve_period("custom", wed, None, None)
    with pytest.raises(ValueError):
        resolve_period("custom", wed, date(2026, 3, 9), date(2026, 3, 1))


async def test_manila_day_rollover_changes_the_week_only_in_manila(monkeypatch, client, make_clinic_with_owner) -> None:
    """Sunday 2026-09-20 23:30 UTC is already Monday 09-21 in Manila -> the
    Manila week is the NEXT one; a UTC 'today' would wrongly stay in the old week."""
    from app.services import invoice_service as inv_mod

    real_dt = inv_mod.datetime

    class FrozenDatetime(real_dt):
        @classmethod
        def now(cls, tz=None):
            frozen = real_dt(2026, 9, 20, 23, 30, tzinfo=UTC)
            return frozen.astimezone(tz) if tz else frozen

    monkeypatch.setattr(inv_mod, "datetime", FrozenDatetime)
    _clinic, headers, _deps = await _setup(client, make_clinic_with_owner)
    body = await _report(client, headers, period="weekly")
    assert (body["date_from"], body["date_to"]) == ("2026-09-21", "2026-09-27")


async def test_weekly_monthly_yearly_include_the_right_invoices(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup(client, make_clinic_with_owner)
    pid = await _patient(client, headers, "Period", yakap=True)
    today = datetime.now(ZoneInfo("Asia/Manila")).date()
    monday = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    year_start = date(today.year, 1, 1)

    today_inv = await _invoice(db_session, clinic, deps, pid, when=today, items=[(CONSULT, "Consultation", "100.00")])
    before_week = await _invoice(db_session, clinic, deps, pid, when=monday - timedelta(days=1), items=[(CONSULT, "Consultation", "10.00")])
    before_month = await _invoice(db_session, clinic, deps, pid, when=month_start - timedelta(days=1), items=[(CONSULT, "Consultation", "1.00")])
    last_year = await _invoice(db_session, clinic, deps, pid, when=year_start - timedelta(days=1), items=[(CONSULT, "Consultation", "1000.00")])

    def numbers(body):
        return {r["invoice_number"] for r in body["items"]}

    weekly = await _report(client, headers, period="weekly")
    assert today_inv.invoice_number in numbers(weekly) and before_week.invoice_number not in numbers(weekly)
    monthly = await _report(client, headers, period="monthly")
    assert today_inv.invoice_number in numbers(monthly)
    assert before_month.invoice_number not in numbers(monthly)
    yearly = await _report(client, headers, period="yearly")
    assert today_inv.invoice_number in numbers(yearly)
    assert last_year.invoice_number not in numbers(yearly)
    assert yearly["date_from"] == year_start.isoformat() and yearly["date_to"] == date(today.year, 12, 31).isoformat()


async def test_custom_range_is_inclusive_on_both_ends(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup(client, make_clinic_with_owner)
    pid = await _patient(client, headers, "Edge", yakap=True)
    day_before = await _invoice(db_session, clinic, deps, pid, when=date(2026, 5, 31), items=[(CONSULT, "C", "1.00")])
    first = await _invoice(db_session, clinic, deps, pid, when=date(2026, 6, 1), items=[(CONSULT, "C", "2.00")])
    last = await _invoice(db_session, clinic, deps, pid, when=date(2026, 6, 30), items=[(CONSULT, "C", "3.00")])
    day_after = await _invoice(db_session, clinic, deps, pid, when=date(2026, 7, 1), items=[(CONSULT, "C", "4.00")])

    body = await _report(client, headers, **_custom(*JUNE))
    got = {r["invoice_number"] for r in body["items"]}
    assert got == {first.invoice_number, last.invoice_number}
    assert day_before.invoice_number not in got and day_after.invoice_number not in got
    assert D(body["summary"]["total_billed"]) == D("5.00")


async def test_custom_range_requires_start_and_end(client, make_clinic_with_owner) -> None:
    _clinic, headers, _deps = await _setup(client, make_clinic_with_owner)
    resp = await client.get("/api/v1/billing/reports/yakap", headers=headers, params={"period": "custom"})
    assert resp.status_code == 400
    bad = await client.get(
        "/api/v1/billing/reports/yakap", headers=headers, params={"period": "custom", "start": "2026-06-09", "end": "2026-06-01"}
    )
    assert bad.status_code == 400
    unknown = await client.get("/api/v1/billing/reports/yakap", headers=headers, params={"period": "decade"})
    assert unknown.status_code == 422


# --- Money: billed / paid / outstanding / item counts --------------------


async def test_unpaid_partial_and_paid_summary(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup(client, make_clinic_with_owner)
    a = await _patient(client, headers, "Unpaid", yakap=True)
    b = await _patient(client, headers, "Partial", yakap=True)
    c = await _patient(client, headers, "Paid", yakap=True)
    await _invoice(db_session, clinic, deps, a, when=date(2026, 6, 5), items=[(CONSULT, "Consultation", "300.00")])
    await _invoice(db_session, clinic, deps, b, when=date(2026, 6, 6), items=[(CONSULT, "Consultation", "300.00")], paid=["100.00"])
    await _invoice(db_session, clinic, deps, c, when=date(2026, 6, 7), items=[(CONSULT, "Consultation", "300.00")], paid=["300.00"])

    s = (await _report(client, headers, **_custom(*JUNE)))["summary"]
    assert D(s["total_billed"]) == D("900.00")
    assert D(s["total_paid"]) == D("400.00")
    assert D(s["total_outstanding"]) == D("500.00")
    assert D(s["total_billed"]) - D(s["total_paid"]) == D(s["total_outstanding"])
    assert s["total_yakap_patients"] == 3 and s["total_invoices"] == 3
    statuses = {r["patient_name"].split()[0]: r["status"] for r in (await _report(client, headers, **_custom(*JUNE)))["items"]}
    assert statuses == {"Unpaid": "PendingPayment", "Partial": "PartiallyPaid", "Paid": "Paid"}


async def test_multi_item_invoice_counts_invoice_total_once_and_items_correctly(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup(client, make_clinic_with_owner)
    pid = await _patient(client, headers, "Multi", yakap=True)
    await _invoice(
        db_session, clinic, deps, pid, when=date(2026, 6, 8),
        items=[(CONSULT, "Consultation", "300.00"), (LAB, "CBC", "250.00"), (LAB, "Urinalysis", "100.00"), (LAB, "FBS", "150.00")],
        paid=["100.00", "200.00"],
    )
    body = await _report(client, headers, **_custom(*JUNE))
    s = body["summary"]
    assert len(body["items"]) == 1  # one ROW per invoice, not per item
    assert D(s["total_billed"]) == D("800.00")  # 300+250+100+150 counted ONCE
    assert D(s["total_paid"]) == D("300.00")  # two payments each counted once
    assert D(s["total_outstanding"]) == D("500.00")
    assert s["total_consultations"] == 1 and s["total_laboratory_services"] == 3
    assert s["total_yakap_patients"] == 1
    row = body["items"][0]
    assert row["consultation_count"] == 1 and row["laboratory_count"] == 3
    assert sorted(row["services"]) == sorted(["Consultation", "CBC", "Urinalysis", "FBS"])
    assert D(row["paid"]) == D("300.00") and D(row["outstanding"]) == D("500.00")


async def test_multiple_invoices_for_one_patient_count_patient_once(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup(client, make_clinic_with_owner)
    pid = await _patient(client, headers, "Twice", yakap=True)
    await _invoice(db_session, clinic, deps, pid, when=date(2026, 6, 2), items=[(CONSULT, "Consultation", "300.00")], paid=["300.00"])
    await _invoice(db_session, clinic, deps, pid, when=date(2026, 6, 20), items=[(CONSULT, "Consultation", "200.00"), (LAB, "CBC", "250.00")])

    body = await _report(client, headers, **_custom(*JUNE))
    s = body["summary"]
    assert s["total_yakap_patients"] == 1 and s["total_invoices"] == 2 and body["total"] == 2
    assert D(s["total_billed"]) == D("750.00") and D(s["total_paid"]) == D("300.00")
    assert D(s["total_outstanding"]) == D("450.00")
    assert s["total_consultations"] == 2 and s["total_laboratory_services"] == 1
    # Newest invoice first.
    assert [r["invoice_date"] for r in body["items"]] == ["2026-06-20", "2026-06-02"]


async def test_pay_first_lab_is_one_item_and_not_double_counted(client, make_clinic_with_owner, db_session) -> None:
    """A walk-in/pay-first lab invoice carries its Laboratory line from the start (paid in
    full); Task #1/#9 logic never adds a second line at completion, and the report counts what
    the invoice actually holds - one lab item, one payment."""
    clinic, headers, deps = await _setup(client, make_clinic_with_owner)
    pid = await _patient(client, headers, "PayFirst", yakap=True)
    await _invoice(db_session, clinic, deps, pid, when=date(2026, 6, 9), items=[(LAB, "CBC", "250.00")], paid=["250.00"])
    s = (await _report(client, headers, **_custom(*JUNE)))["summary"]
    assert s["total_laboratory_services"] == 1 and s["total_consultations"] == 0
    assert D(s["total_billed"]) == D("250.00") and D(s["total_paid"]) == D("250.00") and D(s["total_outstanding"]) == D("0")


async def test_late_lab_charge_after_payment_is_counted_once(client, make_clinic_with_owner, db_session) -> None:
    """Task #9 reopens a paid invoice by ADDING one lab line: total rises, the earlier payment
    stays, the balance is only the new charge, and nothing is counted twice."""
    clinic, headers, deps = await _setup(client, make_clinic_with_owner)
    pid = await _patient(client, headers, "Late", yakap=True)
    await _invoice(
        db_session, clinic, deps, pid, when=date(2026, 6, 9),
        items=[(CONSULT, "Consultation", "300.00"), (LAB, "CBC", "350.00")], paid=["300.00"],
        status=InvoiceStatus.PARTIALLY_PAID,
    )
    body = await _report(client, headers, **_custom(*JUNE))
    s = body["summary"]
    assert D(s["total_billed"]) == D("650.00") and D(s["total_paid"]) == D("300.00") and D(s["total_outstanding"]) == D("350.00")
    assert s["total_consultations"] == 1 and s["total_laboratory_services"] == 1
    assert body["items"][0]["status"] == "PartiallyPaid"


async def test_voided_payment_is_not_counted_as_paid(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup(client, make_clinic_with_owner)
    pid = await _patient(client, headers, "Voided", yakap=True)
    inv = await _invoice(db_session, clinic, deps, pid, when=date(2026, 6, 9), items=[(CONSULT, "Consultation", "300.00")], paid=["100.00"])
    db_session.add(
        Payment(
            clinic_id=clinic.id, invoice_id=inv.id, payment_method=PaymentMethod.CASH, amount=D("200.00"),
            status=PaymentStatus.VOIDED, paid_at=datetime.now(UTC),
        )
    )
    await db_session.commit()
    s = (await _report(client, headers, **_custom(*JUNE)))["summary"]
    assert D(s["total_paid"]) == D("100.00")


async def test_cancelled_and_draft_invoices_are_excluded(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup(client, make_clinic_with_owner)
    pid = await _patient(client, headers, "Cancel", yakap=True)
    ok = await _invoice(db_session, clinic, deps, pid, when=date(2026, 6, 3), items=[(CONSULT, "Consultation", "300.00")])
    await _invoice(db_session, clinic, deps, pid, when=date(2026, 6, 4), items=[(CONSULT, "Consultation", "999.00")], status=InvoiceStatus.CANCELLED)
    await _invoice(db_session, clinic, deps, pid, when=date(2026, 6, 5), items=[(CONSULT, "Consultation", "888.00")], status=InvoiceStatus.DRAFT)
    body = await _report(client, headers, **_custom(*JUNE))
    assert [r["invoice_number"] for r in body["items"]] == [ok.invoice_number]
    assert D(body["summary"]["total_billed"]) == D("300.00")


# --- Empty, pagination, search, tenant isolation, roles -------------------


async def test_empty_result_returns_zeroed_summary(client, make_clinic_with_owner) -> None:
    _clinic, headers, _deps = await _setup(client, make_clinic_with_owner)
    body = await _report(client, headers, **_custom(*JUNE))
    assert body["items"] == [] and body["total"] == 0
    s = body["summary"]
    assert s["total_yakap_patients"] == s["total_invoices"] == s["total_consultations"] == s["total_laboratory_services"] == 0
    assert D(s["total_billed"]) == D(s["total_paid"]) == D(s["total_outstanding"]) == D("0")


async def test_pagination_does_not_change_summary_totals(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup(client, make_clinic_with_owner)
    pid = await _patient(client, headers, "Pages", yakap=True)
    for day in range(1, 6):
        await _invoice(db_session, clinic, deps, pid, when=date(2026, 6, day), items=[(CONSULT, "Consultation", "100.00")], paid=["40.00"])

    full = await _report(client, headers, **_custom(*JUNE), limit=100, offset=0)
    p1 = await _report(client, headers, **_custom(*JUNE), limit=2, offset=0)
    p3 = await _report(client, headers, **_custom(*JUNE), limit=2, offset=4)
    assert len(p1["items"]) == 2 and len(p3["items"]) == 1
    assert p1["total"] == p3["total"] == 5
    assert p1["summary"] == p3["summary"] == full["summary"]
    assert D(p1["summary"]["total_billed"]) == D("500.00") and D(p1["summary"]["total_paid"]) == D("200.00")
    ids = [r["invoice_id"] for r in full["items"]]
    assert len(set(ids)) == 5


async def test_search_narrows_rows_and_summary_together(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup(client, make_clinic_with_owner)
    a = await _patient(client, headers, "Alpha", yakap=True)
    b = await _patient(client, headers, "Bravo", yakap=True)
    await _invoice(db_session, clinic, deps, a, when=date(2026, 6, 5), items=[(CONSULT, "Consultation", "300.00")])
    await _invoice(db_session, clinic, deps, b, when=date(2026, 6, 6), items=[(CONSULT, "Consultation", "500.00")])

    body = await _report(client, headers, **_custom(*JUNE), q="alpha")
    assert [r["patient_name"].split()[0] for r in body["items"]] == ["Alpha"]
    assert D(body["summary"]["total_billed"]) == D("300.00") and body["summary"]["total_yakap_patients"] == 1


async def test_tenant_isolation(client, make_clinic_with_owner, db_session) -> None:
    clinic_a, headers_a, deps_a = await _setup(client, make_clinic_with_owner)
    clinic_b, headers_b, deps_b = await _setup(client, make_clinic_with_owner)
    pa = await _patient(client, headers_a, "ClinicA", yakap=True)
    pb = await _patient(client, headers_b, "ClinicB", yakap=True)
    await _invoice(db_session, clinic_a, deps_a, pa, when=date(2026, 6, 5), items=[(CONSULT, "Consultation", "300.00")], paid=["300.00"])
    await _invoice(db_session, clinic_b, deps_b, pb, when=date(2026, 6, 5), items=[(CONSULT, "Consultation", "700.00"), (LAB, "CBC", "50.00")], paid=["100.00"])

    a = await _report(client, headers_a, **_custom(*JUNE))
    assert [r["patient_name"].split()[0] for r in a["items"]] == ["ClinicA"]
    assert D(a["summary"]["total_billed"]) == D("300.00") and D(a["summary"]["total_paid"]) == D("300.00")
    assert a["summary"]["total_laboratory_services"] == 0 and a["summary"]["total_yakap_patients"] == 1
    b = await _report(client, headers_b, **_custom(*JUNE))
    assert [r["patient_name"].split()[0] for r in b["items"]] == ["ClinicB"]
    assert D(b["summary"]["total_billed"]) == D("750.00") and D(b["summary"]["total_paid"]) == D("100.00")
    # Clinic A cannot find Clinic B's patient by search either.
    assert (await _report(client, headers_a, **_custom(*JUNE), q="ClinicB"))["total"] == 0


async def test_export_csv_contains_every_filtered_row_not_just_one_page(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup(client, make_clinic_with_owner)
    pid = await _patient(client, headers, "Csv", yakap=True)
    for day in range(1, 4):
        await _invoice(db_session, clinic, deps, pid, when=date(2026, 6, day), items=[(CONSULT, "Consultation", "100.00"), (LAB, "CBC", "50.00")])
    reg = await _patient(client, headers, "Regular", yakap=False)
    await _invoice(db_session, clinic, deps, reg, when=date(2026, 6, 2), items=[(CONSULT, "Consultation", "100.00")])

    resp = await client.get("/api/v1/billing/reports/yakap/export", headers=headers, params=_custom(*JUNE))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "yakap_billing_2026-06-01_2026-06-30.csv" in resp.headers["content-disposition"]
    lines = resp.text.strip().splitlines()
    assert lines[0].startswith("Date,Patient,Patient No.,Visit,Invoice")
    assert len(lines) == 1 + 3  # header + 3 YAKAP invoices; the Regular patient is excluded
    assert "Regular" not in resp.text


async def test_role_gating_and_unauthenticated(client, make_clinic_with_owner, db_session) -> None:
    from app.tests.test_billing import _make_role_login

    clinic, _headers, _deps = await _setup(client, make_clinic_with_owner)
    for role, expected in (("Cashier", 200), ("Doctor", 403), ("Receptionist", 403)):
        email, _user = await _make_role_login(db_session, clinic_id=clinic.id, role_name=role)
        token = await _login(client, email, "TestPass123!")
        resp = await client.get(
            "/api/v1/billing/reports/yakap", headers={"Authorization": f"Bearer {token}"}, params=_custom(*JUNE)
        )
        assert resp.status_code == expected, (role, resp.text)
    assert (await client.get("/api/v1/billing/reports/yakap", params=_custom(*JUNE))).status_code in (401, 403)


async def test_existing_invoice_list_is_unaffected_by_the_report(client, make_clinic_with_owner, db_session) -> None:
    """The report is read-only and separate: the normal Billing list still returns
    every patient's invoices, YAKAP or not."""
    clinic, headers, deps = await _setup(client, make_clinic_with_owner)
    yak = await _patient(client, headers, "Yk", yakap=True)
    reg = await _patient(client, headers, "Rg", yakap=False)
    await _invoice(db_session, clinic, deps, yak, when=date(2026, 6, 5), items=[(CONSULT, "Consultation", "300.00")])
    await _invoice(db_session, clinic, deps, reg, when=date(2026, 6, 5), items=[(CONSULT, "Consultation", "300.00")])
    await _report(client, headers, **_custom(*JUNE))
    listing = (await client.get("/api/v1/invoices", headers=headers)).json()
    assert listing["total"] == 2
