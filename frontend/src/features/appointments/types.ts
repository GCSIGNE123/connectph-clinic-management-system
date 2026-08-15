import { Role } from "@/types";

export enum AppointmentType {
  NewConsultation = "NewConsultation",
  FollowUp = "FollowUp",
  AnnualPhysical = "AnnualPhysical",
  Teleconsultation = "Teleconsultation",
  Vaccination = "Vaccination",
  Procedure = "Procedure",
  Laboratory = "Laboratory",
  Custom = "Custom",
}

export enum AppointmentStatus {
  Booked = "Booked",
  Confirmed = "Confirmed",
  CheckedIn = "CheckedIn",
  Waiting = "Waiting",
  InConsultation = "InConsultation",
  Completed = "Completed",
  Cancelled = "Cancelled",
  NoShow = "NoShow",
  Rescheduled = "Rescheduled",
}

/** Same role set already used to gate the "New Appointment" button and the
 * List view's Confirm/Cancel row actions (see `app/(dashboard)/appointments/
 * page.tsx`) - Appointment Details' Edit/Cancel buttons reuse this single
 * source of truth rather than redefining it, matching what the backend's
 * `require_appointment_manage_role` (reschedule/cancel/confirm endpoints)
 * actually enforces. */
export const APPOINTMENT_MANAGE_ROLES = new Set<Role>([Role.Owner, Role.Administrator, Role.Receptionist]);

/** Mirrors `APPOINTMENT_STATUS_TRANSITIONS` in `backend/app/models/
 * appointment.py` exactly - the frontend must reflect the backend's actual
 * rules, not invent its own. Reschedule (`PATCH /{id}/reschedule`) is only
 * a legal transition from Booked/Confirmed; showing the Edit button
 * outside those statuses would just produce a guaranteed-failing request. */
export const APPOINTMENT_RESCHEDULABLE_STATUSES = new Set<AppointmentStatus>([
  AppointmentStatus.Booked,
  AppointmentStatus.Confirmed,
]);

/** Mirrors the same backend transition table's cancel-eligible source
 * statuses (Booked/Confirmed/CheckedIn/Waiting can move to Cancelled;
 * InConsultation/Completed/Cancelled/NoShow/Rescheduled cannot). */
export const APPOINTMENT_CANCELLABLE_STATUSES = new Set<AppointmentStatus>([
  AppointmentStatus.Booked,
  AppointmentStatus.Confirmed,
  AppointmentStatus.CheckedIn,
  AppointmentStatus.Waiting,
]);

export const APPOINTMENT_TYPE_LABELS: Record<AppointmentType, string> = {
  [AppointmentType.NewConsultation]: "New Consultation",
  [AppointmentType.FollowUp]: "Follow-up",
  [AppointmentType.AnnualPhysical]: "Annual Physical",
  [AppointmentType.Teleconsultation]: "Teleconsultation",
  [AppointmentType.Vaccination]: "Vaccination",
  [AppointmentType.Procedure]: "Procedure",
  [AppointmentType.Laboratory]: "Laboratory",
  [AppointmentType.Custom]: "Custom",
};

export const APPOINTMENT_STATUS_LABELS: Record<AppointmentStatus, string> = {
  [AppointmentStatus.Booked]: "Booked",
  [AppointmentStatus.Confirmed]: "Confirmed",
  [AppointmentStatus.CheckedIn]: "Checked In",
  [AppointmentStatus.Waiting]: "Waiting",
  [AppointmentStatus.InConsultation]: "In Consultation",
  [AppointmentStatus.Completed]: "Completed",
  [AppointmentStatus.Cancelled]: "Cancelled",
  [AppointmentStatus.NoShow]: "No Show",
  [AppointmentStatus.Rescheduled]: "Rescheduled",
};

export interface AppointmentListItem {
  id: string;
  appointmentNumber: string;
  appointmentDate: string;
  startTime: string;
  endTime: string;
  status: AppointmentStatus;
  appointmentType: AppointmentType;
  patientId: string;
  patientName: string | null;
  patientNumber: string | null;
  doctorId: string;
  doctorName: string | null;
  departmentName: string | null;
  branchId: string;
}

export interface AppointmentHistoryEntry {
  id: string;
  action: string;
  fromValue: string | null;
  toValue: string | null;
  changedBy: string | null;
  changedAt: string;
  note: string | null;
}

export interface AppointmentDetail extends AppointmentListItem {
  clinicId: string;
  departmentId: string | null;
  serviceId: string | null;
  serviceName: string | null;
  branchName: string | null;
  queueId: string | null;
  visitId: string | null;
  notes: string | null;
  createdAt: string;
  updatedAt: string;
  history: AppointmentHistoryEntry[];
}

export interface AppointmentListParams {
  search?: string;
  branchId?: string;
  departmentId?: string;
  doctorId?: string;
  status?: AppointmentStatus;
  appointmentType?: AppointmentType;
  dateFrom?: string;
  dateTo?: string;
  page?: number;
  pageSize?: number;
}

export interface CreateAppointmentInput {
  patientId: string;
  branchId: string;
  doctorId: string;
  departmentId?: string | null;
  serviceId?: string | null;
  appointmentType: AppointmentType;
  appointmentDate: string;
  startTime: string;
  notes?: string | null;
}

export interface RescheduleAppointmentInput {
  appointmentDate: string;
  startTime: string;
  reason?: string | null;
}

export interface TimeSlot {
  startTime: string;
  endTime: string;
  isAvailable: boolean;
  reason: string | null;
}

export interface DoctorScheduleDay {
  id: string;
  dayOfWeek: number;
  startTime: string;
  endTime: string;
  lunchBreakStart: string | null;
  lunchBreakEnd: string | null;
  slotDurationMinutes: number;
  maxPatientsPerDay: number | null;
  isActive: boolean;
  branchId: string | null;
}

export interface DoctorScheduleBlockEntry {
  id: string;
  blockDate: string;
  blockType: "Vacation" | "Blocked";
  reason: string | null;
}

export interface DoctorSchedule {
  doctorId: string;
  days: DoctorScheduleDay[];
  blocks: DoctorScheduleBlockEntry[];
}

export interface PatientAppointmentsBuckets {
  upcoming: AppointmentListItem[];
  completed: AppointmentListItem[];
  cancelled: AppointmentListItem[];
  noShow: AppointmentListItem[];
}
