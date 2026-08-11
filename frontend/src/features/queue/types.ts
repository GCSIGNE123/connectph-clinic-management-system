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

/** Phase 2.7 (YAKAP Patient Classification): the PER-ENCOUNTER
 * classification of a queue ticket - NOT a queue prefix, does not affect
 * A/B/L/R numbering. Separate from `Patient.isYakapBeneficiary` (the
 * patient's standing beneficiary status). */
export enum VisitClassification {
  Yakap = "Yakap",
  Regular = "Regular",
}

export const VISIT_CLASSIFICATION_LABELS: Record<VisitClassification, string> = {
  [VisitClassification.Yakap]: "YAKAP",
  [VisitClassification.Regular]: "Regular",
};

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
  visitClassification: VisitClassification;
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
  /** Whether this ticket's linked visit already has every required vitals
   * field recorded - drives the "Enter Vitals" button's color on the
   * Reception Queue table (taken vs. not yet taken). False when there's no
   * linked visit at all. */
  vitalsTaken: boolean;
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
  /** Reception Queue Workflow Improvements: same room-label resolution TV
   * Display uses, so a Receptionist's Call/Re-announce speaks the same
   * "...proceed to Room X" destination as the public display, instead of a
   * hardcoded room. Null when no room override is configured. */
  roomName: string | null;
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
  /** Feature 2: always true when a slip is actually returned - printing is
   * blocked server-side (400) before this point if vitals are missing. */
  vitalsTaken: boolean;
}

export interface QueueListParams {
  search?: string;
  branchId?: string;
  departmentId?: string;
  doctorId?: string;
  status?: QueueStatus;
  priority?: QueuePriority;
  visitClassification?: VisitClassification;
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
  // Phase 2.7 (YAKAP Patient Classification): defaults to Regular server-side
  // when omitted. The frontend pre-fills this from the selected patient's
  // `isYakapBeneficiary` flag but the receptionist may override it per ticket.
  visitClassification?: VisitClassification;
}

export interface UpdateQueueInput {
  departmentId?: string;
  doctorId?: string | null;
  serviceId?: string;
  priority?: QueuePriority;
  notes?: string;
  visitClassification?: VisitClassification;
}

/** Live event payloads pushed over `/ws/queues/{clinicId}`. */
export type QueueWsEvent =
  | { event: "queue.created"; data: QueueDetail }
  | { event: "queue.updated"; data: QueueDetail }
  | { event: "queue.status_changed"; data: QueueDetail };
