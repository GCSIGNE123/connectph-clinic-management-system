"""Owner Dashboard & Reports endpoints (Phase 12).

Role gating: Owner and Administrator ONLY (`require_analytics_role`) - the
simplest, strictest gate in the project. Every endpoint 403s for every other
role, including roles that have their own scoped dashboards from earlier
phases (Doctor, Cashier, Receptionist, Laboratory).

Pure read/aggregation - see `services/analytics_service.py` docstring for
the reuse strategy. No endpoint here mutates operational data (except the
report-generation audit-log write, which reuses `audit_logs`).
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_analytics_role, require_clinic_context
from app.models.user import User
from app.schemas.analytics import (
    ActivityFeedResponse,
    AlertsResponse,
    AppointmentReportResponse,
    DoctorReportResponse,
    LaboratoryReportResponse,
    OwnerDashboardResponse,
    PatientReportResponse,
    QueueReportResponse,
    RevenueReportResponse,
)
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _range_params(
    date_range: str | None = Query(default="today"),
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> dict:
    return {"date_range": date_range, "start": start, "end": end}


@router.get("/dashboard", response_model=OwnerDashboardResponse)
async def get_dashboard(
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analytics_role),
) -> OwnerDashboardResponse:
    service = AnalyticsService(db)
    return await service.get_dashboard(clinic_id=clinic_id)


@router.get("/activity-feed", response_model=ActivityFeedResponse)
async def get_activity_feed(
    limit: int = Query(default=50, ge=1, le=200),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analytics_role),
) -> ActivityFeedResponse:
    service = AnalyticsService(db)
    return await service.get_activity_feed(clinic_id=clinic_id, limit=limit)


@router.get("/alerts", response_model=AlertsResponse)
async def get_alerts(
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analytics_role),
) -> AlertsResponse:
    service = AnalyticsService(db)
    return await service.get_alerts(clinic_id=clinic_id)


def _resolve_or_400(service: AnalyticsService, date_range, start, end):
    try:
        return service.resolve_range(date_range, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/reports/patients", response_model=PatientReportResponse)
async def get_patient_report(
    date_range: str | None = Query(default="today"),
    start: date | None = None,
    end: date | None = None,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analytics_role),
) -> PatientReportResponse:
    service = AnalyticsService(db)
    date_from, date_to = _resolve_or_400(service, date_range, start, end)
    result = await service.get_patient_report(clinic_id=clinic_id, date_from=date_from, date_to=date_to)
    await service._log_report_generated(clinic_id=clinic_id, actor_id=current_user.id, report="patients", filters={"date_range": date_range, "start": str(start) if start else None, "end": str(end) if end else None})
    return result


@router.get("/reports/doctors", response_model=DoctorReportResponse)
async def get_doctor_report(
    date_range: str | None = Query(default="today"),
    start: date | None = None,
    end: date | None = None,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analytics_role),
) -> DoctorReportResponse:
    service = AnalyticsService(db)
    date_from, date_to = _resolve_or_400(service, date_range, start, end)
    result = await service.get_doctor_report(clinic_id=clinic_id, date_from=date_from, date_to=date_to)
    await service._log_report_generated(clinic_id=clinic_id, actor_id=current_user.id, report="doctors", filters={"date_range": date_range})
    return result


@router.get("/reports/revenue", response_model=RevenueReportResponse)
async def get_revenue_report(
    date_range: str | None = Query(default="today"),
    start: date | None = None,
    end: date | None = None,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analytics_role),
) -> RevenueReportResponse:
    service = AnalyticsService(db)
    date_from, date_to = _resolve_or_400(service, date_range, start, end)
    result = await service.get_revenue_report(clinic_id=clinic_id, date_from=date_from, date_to=date_to)
    await service._log_report_generated(clinic_id=clinic_id, actor_id=current_user.id, report="revenue", filters={"date_range": date_range})
    return result


@router.get("/reports/queue", response_model=QueueReportResponse)
async def get_queue_report(
    date_range: str | None = Query(default="today"),
    start: date | None = None,
    end: date | None = None,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analytics_role),
) -> QueueReportResponse:
    service = AnalyticsService(db)
    date_from, date_to = _resolve_or_400(service, date_range, start, end)
    result = await service.get_queue_report(clinic_id=clinic_id, date_from=date_from, date_to=date_to)
    await service._log_report_generated(clinic_id=clinic_id, actor_id=current_user.id, report="queue", filters={"date_range": date_range})
    return result


@router.get("/reports/laboratory", response_model=LaboratoryReportResponse)
async def get_laboratory_report(
    date_range: str | None = Query(default="today"),
    start: date | None = None,
    end: date | None = None,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analytics_role),
) -> LaboratoryReportResponse:
    service = AnalyticsService(db)
    date_from, date_to = _resolve_or_400(service, date_range, start, end)
    result = await service.get_laboratory_report(clinic_id=clinic_id, date_from=date_from, date_to=date_to)
    await service._log_report_generated(clinic_id=clinic_id, actor_id=current_user.id, report="laboratory", filters={"date_range": date_range})
    return result


@router.get("/reports/appointments", response_model=AppointmentReportResponse)
async def get_appointment_report(
    date_range: str | None = Query(default="today"),
    start: date | None = None,
    end: date | None = None,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analytics_role),
) -> AppointmentReportResponse:
    service = AnalyticsService(db)
    date_from, date_to = _resolve_or_400(service, date_range, start, end)
    result = await service.get_appointment_report(clinic_id=clinic_id, date_from=date_from, date_to=date_to)
    await service._log_report_generated(clinic_id=clinic_id, actor_id=current_user.id, report="appointments", filters={"date_range": date_range})
    return result


_REPORT_DISPATCH = {
    "patients": lambda s, **kw: s.get_patient_report(**kw),
    "doctors": lambda s, **kw: s.get_doctor_report(**kw),
    "revenue": lambda s, **kw: s.get_revenue_report(**kw),
    "queue": lambda s, **kw: s.get_queue_report(**kw),
    "laboratory": lambda s, **kw: s.get_laboratory_report(**kw),
    "appointments": lambda s, **kw: s.get_appointment_report(**kw),
}


@router.get("/reports/{report}/export")
async def export_report(
    report: str,
    format: str = Query(default="csv", pattern="^(csv|excel|pdf)$"),
    date_range: str | None = Query(default="today"),
    start: date | None = None,
    end: date | None = None,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analytics_role),
):
    if report not in _REPORT_DISPATCH:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown report")

    if format == "pdf":
        # Explicit stub per spec's "Do not implement PDF styling yet" -
        # architecture-only, not a silent 200 with fake content.
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="PDF export is not implemented in this phase. Use format=csv or format=excel.",
        )

    service = AnalyticsService(db)
    date_from, date_to = _resolve_or_400(service, date_range, start, end)
    result = await _REPORT_DISPATCH[report](service, clinic_id=clinic_id, date_from=date_from, date_to=date_to)
    await service._log_report_generated(
        clinic_id=clinic_id, actor_id=current_user.id, report=f"{report}.export.{format}",
        filters={"date_range": date_range},
    )

    # Flatten the response model into rows generically: top-level scalar
    # fields become one summary row; any list[SeriesPoint]-shaped field
    # becomes its own section. Kept simple/generic on purpose - a real BI
    # export tool is out of scope for this phase.
    data = result.model_dump()
    rows: list[dict] = []
    scalar_row = {k: v for k, v in data.items() if not isinstance(v, list)}
    if scalar_row:
        rows.append(scalar_row)
    for key, value in data.items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            for item in value:
                rows.append({"section": key, **item})

    csv_body = await service.export_report_csv(report=report, rows=rows)
    media_type = "text/csv" if format == "csv" else "application/vnd.ms-excel"
    filename = f"{report}_{date_from}_{date_to}.csv"
    return Response(
        content=csv_body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
