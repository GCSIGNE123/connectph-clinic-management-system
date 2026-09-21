"""YAKAP Billing Report service (Task #4).

Population = invoices of patients with `Patient.is_yakap_beneficiary = true`
(patient-level status; `Queue.visit_classification` never decides inclusion).
Date basis = `Invoice.invoice_date`, which is Asia/Manila-based (Task #9). The
Weekly/Monthly/Yearly presets are resolved against the clinic's own "today"
via `InvoiceService._clinic_today` - the same clinic-timezone (default
Asia/Manila) implementation that dates invoices - so this module adds no
second timezone mechanism.
"""

import calendar
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.yakap_billing_report_repository import YakapBillingReportRepository
from app.schemas.yakap_billing_report import YakapBillingReportResponse, YakapReportRow, YakapReportSummary
from app.services.invoice_service import InvoiceService

PERIODS = {"weekly", "monthly", "yearly", "custom"}
EXPORT_ROW_CAP = 10000


def resolve_period(period: str, today: date, start: date | None, end: date | None) -> tuple[date, date]:
    """Inclusive (date_from, date_to) in clinic-local calendar dates. Weekly is
    Monday-Sunday of the current week (the same convention the Billing page's
    'This Week' filter uses)."""
    if period == "weekly":
        monday = today - timedelta(days=today.weekday())
        return monday, monday + timedelta(days=6)
    if period == "monthly":
        return today.replace(day=1), today.replace(day=calendar.monthrange(today.year, today.month)[1])
    if period == "yearly":
        return date(today.year, 1, 1), date(today.year, 12, 31)
    if period == "custom":
        if start is None or end is None:
            raise ValueError("start and end are required when period=custom")
        if start > end:
            raise ValueError("start must not be after end")
        return start, end
    raise ValueError(f"unknown period '{period}'")


class YakapBillingReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = YakapBillingReportRepository(session)

    async def resolve(self, clinic_id: UUID, period: str, start: date | None, end: date | None) -> tuple[date, date]:
        today = await InvoiceService(self.session)._clinic_today(clinic_id)
        return resolve_period(period, today, start, end)

    async def report(
        self, *, clinic_id: UUID, period: str, start: date | None, end: date | None, q: str | None, limit: int, offset: int
    ) -> YakapBillingReportResponse:
        date_from, date_to = await self.resolve(clinic_id, period, start, end)
        summary = await self.repo.summary(clinic_id, date_from, date_to, q)
        total = await self.repo.count(clinic_id, date_from, date_to, q)
        rows = await self.repo.page(clinic_id, date_from, date_to, q, limit=limit, offset=offset)
        return YakapBillingReportResponse(
            period=period,
            date_from=date_from,
            date_to=date_to,
            summary=YakapReportSummary(**summary),
            items=[YakapReportRow(**r) for r in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def export_rows(
        self, *, clinic_id: UUID, period: str, start: date | None, end: date | None, q: str | None
    ) -> tuple[date, date, list[dict]]:
        date_from, date_to = await self.resolve(clinic_id, period, start, end)
        rows = await self.repo.page(clinic_id, date_from, date_to, q, limit=EXPORT_ROW_CAP, offset=0)
        flat = [
            {
                "Date": r["invoice_date"].isoformat(),
                "Patient": r["patient_name"],
                "Patient No.": r["patient_number"],
                "Visit": r["visit_number"] or "",
                "Invoice": r["invoice_number"],
                "Consultations": r["consultation_count"],
                "Laboratory Services": r["laboratory_count"],
                "Services": "; ".join(r["services"]),
                "Total Billed": f"{r['total_billed']:.2f}",
                "Paid": f"{r['paid']:.2f}",
                "Outstanding": f"{r['outstanding']:.2f}",
                "Payment Status": r["status"],
            }
            for r in rows
        ]
        return date_from, date_to, flat
