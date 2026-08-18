import { apiClient } from "@/lib/api-client";
import type { PaginatedResponse } from "@/types";
import type {
  UpdateVisitInput,
  VisitDetail,
  VisitListItem,
  VisitListParams,
  VisitStatus,
  VisitTimelineEntry,
} from "@/features/visits/types";

interface RawTimelineEntry {
  id: string;
  visit_id: string;
  event_type: string;
  occurred_at: string;
  recorded_by: string | null;
  note: string | null;
  event_metadata: Record<string, unknown> | null;
}

interface RawVisitListItem {
  id: string;
  visit_number: string;
  visit_date: string;
  visit_type: string;
  status: string;
  priority: string;
  branch_id: string;
  patient_id: string;
  patient_name: string | null;
  patient_number: string | null;
  doctor_id: string | null;
  doctor_name: string | null;
  department_id: string | null;
  department_name: string | null;
  service_id: string | null;
  service_name: string | null;
  queue_id: string | null;
  queue_number: string | null;
  created_at: string;
}

interface RawVisitDetail extends RawVisitListItem {
  clinic_id: string;
  arrival_time: string | null;
  check_in_time: string | null;
  called_time: string | null;
  consultation_start: string | null;
  consultation_end: string | null;
  check_out_time: string | null;
  remarks: string | null;
  created_by: string | null;
  updated_by: string | null;
  updated_at: string;
  branch_name: string | null;
  timeline: RawTimelineEntry[];
}

function toTimelineEntry(raw: RawTimelineEntry): VisitTimelineEntry {
  return {
    id: raw.id,
    visitId: raw.visit_id,
    eventType: raw.event_type as VisitTimelineEntry["eventType"],
    occurredAt: raw.occurred_at,
    recordedBy: raw.recorded_by,
    note: raw.note,
    metadata: raw.event_metadata,
  };
}

function toVisitListItem(raw: RawVisitListItem): VisitListItem {
  return {
    id: raw.id,
    visitNumber: raw.visit_number,
    visitDate: raw.visit_date,
    visitType: raw.visit_type as VisitListItem["visitType"],
    status: raw.status as VisitListItem["status"],
    priority: raw.priority as VisitListItem["priority"],
    branchId: raw.branch_id,
    patientId: raw.patient_id,
    patientName: raw.patient_name,
    patientNumber: raw.patient_number,
    doctorId: raw.doctor_id,
    doctorName: raw.doctor_name,
    departmentId: raw.department_id,
    departmentName: raw.department_name,
    serviceId: raw.service_id,
    serviceName: raw.service_name,
    queueId: raw.queue_id,
    queueNumber: raw.queue_number,
    createdAt: raw.created_at,
  };
}

function toVisitDetail(raw: RawVisitDetail): VisitDetail {
  return {
    ...toVisitListItem(raw),
    clinicId: raw.clinic_id,
    arrivalTime: raw.arrival_time,
    checkInTime: raw.check_in_time,
    calledTime: raw.called_time,
    consultationStart: raw.consultation_start,
    consultationEnd: raw.consultation_end,
    checkOutTime: raw.check_out_time,
    remarks: raw.remarks,
    createdBy: raw.created_by,
    updatedBy: raw.updated_by,
    updatedAt: raw.updated_at,
    branchName: raw.branch_name,
    timeline: raw.timeline.map(toTimelineEntry),
  };
}

function toQueryString(params: VisitListParams): string {
  const search = new URLSearchParams();
  if (params.search) search.set("q", params.search);
  if (params.branchId) search.set("branch_id", params.branchId);
  if (params.patientId) search.set("patient_id", params.patientId);
  if (params.doctorId) search.set("doctor_id", params.doctorId);
  if (params.departmentId) search.set("department_id", params.departmentId);
  if (params.status) search.set("status", params.status);
  if (params.visitType) search.set("visit_type", params.visitType);
  if (params.dateFrom) search.set("date_from", params.dateFrom);
  if (params.dateTo) search.set("date_to", params.dateTo);

  const pageSize = params.pageSize ?? 50;
  const page = params.page ?? 1;
  search.set("limit", String(pageSize));
  search.set("offset", String((page - 1) * pageSize));

  return `?${search.toString()}`;
}

function toUpdatePayload(input: UpdateVisitInput) {
  return {
    doctor_id: input.doctorId,
    department_id: input.departmentId,
    service_id: input.serviceId,
    priority: input.priority,
    remarks: input.remarks,
  };
}

/** `/api/v1/visits/*` bindings for Visit (Encounter) Management. */
export const visitsApi = {
  async list(params: VisitListParams): Promise<PaginatedResponse<VisitListItem>> {
    const raw = await apiClient.get<{ items: RawVisitListItem[]; total: number; limit: number; offset: number }>(
      `/visits${toQueryString(params)}`
    );
    const pageSize = raw.limit || 1;
    return {
      data: raw.items.map(toVisitListItem),
      meta: {
        page: Math.floor(raw.offset / pageSize) + 1,
        pageSize: raw.limit,
        total: raw.total,
        totalPages: Math.max(1, Math.ceil(raw.total / pageSize)),
      },
    };
  },

  async get(id: string): Promise<VisitDetail> {
    const raw = await apiClient.get<RawVisitDetail>(`/visits/${id}`);
    return toVisitDetail(raw);
  },

  async getTimeline(id: string): Promise<VisitTimelineEntry[]> {
    const raw = await apiClient.get<RawTimelineEntry[]>(`/visits/${id}/timeline`);
    return raw.map(toTimelineEntry);
  },

  async update(id: string, input: UpdateVisitInput): Promise<VisitDetail> {
    const raw = await apiClient.patch<RawVisitDetail>(`/visits/${id}`, toUpdatePayload(input));
    return toVisitDetail(raw);
  },

  async changeStatus(id: string, status: VisitStatus, note?: string): Promise<VisitDetail> {
    const raw = await apiClient.patch<RawVisitDetail>(`/visits/${id}/status`, { status, note: note || null });
    return toVisitDetail(raw);
  },

  /** Creates a `DraftVitals` Visit BEFORE any Queue ticket exists, so
   * something can be attached to it first - either vitals (Consultation/
   * Follow-up, see `NewQueueDialog`'s vitals step) or an invoice
   * (Laboratory pay-first, see `NewQueueDialog`'s Laboratory step /
   * `LabPaymentStep`). `POST /queues` later attaches a Queue ticket to this
   * same Visit id. `doctorId` is required for the Consultation/Follow-up
   * path (the backend rejects a missing one there - see
   * `VisitService.create_draft_visit_for_pre_queue`) but optional for
   * Laboratory. */
  async createPreQueue(input: {
    patientId: string;
    branchId: string;
    doctorId?: string | null;
    departmentId: string;
    serviceId: string;
    remarks?: string | null;
  }): Promise<VisitDetail> {
    const raw = await apiClient.post<RawVisitDetail>("/visits/pre-queue", {
      patient_id: input.patientId,
      branch_id: input.branchId,
      doctor_id: input.doctorId || null,
      department_id: input.departmentId,
      service_id: input.serviceId,
      remarks: input.remarks || null,
    });
    return toVisitDetail(raw);
  },

  async listForPatient(patientId: string, params: { page?: number; pageSize?: number } = {}): Promise<PaginatedResponse<VisitListItem>> {
    const pageSize = params.pageSize ?? 50;
    const page = params.page ?? 1;
    const search = new URLSearchParams();
    search.set("limit", String(pageSize));
    search.set("offset", String((page - 1) * pageSize));
    const raw = await apiClient.get<{ items: RawVisitListItem[]; total: number; limit: number; offset: number }>(
      `/patients/${patientId}/visits?${search.toString()}`
    );
    return {
      data: raw.items.map(toVisitListItem),
      meta: {
        page: Math.floor(raw.offset / pageSize) + 1,
        pageSize: raw.limit,
        total: raw.total,
        totalPages: Math.max(1, Math.ceil(raw.total / pageSize)),
      },
    };
  },
};
