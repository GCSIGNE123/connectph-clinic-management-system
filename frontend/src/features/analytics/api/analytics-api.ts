import { apiClient, tokenStorage } from "@/lib/api-client";
import type {
  ActivityFeedItem,
  AlertItem,
  AppointmentReport,
  DoctorReport,
  ExportFormat,
  LaboratoryReport,
  OwnerDashboard,
  PatientReport,
  QueueReport,
  ReportFilters,
  ReportKey,
  RevenueReport,
  SeriesPoint,
} from "@/features/analytics/types";

/* eslint-disable @typescript-eslint/no-explicit-any -- raw snake_case wire shapes */

export function toSeries(raw: any[]): SeriesPoint[] {
  return (raw ?? []).map((p) => ({ label: String(p.label), value: Number(p.value) }));
}

function filterParams(filters: ReportFilters): Record<string, string> {
  const params: Record<string, string> = { date_range: filters.dateRange };
  if (filters.dateRange === "custom") {
    if (filters.start) params.start = filters.start;
    if (filters.end) params.end = filters.end;
  }
  if (filters.doctorId) params.doctor_id = filters.doctorId;
  return params;
}

function toQueryString(params: Record<string, string>): string {
  const search = new URLSearchParams(params);
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

function toDashboard(raw: any): OwnerDashboard {
  const s = raw.stats;
  return {
    today: raw.today,
    stats: {
      patientsToday: s.patients_today,
      newPatientsToday: s.new_patients_today,
      appointmentsToday: s.appointments_today,
      walkInsToday: s.walk_ins_today,
      completedConsultationsToday: s.completed_consultations_today,
      cancelledVisitsToday: s.cancelled_visits_today,
      noShowsToday: s.no_shows_today,
      laboratoryOrdersToday: s.laboratory_orders_today,
      prescriptionsIssuedToday: s.prescriptions_issued_today,
      pendingPaymentsCount: s.pending_payments_count,
      pendingPaymentsAmount: Number(s.pending_payments_amount),
      collectedRevenueToday: Number(s.collected_revenue_today),
      outstandingBalance: Number(s.outstanding_balance),
      avgWaitingSeconds: s.avg_waiting_seconds,
      avgConsultationSeconds: s.avg_consultation_seconds,
      doctorsOnDuty: s.doctors_on_duty,
      roomsInUse: s.rooms_in_use,
    },
  };
}

function toActivityItem(raw: any): ActivityFeedItem {
  return {
    id: raw.id,
    eventType: raw.event_type,
    description: raw.description,
    occurredAt: raw.occurred_at,
    actorName: raw.actor_name,
    entityType: raw.entity_type,
    entityId: raw.entity_id,
  };
}

function toAlert(raw: any): AlertItem {
  return {
    category: raw.category,
    severity: raw.severity,
    message: raw.message,
    value: raw.value,
    threshold: raw.threshold,
  };
}

export const analyticsApi = {
  getDashboard: async (): Promise<OwnerDashboard> => toDashboard(await apiClient.get("/analytics/dashboard")),

  getActivityFeed: async (limit = 50): Promise<ActivityFeedItem[]> => {
    const raw = await apiClient.get<any>(`/analytics/activity-feed?limit=${limit}`);
    return (raw.items ?? []).map(toActivityItem);
  },

  getAlerts: async (): Promise<AlertItem[]> => {
    const raw = await apiClient.get<any>("/analytics/alerts");
    return (raw.alerts ?? []).map(toAlert);
  },

  getPatientReport: async (filters: ReportFilters): Promise<PatientReport> => {
    const raw = await apiClient.get<any>(`/analytics/reports/patients${toQueryString(filterParams(filters))}`);
    return {
      newPatients: raw.new_patients,
      returningPatients: raw.returning_patients,
      totalVisits: raw.total_visits,
      dailyCensus: toSeries(raw.daily_census),
      monthlyCensus: toSeries(raw.monthly_census),
      ageDistribution: toSeries(raw.age_distribution),
      genderDistribution: toSeries(raw.gender_distribution),
    };
  },

  getDoctorReport: async (filters: ReportFilters): Promise<DoctorReport> => {
    const raw = await apiClient.get<any>(`/analytics/reports/doctors${toQueryString(filterParams(filters))}`);
    return {
      doctors: (raw.doctors ?? []).map((d: any) => ({
        doctorId: d.doctor_id,
        doctorName: d.doctor_name,
        patientsSeen: d.patients_seen,
        completedVisits: d.completed_visits,
        cancelledVisits: d.cancelled_visits,
        avgConsultationSeconds: d.avg_consultation_seconds,
        revenueGenerated: Number(d.revenue_generated),
        appointmentsBooked: d.appointments_booked,
        appointmentsCompleted: d.appointments_completed,
        appointmentUtilization: d.appointment_utilization,
      })),
    };
  },

  getRevenueReport: async (filters: ReportFilters): Promise<RevenueReport> => {
    const raw = await apiClient.get<any>(`/analytics/reports/revenue${toQueryString(filterParams(filters))}`);
    return {
      totalRevenue: Number(raw.total_revenue),
      revenueByDoctor: toSeries(raw.revenue_by_doctor),
      revenueByBranch: toSeries(raw.revenue_by_branch),
      revenueByService: toSeries(raw.revenue_by_service),
      revenueByPaymentMethod: toSeries(raw.revenue_by_payment_method),
      dailyRevenue: toSeries(raw.daily_revenue),
      outstandingInvoicesCount: raw.outstanding_invoices_count,
      outstandingInvoicesAmount: Number(raw.outstanding_invoices_amount),
      discountSummary: toSeries(raw.discount_summary),
    };
  },

  getQueueReport: async (filters: ReportFilters): Promise<QueueReport> => {
    const raw = await apiClient.get<any>(`/analytics/reports/queue${toQueryString(filterParams(filters))}`);
    return {
      avgWaitingSeconds: raw.avg_waiting_seconds,
      longestWaitSeconds: raw.longest_wait_seconds,
      completedCount: raw.completed_count,
      cancelledCount: raw.cancelled_count,
      volumeByHour: toSeries(raw.volume_by_hour),
    };
  },

  getLaboratoryReport: async (filters: ReportFilters): Promise<LaboratoryReport> => {
    const raw = await apiClient.get<any>(`/analytics/reports/laboratory${toQueryString(filterParams(filters))}`);
    return {
      ordersToday: raw.orders_today,
      completed: raw.completed,
      pending: raw.pending,
      avgTurnaroundSeconds: raw.avg_turnaround_seconds,
      topRequestedTests: toSeries(raw.top_requested_tests),
      dailyVolume: toSeries(raw.daily_volume),
    };
  },

  getAppointmentReport: async (filters: ReportFilters): Promise<AppointmentReport> => {
    const raw = await apiClient.get<any>(`/analytics/reports/appointments${toQueryString(filterParams(filters))}`);
    return {
      bookings: raw.bookings,
      completed: raw.completed,
      cancelled: raw.cancelled,
      noShows: raw.no_shows,
      rescheduled: raw.rescheduled,
      doctorUtilization: raw.doctor_utilization ?? [],
      dailyBookings: toSeries(raw.daily_bookings),
    };
  },

  /**
   * Export downloads bypass `apiClient` (which always JSON-parses the
   * response) - a raw `fetch` with the same bearer token is used instead so
   * the CSV/Excel blob can be triggered as a real file download.
   */
  exportReport: async (report: ReportKey, format: ExportFormat, filters: ReportFilters): Promise<void> => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:4000/api/v1";
    const params = { ...filterParams(filters), format };
    const token = tokenStorage.getAccessToken();
    const response = await fetch(`${apiUrl}/analytics/reports/${report}/export${toQueryString(params)}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail ?? `Export failed (${response.status})`);
    }
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${report}_${filters.dateRange}.${format === "excel" ? "xls" : "csv"}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
};
