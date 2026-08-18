import { apiClient } from "@/lib/api-client";
import type { MedicalCertificate, MedicalCertificateDraftInput } from "@/features/clinical-orders/types";

/* eslint-disable @typescript-eslint/no-explicit-any -- raw snake_case wire shape */

function toMedicalCertificate(raw: any): MedicalCertificate {
  return {
    id: raw.id,
    consultationId: raw.consultation_id,
    visitId: raw.visit_id,
    patientId: raw.patient_id,
    doctorId: raw.doctor_id,
    certificateNumber: raw.certificate_number,
    certificateType: raw.certificate_type,
    status: raw.status,
    findings: raw.findings,
    recommendation: raw.recommendation,
    restDays: raw.rest_days,
    dateFrom: raw.date_from,
    dateTo: raw.date_to,
    notes: raw.notes,
    issuedAt: raw.issued_at,
    cancelledAt: raw.cancelled_at,
    cancelledReason: raw.cancelled_reason,
    cancelledBy: raw.cancelled_by,
    supersededById: raw.superseded_by_id,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
    patientName: raw.patient_name,
    patientAge: raw.patient_age,
    patientSex: raw.patient_sex,
    doctorName: raw.doctor_name,
    doctorPrcLicense: raw.doctor_prc_license,
    doctorPtrNumber: raw.doctor_ptr_number,
    clinicName: raw.clinic_name,
    clinicLogoUrl: raw.clinic_logo_url,
    clinicAddress: raw.clinic_address,
    clinicLicenseNumber: raw.clinic_license_number,
    visitNumber: raw.visit_number,
    doctorSignatureSnapshotUrl: raw.doctor_signature_snapshot_url ?? null,
  };
}

function fromDraftInput(input: MedicalCertificateDraftInput) {
  return {
    certificate_type: input.certificateType,
    findings: input.findings ?? null,
    recommendation: input.recommendation ?? null,
    rest_days: input.restDays ?? null,
    date_from: input.dateFrom ?? null,
    date_to: input.dateTo ?? null,
    notes: input.notes ?? null,
  };
}

export const medicalCertificateApi = {
  createDraft: async (consultationId: string, input: MedicalCertificateDraftInput): Promise<MedicalCertificate> => {
    const raw = await apiClient.post<any>(`/consultations/${consultationId}/medical-certificates`, fromDraftInput(input));
    return toMedicalCertificate(raw);
  },
  updateDraft: async (certificateId: string, input: Partial<MedicalCertificateDraftInput>): Promise<MedicalCertificate> => {
    // Partial patch - only send keys the caller actually set, so an
    // omitted field is left alone server-side (`exclude_unset` on the
    // backend) instead of being overwritten with null.
    const payload: Record<string, unknown> = {};
    if (input.certificateType !== undefined) payload.certificate_type = input.certificateType;
    if (input.findings !== undefined) payload.findings = input.findings;
    if (input.recommendation !== undefined) payload.recommendation = input.recommendation;
    if (input.restDays !== undefined) payload.rest_days = input.restDays;
    if (input.dateFrom !== undefined) payload.date_from = input.dateFrom;
    if (input.dateTo !== undefined) payload.date_to = input.dateTo;
    if (input.notes !== undefined) payload.notes = input.notes;
    const raw = await apiClient.patch<any>(`/medical-certificates/${certificateId}`, payload);
    return toMedicalCertificate(raw);
  },
  issue: async (certificateId: string): Promise<MedicalCertificate> => {
    const raw = await apiClient.post<any>(`/medical-certificates/${certificateId}/issue`);
    return toMedicalCertificate(raw);
  },
  cancel: async (certificateId: string, reason: string): Promise<MedicalCertificate> => {
    const raw = await apiClient.post<any>(`/medical-certificates/${certificateId}/cancel`, { reason });
    return toMedicalCertificate(raw);
  },
  reissue: async (certificateId: string, reason: string): Promise<MedicalCertificate> => {
    const raw = await apiClient.post<any>(`/medical-certificates/${certificateId}/reissue`, { reason });
    return toMedicalCertificate(raw);
  },
  recordPrint: async (certificateId: string): Promise<void> => {
    await apiClient.post<any>(`/medical-certificates/${certificateId}/print`);
  },
  get: async (certificateId: string): Promise<MedicalCertificate> => {
    const raw = await apiClient.get<any>(`/medical-certificates/${certificateId}`);
    return toMedicalCertificate(raw);
  },
  listForConsultation: async (consultationId: string): Promise<MedicalCertificate[]> => {
    const raw = await apiClient.get<any[]>(`/consultations/${consultationId}/medical-certificates`);
    return raw.map(toMedicalCertificate);
  },
  listForVisit: async (visitId: string): Promise<MedicalCertificate[]> => {
    const raw = await apiClient.get<any[]>(`/visits/${visitId}/medical-certificates`);
    return raw.map(toMedicalCertificate);
  },
  listForPatient: async (patientId: string): Promise<MedicalCertificate[]> => {
    const raw = await apiClient.get<any[]>(`/patients/${patientId}/medical-certificates`);
    return raw.map(toMedicalCertificate);
  },
};
