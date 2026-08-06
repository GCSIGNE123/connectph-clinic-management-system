/**
 * Domain types for the Doctor Workspace (Phase 7), mirroring the backend's
 * `schemas/doctor_workspace.py`.
 */

export interface DoctorDashboardStats {
  waiting: number;
  called: number;
  serving: number;
  completedToday: number;
  cancelled: number;
  noShow: number;
  avgConsultationSeconds: number | null;
}

export interface DoctorDashboard {
  today: string;
  doctorId: string | null;
  doctorName: string | null;
  branchName: string | null;
  departmentName: string | null;
  stats: DoctorDashboardStats;
}

export interface DoctorQueueItem {
  visitId: string;
  visitNumber: string;
  queueId: string | null;
  queueNumber: string | null;
  patientId: string;
  patientName: string;
  patientNumber: string;
  age: number | null;
  gender: string | null;
  priority: string;
  status: string;
  visitType: string;
  arrivalTime: string | null;
  calledTime: string | null;
  consultationStart: string | null;
  waitingSeconds: number | null;
  isLocked: boolean;
  lockedByName: string | null;
  lockedBySelf: boolean;
}

export interface LockInfo {
  locked: boolean;
  lockedBy: string | null;
  lockedByName: string | null;
  lockedAt: string | null;
  isSelf: boolean;
}

export interface DoctorWsEvent {
  event: string;
  data: Record<string, unknown>;
}
