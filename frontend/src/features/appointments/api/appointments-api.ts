import { apiClient } from "@/lib/api-client";
import type { PaginatedResponse } from "@/types";
import type {
  AppointmentDetail,
  AppointmentListItem,
  AppointmentListParams,
  CreateAppointmentInput,
  DoctorSchedule,
  PatientAppointmentsBuckets,
  RescheduleAppointmentInput,
  TimeSlot,
} from "@/features/appointments/types";

interface RawAppointmentListItem {
  id: string;
  appointment_number: string;
  appointment_date: string;
  start_time: string;
  end_time: string;
  status: string;
  appointment_type: string;
  patient_id: string;
  patient_name: string | null;
  patient_number: string | null;
  doctor_id: string;
  doctor_name: string | null;
  department_name: string | null;
  branch_id: string;
}

interface RawAppointmentDetail extends RawAppointmentListItem {
  clinic_id: string;
  department_id: string | null;
  service_id: string | null;
  service_name: string | null;
  branch_name: string | null;
  queue_id: string | null;
  visit_id: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  history: {
    id: string;
    action: string;
    from_value: string | null;
    to_value: string | null;
    changed_by: string | null;
    changed_at: string;
    note: string | null;
  }[];
}

function toListItem(raw: RawAppointmentListItem): AppointmentListItem {
  return {
    id: raw.id,
    appointmentNumber: raw.appointment_number,
    appointmentDate: raw.appointment_date,
    startTime: raw.start_time,
    endTime: raw.end_time,
    status: raw.status as AppointmentListItem["status"],
    appointmentType: raw.appointment_type as AppointmentListItem["appointmentType"],
    patientId: raw.patient_id,
    patientName: raw.patient_name,
    patientNumber: raw.patient_number,
    doctorId: raw.doctor_id,
    doctorName: raw.doctor_name,
    departmentName: raw.department_name,
    branchId: raw.branch_id,
  };
}

function toDetail(raw: RawAppointmentDetail): AppointmentDetail {
  return {
    ...toListItem(raw),
    clinicId: raw.clinic_id,
    departmentId: raw.department_id,
    serviceId: raw.service_id,
    serviceName: raw.service_name,
    branchName: raw.branch_name,
    queueId: raw.queue_id,
    visitId: raw.visit_id,
    notes: raw.notes,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
    history: raw.history.map((h) => ({
      id: h.id,
      action: h.action,
      fromValue: h.from_value,
      toValue: h.to_value,
      changedBy: h.changed_by,
      changedAt: h.changed_at,
      note: h.note,
    })),
  };
}

function toQueryString(params: AppointmentListParams): string {
  const search = new URLSearchParams();
  if (params.search) search.set("q", params.search);
  if (params.branchId) search.set("branch_id", params.branchId);
  if (params.departmentId) search.set("department_id", params.departmentId);
  if (params.doctorId) search.set("doctor_id", params.doctorId);
  if (params.status) search.set("status", params.status);
  if (params.appointmentType) search.set("appointment_type", params.appointmentType);
  if (params.dateFrom) search.set("date_from", params.dateFrom);
  if (params.dateTo) search.set("date_to", params.dateTo);

  const pageSize = params.pageSize ?? 50;
  const page = params.page ?? 1;
  search.set("limit", String(pageSize));
  search.set("offset", String((page - 1) * pageSize));
  return `?${search.toString()}`;
}

function toCreatePayload(input: CreateAppointmentInput) {
  return {
    patient_id: input.patientId,
    branch_id: input.branchId,
    doctor_id: input.doctorId,
    department_id: input.departmentId || null,
    service_id: input.serviceId || null,
    appointment_type: input.appointmentType,
    appointment_date: input.appointmentDate,
    start_time: input.startTime,
    notes: input.notes || null,
  };
}

export const appointmentsApi = {
  async list(params: AppointmentListParams): Promise<PaginatedResponse<AppointmentListItem>> {
    const raw = await apiClient.get<{ items: RawAppointmentListItem[]; total: number; limit: number; offset: number }>(
      `/appointments${toQueryString(params)}`
    );
    const pageSize = raw.limit || 1;
    return {
      data: raw.items.map(toListItem),
      meta: {
        page: Math.floor(raw.offset / pageSize) + 1,
        pageSize: raw.limit,
        total: raw.total,
        totalPages: Math.max(1, Math.ceil(raw.total / pageSize)),
      },
    };
  },

  async calendar(params: AppointmentListParams): Promise<AppointmentListItem[]> {
    const raw = await apiClient.get<{ items: RawAppointmentListItem[] }>(`/appointments/calendar${toQueryString(params)}`);
    return raw.items.map(toListItem);
  },

  async get(id: string): Promise<AppointmentDetail> {
    const raw = await apiClient.get<RawAppointmentDetail>(`/appointments/${id}`);
    return toDetail(raw);
  },

  async create(input: CreateAppointmentInput): Promise<AppointmentDetail> {
    const raw = await apiClient.post<RawAppointmentDetail>("/appointments", toCreatePayload(input));
    return toDetail(raw);
  },

  async confirm(id: string): Promise<AppointmentDetail> {
    const raw = await apiClient.patch<RawAppointmentDetail>(`/appointments/${id}/confirm`, {});
    return toDetail(raw);
  },

  async reschedule(id: string, input: RescheduleAppointmentInput): Promise<AppointmentDetail> {
    const raw = await apiClient.patch<RawAppointmentDetail>(`/appointments/${id}/reschedule`, {
      appointment_date: input.appointmentDate,
      start_time: input.startTime,
      reason: input.reason || null,
    });
    return toDetail(raw);
  },

  async cancel(id: string, reason?: string): Promise<AppointmentDetail> {
    const raw = await apiClient.patch<RawAppointmentDetail>(`/appointments/${id}/cancel`, { reason: reason || null });
    return toDetail(raw);
  },

  async checkIn(id: string): Promise<AppointmentDetail> {
    const raw = await apiClient.post<RawAppointmentDetail>(`/appointments/${id}/check-in`, {});
    return toDetail(raw);
  },

  async complete(id: string): Promise<AppointmentDetail> {
    const raw = await apiClient.patch<RawAppointmentDetail>(`/appointments/${id}/complete`, {});
    return toDetail(raw);
  },

  async noShow(id: string): Promise<AppointmentDetail> {
    const raw = await apiClient.patch<RawAppointmentDetail>(`/appointments/${id}/no-show`, {});
    return toDetail(raw);
  },

  async availableSlots(doctorId: string, date: string, branchId?: string): Promise<TimeSlot[]> {
    const search = new URLSearchParams({ date });
    if (branchId) search.set("branch_id", branchId);
    const raw = await apiClient.get<{ slots: { start_time: string; end_time: string; is_available: boolean; reason: string | null }[] }>(
      `/doctors/${doctorId}/available-slots?${search.toString()}`
    );
    return raw.slots.map((s) => ({ startTime: s.start_time, endTime: s.end_time, isAvailable: s.is_available, reason: s.reason }));
  },

  async getSchedule(doctorId: string): Promise<DoctorSchedule> {
    const raw = await apiClient.get<{
      doctor_id: string;
      days: { id: string; day_of_week: number; start_time: string; end_time: string; lunch_break_start: string | null; lunch_break_end: string | null; slot_duration_minutes: number; max_patients_per_day: number | null; is_active: boolean; branch_id: string | null }[];
      blocks: { id: string; block_date: string; block_type: "Vacation" | "Blocked"; reason: string | null }[];
    }>(`/doctors/${doctorId}/schedule`);
    return {
      doctorId: raw.doctor_id,
      days: raw.days.map((d) => ({
        id: d.id, dayOfWeek: d.day_of_week, startTime: d.start_time, endTime: d.end_time,
        lunchBreakStart: d.lunch_break_start, lunchBreakEnd: d.lunch_break_end,
        slotDurationMinutes: d.slot_duration_minutes, maxPatientsPerDay: d.max_patients_per_day,
        isActive: d.is_active, branchId: d.branch_id,
      })),
      blocks: raw.blocks.map((b) => ({ id: b.id, blockDate: b.block_date, blockType: b.block_type, reason: b.reason })),
    };
  },

  async setSchedule(doctorId: string, days: { dayOfWeek: number; startTime: string; endTime: string; lunchBreakStart?: string | null; lunchBreakEnd?: string | null; slotDurationMinutes: number; maxPatientsPerDay?: number | null; isActive: boolean }[]): Promise<DoctorSchedule> {
    await apiClient.put(`/doctors/${doctorId}/schedule`, {
      days: days.map((d) => ({
        day_of_week: d.dayOfWeek, start_time: d.startTime, end_time: d.endTime,
        lunch_break_start: d.lunchBreakStart || null, lunch_break_end: d.lunchBreakEnd || null,
        slot_duration_minutes: d.slotDurationMinutes, max_patients_per_day: d.maxPatientsPerDay || null,
        is_active: d.isActive,
      })),
    });
    return appointmentsApi.getSchedule(doctorId);
  },

  async addScheduleBlock(doctorId: string, blockDate: string, blockType: "Vacation" | "Blocked", reason?: string): Promise<DoctorSchedule> {
    await apiClient.post(`/doctors/${doctorId}/schedule/blocks`, { block_date: blockDate, block_type: blockType, reason: reason || null });
    return appointmentsApi.getSchedule(doctorId);
  },

  async removeScheduleBlock(doctorId: string, blockId: string): Promise<DoctorSchedule> {
    await apiClient.delete(`/doctors/${doctorId}/schedule/blocks/${blockId}`);
    return appointmentsApi.getSchedule(doctorId);
  },

  async listForPatient(patientId: string): Promise<PatientAppointmentsBuckets> {
    const raw = await apiClient.get<{
      upcoming: RawAppointmentListItem[]; completed: RawAppointmentListItem[]; cancelled: RawAppointmentListItem[]; no_show: RawAppointmentListItem[];
    }>(`/patients/${patientId}/appointments`);
    return {
      upcoming: raw.upcoming.map(toListItem),
      completed: raw.completed.map(toListItem),
      cancelled: raw.cancelled.map(toListItem),
      noShow: raw.no_show.map(toListItem),
    };
  },
};
