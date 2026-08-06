/**
 * Phase 19: Patient self-service appointment booking API bindings.
 * Thin wrappers around the patient-portal booking endpoints
 * (`/api/v1/patient-portal/appointments/...`), all authenticated via
 * `patientApiFetch` (see `client.ts`), scoped server-side to the
 * authenticated patient's own `patient_id` from the JWT.
 */
import { patientApiFetch } from "@/features/patient-portal/api/client";

export interface BranchOption {
  id: string;
  name: string;
  address: string | null;
}

export interface DepartmentOption {
  id: string;
  name: string;
}

export interface DoctorOption {
  id: string;
  full_name: string;
  specialization: string | null;
  department_id: string | null;
  branch_id: string | null;
}

export interface AvailableDatesResponse {
  doctor_id: string;
  dates: string[];
}

export interface TimeSlot {
  start_time: string;
  end_time: string;
}

export interface AvailableSlotsResponse {
  doctor_id: string;
  date: string;
  slots: TimeSlot[];
}

export interface AppointmentDetail {
  id: string;
  appointment_number: string;
  appointment_type: string;
  appointment_date: string;
  start_time: string;
  end_time: string;
  status: string;
  doctor_name: string | null;
  department_name: string | null;
  branch_name: string | null;
  notes: string | null;
}

export const APPOINTMENT_TYPES = [
  "NewConsultation", "FollowUp", "AnnualPhysical", "Vaccination", "Procedure", "Laboratory", "Custom",
] as const;

export function listBranches() {
  return patientApiFetch<BranchOption[]>("/patient-portal/appointments/branches");
}

export function listDepartments() {
  return patientApiFetch<DepartmentOption[]>("/patient-portal/appointments/departments");
}

export function listDoctors(params?: { branchId?: string; departmentId?: string }) {
  const qs = new URLSearchParams();
  if (params?.branchId) qs.set("branch_id", params.branchId);
  if (params?.departmentId) qs.set("department_id", params.departmentId);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return patientApiFetch<DoctorOption[]>(`/patient-portal/appointments/doctors${suffix}`);
}

export function getAvailableDates(doctorId: string, dateFrom: string, dateTo: string, branchId?: string) {
  const qs = new URLSearchParams({ doctor_id: doctorId, date_from: dateFrom, date_to: dateTo });
  if (branchId) qs.set("branch_id", branchId);
  return patientApiFetch<AvailableDatesResponse>(`/patient-portal/appointments/availability?${qs.toString()}`);
}

export function getAvailableSlots(doctorId: string, date: string, branchId?: string) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  if (branchId) qs.set("branch_id", branchId);
  return patientApiFetch<AvailableSlotsResponse>(`/patient-portal/appointments/availability/${date}?${qs.toString()}`);
}

export interface CreateAppointmentPayload {
  branch_id: string;
  doctor_id: string;
  department_id?: string | null;
  service_id?: string | null;
  appointment_type: string;
  appointment_date: string;
  start_time: string;
  notes?: string | null;
}

export function createAppointment(payload: CreateAppointmentPayload) {
  return patientApiFetch<AppointmentDetail>("/patient-portal/appointments", { method: "POST", body: payload });
}

export function rescheduleAppointment(id: string, payload: { appointment_date: string; start_time: string; reason?: string | null }) {
  return patientApiFetch<AppointmentDetail>(`/patient-portal/appointments/${id}/reschedule`, { method: "PATCH", body: payload });
}

export function cancelAppointment(id: string, reason?: string | null) {
  return patientApiFetch<AppointmentDetail>(`/patient-portal/appointments/${id}/cancel`, { method: "POST", body: { reason: reason ?? null } });
}
