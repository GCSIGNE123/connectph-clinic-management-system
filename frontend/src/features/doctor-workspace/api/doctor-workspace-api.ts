import { apiClient } from "@/lib/api-client";
import type { DoctorDashboard, DoctorQueueItem, LockInfo } from "@/features/doctor-workspace/types";

interface RawStats {
  waiting: number;
  called: number;
  serving: number;
  completed_today: number;
  cancelled: number;
  no_show: number;
  avg_consultation_seconds: number | null;
}

interface RawDashboard {
  today: string;
  doctor_id: string | null;
  doctor_name: string | null;
  branch_name: string | null;
  department_name: string | null;
  stats: RawStats;
}

interface RawQueueItem {
  visit_id: string;
  visit_number: string;
  queue_id: string | null;
  queue_number: string | null;
  patient_id: string;
  patient_name: string;
  patient_number: string;
  age: number | null;
  gender: string | null;
  priority: string;
  status: string;
  visit_type: string;
  arrival_time: string | null;
  called_time: string | null;
  consultation_start: string | null;
  waiting_seconds: number | null;
  is_locked: boolean;
  locked_by_name: string | null;
  locked_by_self: boolean;
}

interface RawLockInfo {
  locked: boolean;
  locked_by: string | null;
  locked_by_name: string | null;
  locked_at: string | null;
  is_self: boolean;
}

function toDashboard(raw: RawDashboard): DoctorDashboard {
  return {
    today: raw.today,
    doctorId: raw.doctor_id,
    doctorName: raw.doctor_name,
    branchName: raw.branch_name,
    departmentName: raw.department_name,
    stats: {
      waiting: raw.stats.waiting,
      called: raw.stats.called,
      serving: raw.stats.serving,
      completedToday: raw.stats.completed_today,
      cancelled: raw.stats.cancelled,
      noShow: raw.stats.no_show,
      avgConsultationSeconds: raw.stats.avg_consultation_seconds,
    },
  };
}

function toQueueItem(raw: RawQueueItem): DoctorQueueItem {
  return {
    visitId: raw.visit_id,
    visitNumber: raw.visit_number,
    queueId: raw.queue_id,
    queueNumber: raw.queue_number,
    patientId: raw.patient_id,
    patientName: raw.patient_name,
    patientNumber: raw.patient_number,
    age: raw.age,
    gender: raw.gender,
    priority: raw.priority,
    status: raw.status,
    visitType: raw.visit_type,
    arrivalTime: raw.arrival_time,
    calledTime: raw.called_time,
    consultationStart: raw.consultation_start,
    waitingSeconds: raw.waiting_seconds,
    isLocked: raw.is_locked,
    lockedByName: raw.locked_by_name,
    lockedBySelf: raw.locked_by_self,
  };
}

function toLockInfo(raw: RawLockInfo): LockInfo {
  return {
    locked: raw.locked,
    lockedBy: raw.locked_by,
    lockedByName: raw.locked_by_name,
    lockedAt: raw.locked_at,
    isSelf: raw.is_self,
  };
}

export const doctorWorkspaceApi = {
  getDashboard: async (doctorId?: string): Promise<DoctorDashboard> => {
    const qs = doctorId ? `?doctor_id=${encodeURIComponent(doctorId)}` : "";
    const raw = await apiClient.get<RawDashboard>(`/doctor-workspace/dashboard${qs}`);
    return toDashboard(raw);
  },
  getQueue: async (doctorId?: string): Promise<DoctorQueueItem[]> => {
    const qs = doctorId ? `?doctor_id=${encodeURIComponent(doctorId)}` : "";
    const raw = await apiClient.get<{ items: RawQueueItem[]; total: number }>(`/doctor-workspace/queue${qs}`);
    return raw.items.map(toQueueItem);
  },
  // Item 8: typed to `{ queue_number }` (backend `VisitDetail.queue_number`)
  // so the caller can pass the actual queue number to the TTS announcer.
  call: (visitId: string) => apiClient.post<{ queue_number: string | null }>(`/doctor-workspace/visits/${visitId}/call`),
  recall: (visitId: string) => apiClient.post<{ queue_number: string | null }>(`/doctor-workspace/visits/${visitId}/recall`),
  startConsultation: (visitId: string) => apiClient.post(`/doctor-workspace/visits/${visitId}/start-consultation`),
  completeConsultation: (visitId: string) => apiClient.post(`/doctor-workspace/visits/${visitId}/complete-consultation`),
  noShow: (visitId: string) => apiClient.post(`/doctor-workspace/visits/${visitId}/no-show`),
  cancel: (visitId: string, reason?: string) => apiClient.post(`/doctor-workspace/visits/${visitId}/cancel`, { reason }),
  openVisit: async (visitId: string): Promise<LockInfo> => {
    const raw = await apiClient.post<RawLockInfo>(`/doctor-workspace/visits/${visitId}/open`);
    return toLockInfo(raw);
  },
  releaseLock: async (visitId: string): Promise<LockInfo> => {
    const raw = await apiClient.post<RawLockInfo>(`/doctor-workspace/visits/${visitId}/release-lock`);
    return toLockInfo(raw);
  },
  // Item 14: Doctor Session Control.
  getSessionStatus: (doctorId?: string) => {
    const qs = doctorId ? `?doctor_id=${encodeURIComponent(doctorId)}` : "";
    return apiClient.get<{ active: boolean; started_at: string | null }>(`/doctor-workspace/session${qs}`);
  },
  startSession: (doctorId?: string) => {
    const qs = doctorId ? `?doctor_id=${encodeURIComponent(doctorId)}` : "";
    return apiClient.post<{ active: boolean; started_at: string | null }>(`/doctor-workspace/session/start${qs}`);
  },
  endSession: (doctorId?: string) => {
    const qs = doctorId ? `?doctor_id=${encodeURIComponent(doctorId)}` : "";
    return apiClient.post<{ active: boolean; started_at: string | null }>(`/doctor-workspace/session/end${qs}`);
  },
  nextPatient: (doctorId?: string) => {
    const qs = doctorId ? `?doctor_id=${encodeURIComponent(doctorId)}` : "";
    return apiClient.post(`/doctor-workspace/next-patient${qs}`);
  },
};
