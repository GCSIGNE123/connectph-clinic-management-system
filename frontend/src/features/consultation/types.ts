/**
 * Domain types for Clinical Consultation / SOAP (Phase 8), mirroring
 * `schemas/consultation.py`.
 */

import type { LockInfo } from "@/features/doctor-workspace/types";
import type { WorkspaceConfig } from "@/features/clinic-config/types";

export type ConsultationStatus = "Draft" | "InProgress" | "Completed" | "Signed";
export type DiagnosisType = "Primary" | "Secondary";
export type DiagnosisStatus = "Working" | "Final";
export type AttachmentType = "ClinicalImage" | "PDF" | "ReferralLetter";

export interface SoapNote {
  id: string;
  consultationId: string;
  chiefComplaint: string | null;
  historyOfPresentIllness: string | null;
  pastMedicalHistory: string | null;
  familyHistory: string | null;
  socialHistory: string | null;
  reviewOfSystems: string | null;
  subjectiveNotes: string | null;
  bloodPressure: string | null;
  pulseRate: number | null;
  respiratoryRate: number | null;
  temperature: number | null;
  heightCm: number | null;
  weightKg: number | null;
  bmi: number | null;
  oxygenSaturation: number | null;
  painScore: number | null;
  headCircumferenceCm: number | null;
  physicalExamination: string | null;
  clinicalFindings: string | null;
  clinicalImpression: string | null;
  differentialDiagnosis: string | null;
  assessmentNotes: string | null;
  treatmentPlan: string | null;
  patientInstructions: string | null;
  followupRecommendation: string | null;
  referralNotes: string | null;
  updatedAt: string;
}

export type SoapNoteInput = Omit<SoapNote, "id" | "consultationId" | "bmi" | "updatedAt">;

export interface Diagnosis {
  id: string;
  consultationId: string;
  diagnosisType: DiagnosisType;
  status: DiagnosisStatus;
  notes: string | null;
  icd10Code: string | null;
  icd10Description: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ConsultationAttachment {
  id: string;
  consultationId: string;
  attachmentType: AttachmentType;
  fileName: string;
  fileUrl: string;
  fileSizeBytes: number | null;
  createdAt: string;
}

export interface Consultation {
  id: string;
  visitId: string;
  branchId: string;
  doctorId: string;
  patientId: string;
  status: ConsultationStatus;
  startedAt: string;
  completedAt: string | null;
  signedAt: string | null;
  doctorName: string | null;
  doctorPrcLicense: string | null;
  doctorPtrNumber: string | null;
  // Fully resolved (never null) - see `resolve_workspace_config` on the
  // backend. Drives which consultation sections render for THIS doctor.
  doctorWorkspaceConfig: WorkspaceConfig;
  patientName: string | null;
  patientNumber: string | null;
  visitNumber: string | null;
  soapNote: SoapNote | null;
  diagnoses: Diagnosis[];
  attachments: ConsultationAttachment[];
  lock: LockInfo;
}
