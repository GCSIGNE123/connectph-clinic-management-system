"""Owner Dashboard & Reports service (Phase 12).

Pure read/aggregation layer - reuses repository query methods rather than
duplicating any business logic already implemented for the Doctor
Dashboard (Phase 7), Cashier Dashboard (Phase 9), Laboratory Dashboard
(Phase 10), and Appointment reporting (Phase 11). Where a metric already
had a repository method (e.g. `InvoiceRepository.sum_todays_revenue`,
`DoctorWorkspaceRepository.avg_duration_seconds`), it is called directly
here. New aggregation methods added for this phase live on the existing
repositories they logically belong to (see each repository's "Phase 12"
section) - only genuinely cross-cutting queries (the merged Activity Feed,
live Owner Alerts) live in the new `AnalyticsRepository`.

Date-range resolution: every report endpoint accepts a `date_range` preset
(`today`, `yesterday`, `last_7_days`, `this_month`, `last_month`, `custom`)
plus optional `start`/`end` for `custom`. `_resolve_range()` centralizes
this so every report applies filters identically, per the spec.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from app.models.laboratory_order import LaboratoryOrderStatus
from app.models.queue import QueueStatus
from app.repositories.analytics_repository import AnalyticsRepository
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.clinical_orders_repository import ClinicalOrdersRepository
from app.repositories.doctor_workspace_repository import DoctorWorkspaceRepository
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.laboratory_repository import LaboratoryRepository
from app.repositories.patient_repository import PatientRepository
from app.repositories.queue_repository import QueueRepository
from app.repositories.visit_repository import VisitRepository
from app.services.audit_service import AuditService

DATE_RANGE_PRESETS = {"today", "yesterday", "last_7_days", "this_month", "last_month", "custom"}


def _resolve_range(date_range: str | None, start: date | None, end: date | None, today: date) -> tuple[date, date]:
    """Returns an inclusive (date_from, date_to) pair."""
    preset = date_range or "today"
    if preset == "custom":
        if start is None or end is None:
            raise ValueError("start and end are required when date_range=custom")
        return start, end
    if preset == "yesterday":
        y = today - timedelta(days=1)
        return y, y
    if preset == "last_7_days":
        return today - timedelta(days=6), today
    if preset == "this_month":
        return today.replace(day=1), today
    if preset == "last_month":
        first_this_month = today.replace(day=1)
        last_month_end = first_this_month - timedelta(days=1)
        return last_month_end.replace(day=1), last_month_end
    # default/"today"
    return today, today


def _to_datetime_bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    dt_from = datetime(date_from.year, date_from.month, date_from.day, tzinfo=UTC)
    dt_to = datetime(date_to.year, date_to.month, date_to.day, tzinfo=UTC) + timedelta(days=1)
    return dt_from, dt_to


class AnalyticsService:
    def __init__(self, session) -> None:
        self.session = session
        self.analytics_repo = AnalyticsRepository(session)
        self.invoice_repo = InvoiceRepository(session)
        self.queue_repo = QueueRepository(session)
        self.visit_repo = VisitRepository(session)
        self.patient_repo = PatientRepository(session)
        self.appointment_repo = AppointmentRepository(session)
        self.laboratory_repo = LaboratoryRepository(session)
        self.orders_repo = ClinicalOrdersRepository(session)
        self.doctor_workspace_repo = DoctorWorkspaceRepository(session)
        self.audit_service = AuditService(session)

    def resolve_range(self, date_range: str | None, start: date | None, end: date | None) -> tuple[date, date]:
        today = datetime.now(UTC).date()
        return _resolve_range(date_range, start, end, today)

    async def _log_report_generated(self, *, clinic_id: UUID, actor_id: UUID, report: str, filters: dict) -> None:
        """Report generation audit: reuses the existing `audit_logs` table
        (via `AuditService`) rather than a new `report_generation_log`
        table - the generic audit log already carries clinic/user/action/
        entity/metadata, which is exactly what "report type + filters +
        generated_by" needs; a dedicated table would just duplicate it."""
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action=f"analytics.report_generated.{report}",
            entity_type="report", entity_id=report, metadata=filters,
        )
        await self.session.commit()

    # --- Owner Dashboard ---

    async def get_dashboard(self, *, clinic_id: UUID):
        from app.schemas.analytics import OwnerDashboardResponse, OwnerDashboardStats

        now = datetime.now(UTC)
        today = now.date()
        dt_from, dt_to = _to_datetime_bounds(today, today)

        visit_status_counts = await self.visit_repo.status_counts_in_range(clinic_id, today, today)
        visit_type_counts = await self.visit_repo.visit_type_counts_in_range(clinic_id, today, today)
        new_patients = await self.patient_repo.count_created_in_range(clinic_id, dt_from, dt_to)
        appt_status_counts = await self.appointment_repo.status_counts_in_range(clinic_id, today, today)
        lab_orders_today = await self.laboratory_repo.count_created_in_range(clinic_id, dt_from, dt_to)
        prescriptions_today = await self.orders_repo.count_prescriptions_in_range(clinic_id, dt_from, dt_to)
        pending_count = await self.invoice_repo.count_pending_payments(clinic_id)
        revenue_today = await self.invoice_repo.sum_todays_revenue(clinic_id, dt_from, dt_to)
        outstanding = await self.invoice_repo.sum_outstanding_balance(clinic_id)
        wait_stats = await self.queue_repo.waiting_time_stats(clinic_id, today, today)
        avg_consult = await self.doctor_workspace_repo.avg_duration_seconds(clinic_id=clinic_id, doctor_id=None, visit_date=today)
        doctors_on_duty = await self.visit_repo.distinct_doctors_with_activity(clinic_id, today)

        # pending_payments_amount: outstanding balance restricted to invoices
        # actually in PendingPayment/PartiallyPaid status (reuses the same
        # `sum_outstanding_balance` filter Billing's Cashier Dashboard shows
        # as "outstanding" - here surfaced alongside the pending *count*).
        pending_amount = outstanding

        appointments_today_total = sum(appt_status_counts.values())

        stats = OwnerDashboardStats(
            patients_today=sum(visit_status_counts.values()),
            new_patients_today=new_patients,
            appointments_today=appointments_today_total,
            walk_ins_today=visit_type_counts.get("WalkIn", 0),
            completed_consultations_today=visit_status_counts.get("Completed", 0),
            cancelled_visits_today=visit_status_counts.get("Cancelled", 0),
            no_shows_today=visit_status_counts.get("NoShow", 0),
            laboratory_orders_today=lab_orders_today,
            prescriptions_issued_today=prescriptions_today,
            pending_payments_count=pending_count,
            pending_payments_amount=pending_amount,
            collected_revenue_today=revenue_today,
            outstanding_balance=outstanding,
            avg_waiting_seconds=wait_stats["avg_waiting_seconds"],
            avg_consultation_seconds=avg_consult,
            doctors_on_duty=doctors_on_duty,
            rooms_in_use=None,
        )
        return OwnerDashboardResponse(today=today, stats=stats)

    # --- Real-time Activity Feed ---

    async def get_activity_feed(self, *, clinic_id: UUID, limit: int = 50):
        from app.schemas.analytics import ActivityFeedItem, ActivityFeedResponse

        timeline_events = await self.visit_repo.recent_timeline_events(clinic_id, limit=limit)
        audit_logs = await self.analytics_repo.recent_audit_logs(clinic_id, limit=limit)
        queue_changes = await self.analytics_repo.recent_queue_status_changes(clinic_id, limit=limit)

        items: list[ActivityFeedItem] = []
        for ev in timeline_events:
            items.append(ActivityFeedItem(
                id=f"visit_event:{ev.id}", event_type=ev.event_type.value,
                description=ev.note or ev.event_type.value, occurred_at=ev.occurred_at,
                entity_type="visit", entity_id=str(ev.visit_id),
            ))
        for log in audit_logs:
            items.append(ActivityFeedItem(
                id=f"audit:{log.id}", event_type=log.action,
                description=log.action.replace(".", " ").replace("_", " ").title(),
                occurred_at=log.created_at, entity_type=log.entity_type, entity_id=log.entity_id,
            ))
        for qc in queue_changes:
            items.append(ActivityFeedItem(
                id=f"queue:{qc.id}", event_type=f"queue.{qc.to_status.value.lower()}",
                description=f"Queue ticket moved to {qc.to_status.value}"
                + (f" - {qc.note}" if qc.note else ""),
                occurred_at=qc.changed_at, entity_type="queue", entity_id=str(qc.queue_id),
            ))

        items.sort(key=lambda i: i.occurred_at, reverse=True)
        return ActivityFeedResponse(items=items[:limit])

    # --- Owner Alerts ---

    async def get_alerts(self, *, clinic_id: UUID, queue_volume_threshold: int = 10, wait_minutes_threshold: int = 30, outstanding_days_threshold: int = 30):
        from app.schemas.analytics import AlertItem, AlertsResponse

        now = datetime.now(UTC)
        today = now.date()
        alerts: list[AlertItem] = []

        waiting_count = await self.analytics_repo.current_waiting_count(clinic_id, today)
        if waiting_count > queue_volume_threshold:
            alerts.append(AlertItem(
                category="HighQueueVolume", severity="warning",
                message=f"{waiting_count} patients currently waiting (threshold {queue_volume_threshold}).",
                value=waiting_count, threshold=queue_volume_threshold,
            ))

        longest_wait = await self.analytics_repo.longest_current_wait_seconds(clinic_id, today, now)
        if longest_wait is not None and longest_wait > wait_minutes_threshold * 60:
            alerts.append(AlertItem(
                category="LongWaitingTime", severity="warning",
                message=f"A patient has been waiting {int(longest_wait // 60)} minutes (threshold {wait_minutes_threshold}).",
                value=round(longest_wait / 60, 1), threshold=wait_minutes_threshold,
            ))

        old_cutoff = today - timedelta(days=outstanding_days_threshold)
        old_outstanding = await self.invoice_repo.outstanding_invoices_in_range(clinic_id, date(2000, 1, 1), old_cutoff)
        if old_outstanding:
            total = sum((inv.balance_due for inv in old_outstanding), Decimal("0"))
            alerts.append(AlertItem(
                category="OutstandingPayments", severity="critical",
                message=f"{len(old_outstanding)} invoice(s) outstanding for over {outstanding_days_threshold} days, totalling {total}.",
                value=float(total), threshold=outstanding_days_threshold,
            ))

        # System Errors / Failed Backups: explicitly out of scope - no
        # infrastructure monitoring exists yet to check against. Returned as
        # empty categories so the frontend can render the section without a
        # special case, per the spec's "architecture-only" note.
        alerts.append(AlertItem(category="SystemErrors", severity="warning", message="No monitoring configured yet.", value=None, threshold=None))
        alerts = [a for a in alerts if a.category != "SystemErrors"]  # keep response focused on real, actionable alerts

        return AlertsResponse(alerts=alerts)

    # --- Reports ---

    async def get_patient_report(self, *, clinic_id: UUID, date_from: date, date_to: date):
        from app.schemas.analytics import PatientReportResponse, SeriesPoint

        distinct_patients = await self.visit_repo.distinct_patient_ids_in_range(clinic_id, date_from, date_to)
        dt_from, dt_to = _to_datetime_bounds(date_from, date_to)
        new_patients = await self.patient_repo.count_created_in_range(clinic_id, dt_from, dt_to)
        returning = await self.visit_repo.returning_patient_count(clinic_id, date_from, date_to)
        daily = await self.visit_repo.daily_census_series(clinic_id, date_from, date_to)
        monthly = await self.visit_repo.monthly_census_series(clinic_id, date_from, date_to)
        gender = await self.patient_repo.gender_distribution(clinic_id, distinct_patients)
        age = await self.patient_repo.age_distribution(clinic_id, distinct_patients)

        return PatientReportResponse(
            new_patients=new_patients,
            returning_patients=returning,
            total_visits=sum(p["value"] for p in daily),
            daily_census=[SeriesPoint(label=p["date"], value=p["value"]) for p in daily],
            monthly_census=[SeriesPoint(label=p["date"], value=p["value"]) for p in monthly],
            age_distribution=[SeriesPoint(label=k, value=v) for k, v in age.items()],
            gender_distribution=[SeriesPoint(label=k, value=v) for k, v in gender.items()],
        )

    async def get_doctor_report(self, *, clinic_id: UUID, date_from: date, date_to: date):
        from app.schemas.analytics import DoctorReportResponse, DoctorReportRow

        visit_stats = await self.visit_repo.doctor_visit_stats(clinic_id, date_from, date_to)
        dt_from, dt_to = _to_datetime_bounds(date_from, date_to)
        revenue_rows = {r["doctor_id"]: r["revenue"] for r in await self.invoice_repo.revenue_by_doctor(clinic_id, dt_from, dt_to)}
        utilization_rows = {r["doctor_id"]: r for r in await self.appointment_repo.doctor_utilization_in_range(clinic_id, date_from, date_to)}

        rows: list[DoctorReportRow] = []
        for v in visit_stats:
            doctor_id = v["doctor_id"]
            avg_consult = await self.visit_repo.avg_consultation_seconds_for_doctor(clinic_id, doctor_id, date_from, date_to)
            util = utilization_rows.get(doctor_id, {"booked": 0, "completed": 0, "utilization": 0.0})
            rows.append(DoctorReportRow(
                doctor_id=doctor_id, doctor_name=v["doctor_name"],
                patients_seen=v["patients_seen"], completed_visits=v["completed"], cancelled_visits=v["cancelled"],
                avg_consultation_seconds=avg_consult,
                revenue_generated=revenue_rows.get(doctor_id, Decimal("0")),
                appointments_booked=util["booked"], appointments_completed=util["completed"],
                appointment_utilization=util["utilization"],
            ))
        return DoctorReportResponse(doctors=rows)

    async def get_revenue_report(self, *, clinic_id: UUID, date_from: date, date_to: date):
        from app.schemas.analytics import RevenueReportResponse, SeriesPoint

        dt_from, dt_to = _to_datetime_bounds(date_from, date_to)
        total = await self.invoice_repo.sum_revenue_in_range(clinic_id, dt_from, dt_to)
        by_doctor = await self.invoice_repo.revenue_by_doctor(clinic_id, dt_from, dt_to)
        by_branch = await self.invoice_repo.revenue_by_branch(clinic_id, dt_from, dt_to)
        by_service = await self.invoice_repo.revenue_by_service(clinic_id, dt_from, dt_to)
        by_method = await self.invoice_repo.revenue_by_payment_method(clinic_id, dt_from, dt_to)
        daily = await self.invoice_repo.daily_revenue_series(clinic_id, dt_from, dt_to)
        outstanding = await self.invoice_repo.outstanding_invoices_in_range(clinic_id, date_from, date_to + timedelta(days=1))
        discounts = await self.invoice_repo.discount_summary_in_range(clinic_id, date_from, date_to + timedelta(days=1))

        outstanding_amount = sum((inv.balance_due for inv in outstanding), Decimal("0"))

        return RevenueReportResponse(
            total_revenue=total,
            revenue_by_doctor=[SeriesPoint(label=r["doctor_name"], value=float(r["revenue"])) for r in by_doctor],
            revenue_by_branch=[SeriesPoint(label=r["branch_name"], value=float(r["revenue"])) for r in by_branch],
            revenue_by_service=[SeriesPoint(label=r["service"], value=float(r["revenue"])) for r in by_service],
            revenue_by_payment_method=[SeriesPoint(label=r["method"], value=float(r["revenue"])) for r in by_method],
            daily_revenue=[SeriesPoint(label=r["date"], value=float(r["value"])) for r in daily],
            outstanding_invoices_count=len(outstanding),
            outstanding_invoices_amount=outstanding_amount,
            discount_summary=[SeriesPoint(label=r["discount_type"], value=float(r["amount"])) for r in discounts],
        )

    async def get_queue_report(self, *, clinic_id: UUID, date_from: date, date_to: date):
        from app.schemas.analytics import QueueReportResponse, SeriesPoint

        wait_stats = await self.queue_repo.waiting_time_stats(clinic_id, date_from, date_to)
        status_counts = await self.queue_repo.status_counts_in_range(clinic_id, date_from, date_to)
        by_hour = await self.queue_repo.volume_by_hour(clinic_id, date_from, date_to)

        return QueueReportResponse(
            avg_waiting_seconds=wait_stats["avg_waiting_seconds"],
            longest_wait_seconds=wait_stats["longest_wait_seconds"],
            completed_count=status_counts.get(QueueStatus.COMPLETED.value, 0),
            cancelled_count=status_counts.get(QueueStatus.CANCELLED.value, 0),
            volume_by_hour=[SeriesPoint(label=f"{r['hour']:02d}:00", value=r["value"]) for r in by_hour],
        )

    async def get_laboratory_report(self, *, clinic_id: UUID, date_from: date, date_to: date):
        from app.schemas.analytics import LaboratoryReportResponse, SeriesPoint

        dt_from, dt_to = _to_datetime_bounds(date_from, date_to)
        counts = await self.laboratory_repo.report_counts_in_range(clinic_id, dt_from, dt_to)
        avg_turnaround = await self.laboratory_repo.avg_turnaround_seconds(clinic_id, dt_from, dt_to)
        top_tests = await self.laboratory_repo.top_requested_tests(clinic_id, dt_from, dt_to)
        daily = await self.laboratory_repo.daily_volume_series(clinic_id, dt_from, dt_to)

        pending = sum(v for k, v in counts.items() if k in {LaboratoryOrderStatus.REQUESTED.value, LaboratoryOrderStatus.COLLECTED.value, LaboratoryOrderStatus.PROCESSING.value})
        completed = counts.get(LaboratoryOrderStatus.COMPLETED.value, 0) + counts.get(LaboratoryOrderStatus.RELEASED.value, 0)

        return LaboratoryReportResponse(
            orders_today=sum(counts.values()),
            completed=completed,
            pending=pending,
            avg_turnaround_seconds=avg_turnaround,
            top_requested_tests=[SeriesPoint(label=t["test"], value=t["value"]) for t in top_tests],
            daily_volume=[SeriesPoint(label=d["date"], value=d["value"]) for d in daily],
        )

    async def get_appointment_report(self, *, clinic_id: UUID, date_from: date, date_to: date):
        from app.schemas.analytics import AppointmentReportResponse, SeriesPoint

        status_counts = await self.appointment_repo.status_counts_in_range(clinic_id, date_from, date_to)
        rescheduled = await self.appointment_repo.rescheduled_count_in_range(clinic_id, date_from, date_to)
        utilization = await self.appointment_repo.doctor_utilization_in_range(clinic_id, date_from, date_to)
        daily = await self.appointment_repo.daily_booking_series(clinic_id, date_from, date_to)

        return AppointmentReportResponse(
            bookings=sum(status_counts.values()),
            completed=status_counts.get("Completed", 0),
            cancelled=status_counts.get("Cancelled", 0),
            no_shows=status_counts.get("NoShow", 0),
            rescheduled=rescheduled,
            doctor_utilization=utilization,
            daily_bookings=[SeriesPoint(label=d["date"], value=d["value"]) for d in daily],
        )

    # --- Export ---

    async def export_report_csv(self, *, report: str, rows: list[dict]) -> str:
        """Real CSV export via stdlib `csv` - works for every report since
        they all reduce to a flat list of dict rows before this is called."""
        import csv
        import io

        if not rows:
            return ""
        # Rows are a heterogeneous mix (one summary row of scalar fields,
        # plus one row per chart-series data point) - union every row's
        # keys into one fieldname set (order-preserving) rather than
        # assuming the first row's keys cover every column, and fill
        # missing cells with "" via `restval`.
        fieldnames: list[str] = []
        seen = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    fieldnames.append(key)
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, restval="")
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue()
