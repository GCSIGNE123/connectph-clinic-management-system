import { apiClient } from "@/lib/api-client";
import type { PaginatedResponse } from "@/types";
import type {
  CreateQueueInput,
  QueueDetail,
  QueueListItem,
  QueueListParams,
  QueueSlip,
  QueueStatus,
  QueueStatusHistoryEntry,
  UpdateQueueInput,
} from "@/features/queue/types";

interface RawHistoryEntry {
  id: string;
  from_status: string | null;
  to_status: string;
  changed_by: string | null;
  changed_at: string;
  note: string | null;
}

interface RawQueueListItem {
  id: string;
  queue_number: string;
  queue_date: string;
  priority: string;
  status: string;
  branch_id: string;
  department_id: string;
  department_name: string | null;
  doctor_id: string | null;
  doctor_name: string | null;
  service_id: string;
  service_name: string | null;
  patient_id: string;
  patient_name: string | null;
  patient_number: string | null;
  created_at: string;
  called_at: string | null;
  visit_id: string | null;
}

interface RawQueueDetail extends RawQueueListItem {
  clinic_id: string;
  queue_prefix: string;
  notes: string | null;
  serving_started_at: string | null;
  completed_at: string | null;
  created_by: string | null;
  updated_by: string | null;
  updated_at: string;
  branch_name: string | null;
  history: RawHistoryEntry[];
  room_name: string | null;
}

interface RawQueueSlip {
  queue_id: string;
  queue_number: string;
  clinic_name: string;
  branch_name: string;
  patient_name: string;
  department_name: string;
  doctor_name: string | null;
  service_name: string;
  priority: string;
  queue_date: string;
  created_at: string;
  qr_token: string;
  vitals_taken: boolean;
}

function toHistoryEntry(raw: RawHistoryEntry): QueueStatusHistoryEntry {
  return {
    id: raw.id,
    fromStatus: (raw.from_status as QueueStatusHistoryEntry["toStatus"] | null) ?? null,
    toStatus: raw.to_status as QueueStatusHistoryEntry["toStatus"],
    changedBy: raw.changed_by,
    changedAt: raw.changed_at,
    note: raw.note,
  };
}

function toQueueListItem(raw: RawQueueListItem): QueueListItem {
  return {
    id: raw.id,
    queueNumber: raw.queue_number,
    queueDate: raw.queue_date,
    priority: raw.priority as QueueListItem["priority"],
    status: raw.status as QueueListItem["status"],
    branchId: raw.branch_id,
    departmentId: raw.department_id,
    departmentName: raw.department_name,
    doctorId: raw.doctor_id,
    doctorName: raw.doctor_name,
    serviceId: raw.service_id,
    serviceName: raw.service_name,
    patientId: raw.patient_id,
    patientName: raw.patient_name,
    patientNumber: raw.patient_number,
    createdAt: raw.created_at,
    calledAt: raw.called_at,
    visitId: raw.visit_id ?? null,
  };
}

export function toQueueDetail(raw: RawQueueDetail): QueueDetail {
  return {
    ...toQueueListItem(raw),
    clinicId: raw.clinic_id,
    queuePrefix: raw.queue_prefix,
    notes: raw.notes,
    servingStartedAt: raw.serving_started_at,
    completedAt: raw.completed_at,
    createdBy: raw.created_by,
    updatedBy: raw.updated_by,
    updatedAt: raw.updated_at,
    branchName: raw.branch_name,
    history: raw.history.map(toHistoryEntry),
    roomName: raw.room_name ?? null,
  };
}

function toQueueSlip(raw: RawQueueSlip): QueueSlip {
  return {
    queueId: raw.queue_id,
    queueNumber: raw.queue_number,
    clinicName: raw.clinic_name,
    branchName: raw.branch_name,
    patientName: raw.patient_name,
    departmentName: raw.department_name,
    doctorName: raw.doctor_name,
    serviceName: raw.service_name,
    priority: raw.priority as QueueSlip["priority"],
    queueDate: raw.queue_date,
    createdAt: raw.created_at,
    qrToken: raw.qr_token,
    vitalsTaken: raw.vitals_taken,
  };
}

function toQueryString(params: QueueListParams): string {
  const search = new URLSearchParams();
  if (params.search) search.set("q", params.search);
  if (params.branchId) search.set("branch_id", params.branchId);
  if (params.departmentId) search.set("department_id", params.departmentId);
  if (params.doctorId) search.set("doctor_id", params.doctorId);
  if (params.status) search.set("status", params.status);
  if (params.priority) search.set("priority", params.priority);
  if (params.queueDate) search.set("queue_date", params.queueDate);

  const pageSize = params.pageSize ?? 50;
  const page = params.page ?? 1;
  search.set("limit", String(pageSize));
  search.set("offset", String((page - 1) * pageSize));

  return `?${search.toString()}`;
}

function toCreatePayload(input: CreateQueueInput) {
  return {
    patient_id: input.patientId,
    branch_id: input.branchId,
    department_id: input.departmentId,
    doctor_id: input.doctorId || null,
    service_id: input.serviceId,
    priority: input.priority,
    notes: input.notes || null,
    visit_id: input.visitId || null,
  };
}

function toUpdatePayload(input: UpdateQueueInput) {
  return {
    department_id: input.departmentId,
    doctor_id: input.doctorId,
    service_id: input.serviceId,
    priority: input.priority,
    notes: input.notes,
  };
}

/** `/api/v1/queues/*` + slip bindings for Reception & Queue Management. */
export const queueApi = {
  async list(params: QueueListParams): Promise<PaginatedResponse<QueueListItem>> {
    const raw = await apiClient.get<{ items: RawQueueListItem[]; total: number; limit: number; offset: number }>(
      `/queues${toQueryString(params)}`
    );
    const pageSize = raw.limit || 1;
    return {
      data: raw.items.map(toQueueListItem),
      meta: {
        page: Math.floor(raw.offset / pageSize) + 1,
        pageSize: raw.limit,
        total: raw.total,
        totalPages: Math.max(1, Math.ceil(raw.total / pageSize)),
      },
    };
  },

  async get(id: string): Promise<QueueDetail> {
    const raw = await apiClient.get<RawQueueDetail>(`/queues/${id}`);
    return toQueueDetail(raw);
  },

  async create(input: CreateQueueInput): Promise<QueueDetail> {
    const raw = await apiClient.post<RawQueueDetail>("/queues", toCreatePayload(input));
    return toQueueDetail(raw);
  },

  async update(id: string, input: UpdateQueueInput): Promise<QueueDetail> {
    const raw = await apiClient.patch<RawQueueDetail>(`/queues/${id}`, toUpdatePayload(input));
    return toQueueDetail(raw);
  },

  async changeStatus(id: string, status: QueueStatus, note?: string): Promise<QueueDetail> {
    const raw = await apiClient.patch<RawQueueDetail>(`/queues/${id}/status`, { status, note: note || null });
    return toQueueDetail(raw);
  },

  async cancel(id: string): Promise<QueueDetail> {
    const raw = await apiClient.post<RawQueueDetail>(`/queues/${id}/cancel`);
    return toQueueDetail(raw);
  },

  async reannounce(id: string): Promise<QueueDetail> {
    const raw = await apiClient.post<RawQueueDetail>(`/queues/${id}/reannounce`);
    return toQueueDetail(raw);
  },

  async getSlip(id: string): Promise<QueueSlip> {
    const raw = await apiClient.get<RawQueueSlip>(`/queues/${id}/slip`);
    return toQueueSlip(raw);
  },
};
