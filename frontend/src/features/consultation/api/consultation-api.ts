import { apiClient } from "@/lib/api-client";
import type { LockInfo } from "@/features/doctor-workspace/types";
import type {
  Consultation,
  ConsultationAttachment,
  Diagnosis,
  SoapNote,
  SoapNoteInput,
  AttachmentType,
} from "@/features/consultation/types";

/* eslint-disable @typescript-eslint/no-explicit-any -- raw snake_case wire shapes */

function toSoapNote(raw: any): SoapNote {
  return {
    id: raw.id,
    consultationId: raw.consultation_id,
    chiefComplaint: raw.chief_complaint,
    historyOfPresentIllness: raw.history_of_present_illness,
    pastMedicalHistory: raw.past_medical_history,
    familyHistory: raw.family_history,
    socialHistory: raw.social_history,
    reviewOfSystems: raw.review_of_systems,
    subjectiveNotes: raw.subjective_notes,
    bloodPressure: raw.blood_pressure,
    pulseRate: raw.pulse_rate,
    respiratoryRate: raw.respiratory_rate,
    temperature: raw.temperature,
    heightCm: raw.height_cm,
    weightKg: raw.weight_kg,
    bmi: raw.bmi,
    oxygenSaturation: raw.oxygen_saturation,
    painScore: raw.pain_score,
    headCircumferenceCm: raw.head_circumference_cm,
    physicalExamination: raw.physical_examination,
    clinicalFindings: raw.clinical_findings,
    clinicalImpression: raw.clinical_impression,
    differentialDiagnosis: raw.differential_diagnosis,
    assessmentNotes: raw.assessment_notes,
    treatmentPlan: raw.treatment_plan,
    patientInstructions: raw.patient_instructions,
    followupRecommendation: raw.followup_recommendation,
    referralNotes: raw.referral_notes,
    updatedAt: raw.updated_at,
  };
}

function toDiagnosis(raw: any): Diagnosis {
  return {
    id: raw.id,
    consultationId: raw.consultation_id,
    diagnosisType: raw.diagnosis_type,
    status: raw.status,
    notes: raw.notes,
    icd10Code: raw.icd10_code,
    icd10Description: raw.icd10_description,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

function toAttachment(raw: any): ConsultationAttachment {
  return {
    id: raw.id,
    consultationId: raw.consultation_id,
    attachmentType: raw.attachment_type,
    fileName: raw.file_name,
    fileUrl: raw.file_url,
    fileSizeBytes: raw.file_size_bytes,
    createdAt: raw.created_at,
  };
}

function toLockInfo(raw: any): LockInfo {
  return {
    locked: raw.locked,
    lockedBy: raw.locked_by,
    lockedByName: raw.locked_by_name,
    lockedAt: raw.locked_at,
    isSelf: raw.is_self,
  };
}

function toConsultation(raw: any): Consultation {
  return {
    id: raw.id,
    visitId: raw.visit_id,
    branchId: raw.branch_id,
    doctorId: raw.doctor_id,
    patientId: raw.patient_id,
    status: raw.status,
    startedAt: raw.started_at,
    completedAt: raw.completed_at,
    signedAt: raw.signed_at,
    doctorName: raw.doctor_name,
    patientName: raw.patient_name,
    patientNumber: raw.patient_number,
    visitNumber: raw.visit_number,
    soapNote: raw.soap_note ? toSoapNote(raw.soap_note) : null,
    diagnoses: (raw.diagnoses ?? []).map(toDiagnosis),
    attachments: (raw.attachments ?? []).map(toAttachment),
    lock: toLockInfo(raw.lock),
  };
}

function fromSoapNoteInput(input: Partial<SoapNoteInput>) {
  return {
    chief_complaint: input.chiefComplaint ?? null,
    history_of_present_illness: input.historyOfPresentIllness ?? null,
    past_medical_history: input.pastMedicalHistory ?? null,
    family_history: input.familyHistory ?? null,
    social_history: input.socialHistory ?? null,
    review_of_systems: input.reviewOfSystems ?? null,
    subjective_notes: input.subjectiveNotes ?? null,
    blood_pressure: input.bloodPressure ?? null,
    pulse_rate: input.pulseRate ?? null,
    respiratory_rate: input.respiratoryRate ?? null,
    temperature: input.temperature ?? null,
    height_cm: input.heightCm ?? null,
    weight_kg: input.weightKg ?? null,
    oxygen_saturation: input.oxygenSaturation ?? null,
    pain_score: input.painScore ?? null,
    head_circumference_cm: input.headCircumferenceCm ?? null,
    physical_examination: input.physicalExamination ?? null,
    clinical_findings: input.clinicalFindings ?? null,
    clinical_impression: input.clinicalImpression ?? null,
    differential_diagnosis: input.differentialDiagnosis ?? null,
    assessment_notes: input.assessmentNotes ?? null,
    treatment_plan: input.treatmentPlan ?? null,
    patient_instructions: input.patientInstructions ?? null,
    followup_recommendation: input.followupRecommendation ?? null,
    referral_notes: input.referralNotes ?? null,
  };
}

export const consultationApi = {
  openForVisit: async (visitId: string): Promise<Consultation> => {
    const raw = await apiClient.post<any>(`/visits/${visitId}/consultation/open`);
    return toConsultation(raw);
  },
  getForVisit: async (visitId: string): Promise<Consultation | null> => {
    const raw = await apiClient.get<any>(`/visits/${visitId}/consultation`);
    return raw ? toConsultation(raw) : null;
  },
  getById: async (consultationId: string): Promise<Consultation> => {
    const raw = await apiClient.get<any>(`/consultations/${consultationId}`);
    return toConsultation(raw);
  },
  saveSoap: async (consultationId: string, payload: Partial<SoapNoteInput>): Promise<Consultation> => {
    const raw = await apiClient.put<any>(`/consultations/${consultationId}/soap`, fromSoapNoteInput(payload));
    return toConsultation(raw);
  },
  addDiagnosis: async (
    consultationId: string,
    payload: { diagnosisType: string; status: string; notes?: string | null; icd10Code?: string | null; icd10Description?: string | null }
  ): Promise<Consultation> => {
    const raw = await apiClient.post<any>(`/consultations/${consultationId}/diagnoses`, {
      diagnosis_type: payload.diagnosisType,
      status: payload.status,
      notes: payload.notes ?? null,
      icd10_code: payload.icd10Code ?? null,
      icd10_description: payload.icd10Description ?? null,
    });
    return toConsultation(raw);
  },
  completeConsultation: async (consultationId: string, consultationFee?: number | null): Promise<Consultation> => {
    // Phase 20 (item 9): optional fee override that flows into the
    // auto-created invoice's Consultation Fee line item - omitting it
    // preserves the pre-Phase-20 Doctor.consultation_fee/Service-price
    // behavior exactly.
    const body = consultationFee != null ? { consultation_fee: consultationFee } : undefined;
    const raw = await apiClient.post<any>(`/consultations/${consultationId}/complete`, body);
    return toConsultation(raw);
  },
  signConsultation: async (consultationId: string): Promise<Consultation> => {
    const raw = await apiClient.post<any>(`/consultations/${consultationId}/sign`);
    return toConsultation(raw);
  },
  requestAttachmentUpload: async (
    consultationId: string,
    payload: { attachmentType: AttachmentType; fileName: string; fileSizeBytes?: number | null }
  ) => {
    return apiClient.post<{ id: string; upload_url: string; file_url: string; expires_in: number }>(
      `/consultations/${consultationId}/attachments`,
      { attachment_type: payload.attachmentType, file_name: payload.fileName, file_size_bytes: payload.fileSizeBytes ?? null }
    );
  },
  listAttachments: async (consultationId: string): Promise<ConsultationAttachment[]> => {
    const raw = await apiClient.get<any[]>(`/consultations/${consultationId}/attachments`);
    return raw.map(toAttachment);
  },
  // --- Phase 20 (items 3-5): Receptionist/Nurse Subjective/Objective entry ---
  openForReception: async (visitId: string): Promise<Consultation> => {
    const raw = await apiClient.post<any>(`/visits/${visitId}/consultation/open-for-reception`);
    return toConsultation(raw);
  },
  getSubjectiveObjective: async (consultationId: string) => {
    const raw = await apiClient.get<any>(`/consultations/${consultationId}/soap/subjective-objective`);
    return raw ? toSoapNote(raw) : null;
  },
  saveSubjectiveObjective: async (consultationId: string, payload: Partial<SoapNoteInput>): Promise<Consultation> => {
    const body = fromSoapNoteInput(payload);
    // Only Subjective/Objective keys are meaningful to this endpoint - the
    // backend schema (`SoapNoteSubjectiveObjectiveUpsert`) has no
    // Assessment/Plan fields at all, so sending them would be silently
    // dropped anyway, but we omit them here too for clarity.
    const {
      clinical_impression, differential_diagnosis, assessment_notes,
      treatment_plan, patient_instructions, followup_recommendation, referral_notes,
      ...subjectiveObjective
    } = body;
    void clinical_impression; void differential_diagnosis; void assessment_notes;
    void treatment_plan; void patient_instructions; void followup_recommendation; void referral_notes;
    const raw = await apiClient.put<any>(`/consultations/${consultationId}/soap/subjective-objective`, subjectiveObjective);
    return toConsultation(raw);
  },
};
