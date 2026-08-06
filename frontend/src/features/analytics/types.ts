export interface SeriesPoint {
  label: string;
  value: number;
}

export interface OwnerDashboardStats {
  patientsToday: number;
  newPatientsToday: number;
  appointmentsToday: number;
  walkInsToday: number;
  completedConsultationsToday: number;
  cancelledVisitsToday: number;
  noShowsToday: number;
  laboratoryOrdersToday: number;
  prescriptionsIssuedToday: number;
  pendingPaymentsCount: number;
  pendingPaymentsAmount: number;
  collectedRevenueToday: number;
  outstandingBalance: number;
  avgWaitingSeconds: number | null;
  avgConsultationSeconds: number | null;
  doctorsOnDuty: number;
  roomsInUse: number | null;
}

export interface OwnerDashboard {
  today: string;
  stats: OwnerDashboardStats;
}

export interface ActivityFeedItem {
  id: string;
  eventType: string;
  description: string;
  occurredAt: string;
  actorName: string | null;
  entityType: string | null;
  entityId: string | null;
}

export interface AlertItem {
  category: string;
  severity: "warning" | "critical";
  message: string;
  value: number | null;
  threshold: number | null;
}

export type DateRangePreset = "today" | "yesterday" | "last_7_days" | "this_month" | "last_month" | "custom";

export interface ReportFilters {
  dateRange: DateRangePreset;
  start?: string;
  end?: string;
  doctorId?: string;
}

export interface PatientReport {
  newPatients: number;
  returningPatients: number;
  totalVisits: number;
  dailyCensus: SeriesPoint[];
  monthlyCensus: SeriesPoint[];
  ageDistribution: SeriesPoint[];
  genderDistribution: SeriesPoint[];
}

export interface DoctorReportRow {
  doctorId: string;
  doctorName: string;
  patientsSeen: number;
  completedVisits: number;
  cancelledVisits: number;
  avgConsultationSeconds: number | null;
  revenueGenerated: number;
  appointmentsBooked: number;
  appointmentsCompleted: number;
  appointmentUtilization: number;
}

export interface DoctorReport {
  doctors: DoctorReportRow[];
}

export interface RevenueReport {
  totalRevenue: number;
  revenueByDoctor: SeriesPoint[];
  revenueByBranch: SeriesPoint[];
  revenueByService: SeriesPoint[];
  revenueByPaymentMethod: SeriesPoint[];
  dailyRevenue: SeriesPoint[];
  outstandingInvoicesCount: number;
  outstandingInvoicesAmount: number;
  discountSummary: SeriesPoint[];
}

export interface QueueReport {
  avgWaitingSeconds: number | null;
  longestWaitSeconds: number | null;
  completedCount: number;
  cancelledCount: number;
  volumeByHour: SeriesPoint[];
}

export interface LaboratoryReport {
  ordersToday: number;
  completed: number;
  pending: number;
  avgTurnaroundSeconds: number | null;
  topRequestedTests: SeriesPoint[];
  dailyVolume: SeriesPoint[];
}

export interface AppointmentReport {
  bookings: number;
  completed: number;
  cancelled: number;
  noShows: number;
  rescheduled: number;
  doctorUtilization: Array<{
    doctor_id: string;
    doctor_name: string;
    booked: number;
    completed: number;
    utilization: number;
  }>;
  dailyBookings: SeriesPoint[];
}

export type ReportKey = "patients" | "doctors" | "revenue" | "queue" | "laboratory" | "appointments";
export type ExportFormat = "csv" | "excel" | "pdf";
