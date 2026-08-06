"""Pydantic schemas for Phase 12 - Owner Dashboard & Reports.

Every report accepts the same `ReportFilters` query-param shape (date range
preset or custom start/end, optional doctor/department/branch), per the
spec's "Filters" requirement. Chart-ready series use the same
`{label|date, value}` shape throughout so the frontend has one rendering
path for every chart.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class SeriesPoint(BaseModel):
    label: str
    value: float


class OwnerDashboardStats(BaseModel):
    patients_today: int
    new_patients_today: int
    appointments_today: int
    walk_ins_today: int
    completed_consultations_today: int
    cancelled_visits_today: int
    no_shows_today: int
    laboratory_orders_today: int
    prescriptions_issued_today: int
    pending_payments_count: int
    pending_payments_amount: Decimal
    collected_revenue_today: Decimal
    outstanding_balance: Decimal
    avg_waiting_seconds: float | None
    avg_consultation_seconds: float | None
    doctors_on_duty: int
    rooms_in_use: int | None = Field(
        default=None,
        description="TODO: visits/consultations do not yet track a consultation_room_id assignment "
        "(consultation_rooms exists as master data only) - null until a future phase links them.",
    )


class OwnerDashboardResponse(BaseModel):
    today: date
    stats: OwnerDashboardStats


class ActivityFeedItem(BaseModel):
    id: str
    event_type: str
    description: str
    occurred_at: datetime
    actor_name: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None


class ActivityFeedResponse(BaseModel):
    items: list[ActivityFeedItem]


class AlertItem(BaseModel):
    category: str
    severity: str  # "warning" | "critical"
    message: str
    value: float | None = None
    threshold: float | None = None


class AlertsResponse(BaseModel):
    alerts: list[AlertItem]


class PatientReportResponse(BaseModel):
    new_patients: int
    returning_patients: int
    total_visits: int
    daily_census: list[SeriesPoint]
    monthly_census: list[SeriesPoint]
    age_distribution: list[SeriesPoint]
    gender_distribution: list[SeriesPoint]


class DoctorReportRow(BaseModel):
    doctor_id: UUID
    doctor_name: str
    patients_seen: int
    completed_visits: int
    cancelled_visits: int
    avg_consultation_seconds: float | None
    revenue_generated: Decimal
    appointments_booked: int
    appointments_completed: int
    appointment_utilization: float


class DoctorReportResponse(BaseModel):
    doctors: list[DoctorReportRow]


class RevenueReportResponse(BaseModel):
    total_revenue: Decimal
    revenue_by_doctor: list[SeriesPoint]
    revenue_by_branch: list[SeriesPoint]
    revenue_by_service: list[SeriesPoint]
    revenue_by_payment_method: list[SeriesPoint]
    daily_revenue: list[SeriesPoint]
    outstanding_invoices_count: int
    outstanding_invoices_amount: Decimal
    discount_summary: list[SeriesPoint]


class QueueReportResponse(BaseModel):
    avg_waiting_seconds: float | None
    longest_wait_seconds: float | None
    completed_count: int
    cancelled_count: int
    volume_by_hour: list[SeriesPoint]


class LaboratoryReportResponse(BaseModel):
    orders_today: int
    completed: int
    pending: int
    avg_turnaround_seconds: float | None
    top_requested_tests: list[SeriesPoint]
    daily_volume: list[SeriesPoint]


class AppointmentReportResponse(BaseModel):
    bookings: int
    completed: int
    cancelled: int
    no_shows: int
    rescheduled: int
    doctor_utilization: list[dict]
    daily_bookings: list[SeriesPoint]
