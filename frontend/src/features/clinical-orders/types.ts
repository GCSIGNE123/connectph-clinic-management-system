export type OrderCategory = "Laboratory" | "Radiology" | "Procedure" | "Referral" | "Vaccination" | "Custom";
export type OrderPriority = "Routine" | "STAT";
export type OrderStatus = "Requested" | "Collected" | "Processing" | "Completed" | "Cancelled";
export type PrescriptionStatus = "Draft" | "Finalized" | "Cancelled";

export type MedicalCertificateType = "MedicalCertificate" | "FitToWork" | "SickLeave" | "Custom";
export type MedicalCertificateStatus = "Draft" | "Issued" | "Cancelled";

export const MEDICAL_CERTIFICATE_TYPE_LABELS: Record<MedicalCertificateType, string> = {
  MedicalCertificate: "Medical Certificate",
  FitToWork: "Fit to Work",
  SickLeave: "Sick Leave",
  Custom: "Custom",
};

/** Sensible neutral default wording per certificate type, clearly isolated
 * here (not hardcoded inline in the form/print template) so it can be
 * adjusted later without touching component logic - explicitly NOT
 * authoritative legal wording, see `MedicalCertificateService`'s module
 * docstring. The doctor edits this before issuing either way. */
export const MEDICAL_CERTIFICATE_TEMPLATE_TEXT: Record<MedicalCertificateType, { findings: string; recommendation: string }> = {
  MedicalCertificate: {
    findings: "",
    recommendation: "This is to certify that the above-named patient was examined and treated at this clinic.",
  },
  FitToWork: {
    findings: "",
    recommendation: "This is to certify that the above-named patient is fit to return to work.",
  },
  SickLeave: {
    findings: "",
    recommendation: "This is to certify that the above-named patient is advised to rest for the period indicated below.",
  },
  Custom: { findings: "", recommendation: "" },
};

export interface MedicalCertificate {
  id: string;
  consultationId: string;
  visitId: string;
  patientId: string;
  doctorId: string;
  certificateNumber: string | null;
  certificateType: MedicalCertificateType;
  status: MedicalCertificateStatus;
  findings: string | null;
  recommendation: string | null;
  restDays: number | null;
  dateFrom: string | null;
  dateTo: string | null;
  notes: string | null;
  issuedAt: string | null;
  cancelledAt: string | null;
  cancelledReason: string | null;
  cancelledBy: string | null;
  supersededById: string | null;
  createdAt: string;
  updatedAt: string;
  // Live-pulled display fields - never stored on the row itself, see
  // `MedicalCertificateService._to_detail` on the backend.
  patientName: string | null;
  patientAge: number | null;
  patientSex: string | null;
  doctorName: string | null;
  doctorPrcLicense: string | null;
  doctorPtrNumber: string | null;
  clinicName: string | null;
  clinicLogoUrl: string | null;
  clinicAddress: string | null;
  clinicLicenseNumber: string | null;
  visitNumber: string | null;
}

export interface MedicalCertificateDraftInput {
  certificateType: MedicalCertificateType;
  findings?: string | null;
  recommendation?: string | null;
  restDays?: number | null;
  dateFrom?: string | null;
  dateTo?: string | null;
  notes?: string | null;
}

export interface OrderItem {
  id: string;
  itemName: string;
  itemCategory?: string | null;
  examType?: string | null;
  bodyPart?: string | null;
  clinicalIndication?: string | null;
}

export interface Order {
  id: string;
  consultationId: string;
  visitId: string;
  patientId: string;
  doctorId: string | null;
  orderNumber: string;
  orderCategory: OrderCategory;
  priority: OrderPriority;
  scheduledDate?: string | null;
  clinicalNotes?: string | null;
  status: OrderStatus;
  createdAt: string;
  items: OrderItem[];
}

export interface Procedure {
  id: string;
  consultationId: string;
  visitId: string;
  doctorId: string | null;
  procedureName: string;
  procedureDate?: string | null;
  notes?: string | null;
  status: OrderStatus;
  createdAt: string;
}

export interface Referral {
  id: string;
  consultationId: string;
  visitId: string;
  doctorId: string | null;
  referredTo: string;
  reason?: string | null;
  notes?: string | null;
  status: OrderStatus;
  createdAt: string;
}

export interface PrescriptionItem {
  id: string;
  medicine: string;
  genericName?: string | null;
  brandName?: string | null;
  strength?: string | null;
  dosage?: string | null;
  frequency?: string | null;
  duration?: string | null;
  quantity?: string | null;
  route?: string | null;
  instructions?: string | null;
  substitutionAllowed: boolean;
}

export interface Prescription {
  id: string;
  consultationId: string;
  visitId: string;
  patientId: string;
  doctorId: string | null;
  prescriptionNumber: string;
  status: PrescriptionStatus;
  createdAt: string;
  items: PrescriptionItem[];
}

export interface PrescriptionItemInput {
  medicine: string;
  genericName?: string | null;
  brandName?: string | null;
  strength?: string | null;
  dosage?: string | null;
  frequency?: string | null;
  duration?: string | null;
  quantity?: string | null;
  route?: string | null;
  instructions?: string | null;
  substitutionAllowed: boolean;
}

export interface OrderItemInput {
  itemName: string;
  itemCategory?: string | null;
  examType?: string | null;
  bodyPart?: string | null;
  clinicalIndication?: string | null;
}

/** Client-side, non-blocking validation for prescription line items -
 * duplicate medicine (case-insensitive), missing dosage, missing duration.
 * Mirrors `ClinicalOrdersService._validate_prescription_items` on the
 * backend (which is the source of truth / also runs server-side), so the
 * doctor sees the same warnings before submitting. */
export function validatePrescriptionItems(items: PrescriptionItemInput[]): string[] {
  const warnings: string[] = [];
  const seen = new Map<string, number>();
  for (const item of items) {
    const name = (item.medicine || "").trim().toLowerCase();
    if (name) seen.set(name, (seen.get(name) ?? 0) + 1);
    if (!item.dosage) warnings.push(`Missing dosage for '${item.medicine || ""}'.`);
    if (!item.duration) warnings.push(`Missing duration for '${item.medicine || ""}'.`);
  }
  for (const [name, count] of seen) {
    if (count > 1) warnings.push(`Duplicate medicine entry: '${name}' appears ${count} times.`);
  }
  return warnings;
}

/** Small, clearly-non-authoritative common-medicines list for the
 * Medication Search autocomplete convenience feature - NOT a real
 * formulary. Free text entry always remains possible. */
export const COMMON_MEDICINES: string[] = [
  "Paracetamol", "Ibuprofen", "Amoxicillin", "Cefalexin", "Azithromycin",
  "Metformin", "Losartan", "Amlodipine", "Atorvastatin", "Omeprazole",
  "Cetirizine", "Loratadine", "Salbutamol", "Mefenamic Acid", "Ascorbic Acid",
  "Multivitamins", "Loperamide", "Oral Rehydration Salts", "Co-Amoxiclav", "Ciprofloxacin",
  "Metronidazole", "Hydrocortisone Cream", "Diphenhydramine", "Dextromethorphan", "Guaifenesin",
  "Clopidogrel", "Simvastatin", "Insulin (Regular)", "Tranexamic Acid", "Tramadol",
];
