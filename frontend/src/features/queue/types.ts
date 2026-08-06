/**
 * Domain types for Reception & Queue Management, mirroring the backend's
 * `schemas/queue.py` / `models/queue.py`.
 */

export enum QueuePriority {
  Normal = "Normal",
  SeniorCitizen = "SeniorCitizen",
  PWD = "PWD",
  Pregnant = "Pregnant",
  Emergency = "Emergency",
  VIP = "VIP",
}

export enum QueueStatus {
  Waiting = "Waiting",
  Called = "Called",
  Serving = "Serving",
  Completed = "Completed",
  Skipped = "Skipped",
  Cancelled = "Cancelled",
  NoShow = "NoShow",
}

export const QUEUE_PRIORITY_LABELS: Record<QueuePriority, string> = {
  [QueuePriority.Normal]: "Normal",
  [QueuePriority.SeniorCitizen]: "Senior Citizen",
  [QueuePriority.PWD]: "PWD",
  [QueuePriority.Pregnant]: "Pregnant",
  [QueuePriority.Emergency]: "Emergency",
  [QueuePriority.VIP]: "VIP",
};

export const QUEUE_STATUS_LABELS: Record<QueueStatus, string> = {
  [QueueStatus.Waiting]: "Waiting",
  [QueueStatus.Called]: "Called",
  [QueueStatus.Serving]: "Serving",
  [QueueStatus.Completed]: "Completed",
  [QueueStatus.Skipped]: "Skipped",
  [QueueStatus.Cancelled]: "Cancelled",
  [QueueStatus.NoShow]: "No Show",
};

/** Allowed forward transitions per current status - mirrors backend
 * `QUEUE_STATUS_TRANSITIONS`, used to only render legal action buttons. */
export const QUEUE_STATUS_TRANSITIONS: Record<QueueStatus, QueueStatus[]> = {
  [QueueStatus.Waiting]: [QueueStatus.Called, QueueStatus.Cancelled, QueueStatus.Skipped, QueueStatus.NoShow],
  [QueueStatus.Called]: [
    QueueStatus.Serving,
    QueueStatus.Skipped,
    QueueStatus.NoShow,
    QueueStatus.Cancelled,
    QueueStatus.Waiting,
  ],
  [QueueStatus.Serving]: [QueueStatus.Completed, QueueStatus.Cancelled],
  [QueueStatus.Completed]: [],
  [QueueStatus.Skipped]: [QueueStatus.Waiting],
  [QueueStatus.Cancelled]: [],
  [QueueStatus.NoShow]: [QueueStatus.Waiting],
};

export interface QueueStatusHistoryEntry {
  id: string;
  fromStatus: QueueStatus | null;
  toStatus: QueueStatus;
  changedBy: string | null;
  changedAt: string;
  note: string | null;
}

export interface QueueListItem {
  id: string;
  queueNumber: string;
  queueDate: string;
  priority: QueuePriority;
  status: QueueStatus;
  branchId: string;
  departmentId: string;
  departmentName: string | null;
  doctorId: string | null;
  doctorName: string | null;
  serviceId: string;
  serviceName: string | null;
  patientId: string;
  patientName: string | null;
  patientNumber: string | null;
  createdAt: string;
  calledAt: string | null;
  /** Phase 20 (items 4-5): the visit this ticket is linked to, needed so
   * Reception can open `/visits/{id}/consultation/open-for-reception` to
   * enter Subjective/Objective/vitals directly from the Queue screen. */
  visitId: string | null;
}

export interface QueueDetail extends QueueListItem {
  clinicId: string;
  queuePrefix: string;
  notes: string | null;
  servingStartedAt: string | null;
  completedAt: string | null;
  createdBy: string | null;
  updatedBy: string | null;
  updatedAt: string;
  branchName: string | null;
  history: QueueStatusHistoryEntry[];
}

export interface QueueSlip {
  queueId: string;
  queueNumber: string;
  clinicName: string;
  branchName: string;
  patientName: string;
  departmentName: string;
  doctorName: string | null;
  serviceName: string;
  priority: QueuePriority;
  queueDate: string;
  createdAt: string;
  qrToken: string;
}

export interface QueueListParams {
  search?: string;
  branchId?: string;
  departmentId?: string;
  doctorId?: string;
  status?: QueueStatus;
  priority?: QueuePriority;
  queueDate?: string;
  page?: number;
  pageSize?: number;
}

export interface CreateQueueInput {
  patientId: string;
  branchId: string;
  departmentId: string;
  doctorId?: string | null;
  serviceId: string;
  priority: QueuePriority;
  notes?: string;
  // Phase 21 (Vitals-before-Queue): when set, attaches this ticket to an
  // existing `DraftVitals` Visit (created via `visitsApi.createPreQueue`)
  // instead of creating a new Visit - required for Consultation/Follow-up
  // services, ignored/rejected server-side for everything else.
  visitId?: string | null;
}

export interface UpdateQueueInput {
  departmentId?: string;
  doctorId?: string | null;
  serviceId?: string;
  priority?: QueuePriority;
  notes?: string;
}

/** Live event payloads pushed over `/ws/queues/{clinicId}`. */
export type QueueWsEvent =
  | { event: "queue.created"; data: QueueDetail }
  | { event: "queue.updated"; data: QueueDetail }
  | { event: "queue.status_changed"; data: QueueDetail };
