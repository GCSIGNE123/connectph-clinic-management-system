"""YAKAP Billing Report endpoints (Task #4).

Read-only. Gated like other billing management/reporting views (Owner,
Administrator, Cashier). Clinic-scoped; aggregation happens in SQL.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_billing_manage_role, require_clinic_context
from app.models.user import User
from app.schemas.yakap_billing_report import YakapBillingReportResponse
from app.services.analytics_service import AnalyticsService
from app.services.yakap_billing_report_service import PERIODS, YakapBillingReportService

router = APIRouter(prefix="/billing/reports", tags=["billing-reports"])

_PERIOD_PATTERN = "^(" + "|".join(sorted(PERIODS)) + ")$"


@router.get("/yakap", response_model=YakapBillingReportResponse)
async def yakap_billing_report(
    period: str = Query(default="monthly", pattern=_PERIOD_PATTERN),
    start: date | None = None,
    end: date | None = None,
    q: str | None = Query(default=None, description="Patient name/number, invoice or visit number."),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_billing_manage_role),
) -> YakapBillingReportResponse:
    try:
        return await YakapBillingReportService(db).report(
            clinic_id=clinic_id, period=period, start=start, end=end, q=q or None, limit=limit, offset=offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/yakap/export")
async def export_yakap_billing_report(
    period: str = Query(default="monthly", pattern=_PERIOD_PATTERN),
    start: date | None = None,
    end: date | None = None,
    q: str | None = None,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_billing_manage_role),
) -> Response:
    """CSV of every invoice row in the filtered population (not just one page),
    built with the existing `AnalyticsService.export_report_csv`."""
    try:
        date_from, date_to, rows = await YakapBillingReportService(db).export_rows(
            clinic_id=clinic_id, period=period, start=start, end=end, q=q or None
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    body = await AnalyticsService(db).export_report_csv(report="yakap_billing", rows=rows)
    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="yakap_billing_{date_from}_{date_to}.csv"'},
    )
