/**
 * Domain types for Visit (Encounter) Management, mirroring the backend's
 * `schemas/visit.py` / `models/visit.py`.
 */

export enum VisitType {
  WalkIn = "WalkIn",
  Appointment = "Appointment",
  FollowUp = "FollowUp",
  Emergency = "Emergency",
  Teleconsultation = "Teleconsultation",
  HomeService = "HomeService",
}

export enum VisitStatus {
  Registered = "Registered",
  Waiting = "Waiting",
  Called = "Called",
  InConsultation = "InConsultation",
  Completed = "Completed",
  Cancelled = "Cancelled",
  NoShow = "NoShow",
  // Phase 21 (Vitals-before-Queue): a "draft" Visit for a Consultation/
  // Follow-up service, created by Reception BEFORE a Queue ticket exists so
  // vitals can be captured first - see `NewQueueDialog`'s two-step flow.
  DraftVitals = "DraftVitals",
}

export enum VisitPriority {
  Normal = "Normal",
  SeniorCitizen = "SeniorCitizen",
  PWD = "PWD",
  Pregnant = "Pregnant",
  Emergency = "Emergency",
  VIP = "VIP",
}

export enum VisitTimelineEventType {
  Registered = "Registered",
  CheckedIn = "CheckedIn",
  Queued = "Queued",
  Called = "Called",
  ConsultationStarted = "ConsultationStarted",
  ConsultationFinished = "ConsultationFinished",
  CheckedOut = "CheckedOut",
  StatusChanged = "StatusChanged",
  Cancelled = "Cancelled",
  Note = "Note",
  ConsultationOpened = "ConsultationOpened",
  SoapSaved = "SoapSaved",
  DiagnosisAdded = "DiagnosisAdded",
  ConsultationCompleted = "ConsultationCompleted",
  ConsultationSigned = "ConsultationSigned",
  // Phase 9 - Clinical Orders & Prescriptions events, recorded on the same
  // visit-scoped timeline (see `features/clinical-orders/`).
  OrderCreated = "OrderCreated",
  ProcedureCreated = "ProcedureCreated",
  ReferralCreated = "ReferralCreated",
  PrescriptionCreated = "PrescriptionCreated",
}

export const VISIT_TYPE_LABELS: Record<VisitType, string> = {
  [VisitType.WalkIn]: "Walk-In",
  [VisitType.Appointment]: "Appointment",
  [VisitType.FollowUp]: "Follow-Up",
  [VisitType.Emergency]: "Emergency",
  [VisitType.Teleconsultation]: "Teleconsultation",
  [VisitType.HomeService]: "Home Service",
};

export const VISIT_STATUS_LABELS: Record<VisitStatus, string> = {
  [VisitStatus.Registered]: "Registered",
  [VisitStatus.Waiting]: "Waiting",
  [VisitStatus.Called]: "Called",
  [VisitStatus.InConsultation]: "In Consultation",
  [VisitStatus.Completed]: "Completed",
  [VisitStatus.Cancelled]: "Cancelled",
  [VisitStatus.NoShow]: "No Show",
  [VisitStatus.DraftVitals]: "Vitals In Progress",
};

export const VISIT_PRIORITY_LABELS: Record<VisitPriority, string> = {
  [VisitPriority.Normal]: "Normal",
  [VisitPriority.SeniorCitizen]: "Senior Citizen",
  [VisitPriority.PWD]: "PWD",
  [VisitPriority.Pregnant]: "Pregnant",
  [VisitPriority.Emergency]: "Emergency",
  [VisitPriority.VIP]: "VIP",
};

export const VISIT_TIMELINE_EVENT_LABELS: Record<VisitTimelineEventType, string> = {
  [VisitTimelineEventType.Registered]: "Visit registered",
  [VisitTimelineEventType.CheckedIn]: "Checked in",
  [VisitTimelineEventType.Queued]: "Added to queue",
  [VisitTimelineEventType.Called]: "Called",
  [VisitTimelineEventType.ConsultationStarted]: "Consultation started",
  [VisitTimelineEventType.ConsultationFinished]: "Consultation finished",
  [VisitTimelineEventType.CheckedOut]: "Checked out",
  [VisitTimelineEventType.StatusChanged]: "Status changed",
  [VisitTimelineEventType.Cancelled]: "Cancelled",
  [VisitTimelineEventType.Note]: "Note",
  [VisitTimelineEventType.ConsultationOpened]: "Consultation opened",
  [VisitTimelineEventType.SoapSaved]: "SOAP note saved",
  [VisitTimelineEventType.DiagnosisAdded]: "Diagnosis added",
  [VisitTimelineEventType.ConsultationCompleted]: "Consultation completed",
  [VisitTimelineEventType.ConsultationSigned]: "Consultation signed",
  [VisitTimelineEventType.OrderCreated]: "Order created",
  [VisitTimelineEventType.ProcedureCreated]: "Procedure created",
  [VisitTimelineEventType.ReferralCreated]: "Referral created",
  [VisitTimelineEventType.PrescriptionCreated]: "Prescription created",
};

/** Allowed forward transitions per current status - mirrors backend
 * `VISIT_STATUS_TRANSITIONS`, used to only render legal action buttons. */
export const VISIT_STATUS_TRANSITIONS: Record<VisitStatus, VisitStatus[]> = {
  [VisitStatus.DraftVitals]: [VisitStatus.Waiting, VisitStatus.Cancelled],
  [VisitStatus.Registered]: [VisitStatus.Waiting, VisitStatus.Cancelled, VisitStatus.NoShow],
  [VisitStatus.Waiting]: [VisitStatus.Called, VisitStatus.Cancelled, VisitStatus.NoShow],
  [VisitStatus.Called]: [VisitStatus.InConsultation, VisitStatus.Waiting, VisitStatus.Cancelled, VisitStatus.NoShow],
  [VisitStatus.InConsultation]: [VisitStatus.Completed, VisitStatus.Cancelled],
  [VisitStatus.Completed]: [],
  [VisitStatus.Cancelled]: [],
  [VisitStatus.NoShow]: [VisitStatus.Waiting],
};

export interface VisitTimelineEntry {
  id: string;
  visitId: string;
  eventType: VisitTimelineEventType;
  occurredAt: string;
  recordedBy: string | null;
  note: string | null;
  metadata: Record<string, unknown> | null;
}

export interface VisitListItem {
  id: string;
  visitNumber: string;
  visitDate: string;
  visitType: VisitType;
  status: VisitStatus;
  priority: VisitPriority;
  branchId: string;
  patientId: string;
  patientName: string | null;
  patientNumber: string | null;
  doctorId: string | null;
  doctorName: string | null;
  departmentId: string | null;
  departmentName: string | null;
  serviceId: string | null;
  serviceName: string | null;
  queueId: string | null;
  queueNumber: string | null;
  createdAt: string;
}

export interface VisitDetail extends VisitListItem {
  clinicId: string;
  arrivalTime: string | null;
  checkInTime: string | null;
  calledTime: string | null;
  consultationStart: string | null;
  consultationEnd: string | null;
  checkOutTime: string | null;
  remarks: string | null;
  createdBy: string | null;
  updatedBy: string | null;
  updatedAt: string;
  branchName: string | null;
  timeline: VisitTimelineEntry[];
}

export interface VisitListParams {
  search?: string;
  branchId?: string;
  patientId?: string;
  doctorId?: string;
  departmentId?: string;
  status?: VisitStatus;
  visitType?: VisitType;
  dateFrom?: string;
  dateTo?: string;
  page?: number;
  pageSize?: number;
}

export interface UpdateVisitInput {
  doctorId?: string | null;
  departmentId?: string;
  serviceId?: string;
  priority?: VisitPriority;
  remarks?: string;
}
