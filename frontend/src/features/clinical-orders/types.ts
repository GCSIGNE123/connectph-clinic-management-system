export type OrderCategory = "Laboratory" | "Radiology" | "Procedure" | "Referral" | "Vaccination" | "Custom";
export type OrderPriority = "Routine" | "STAT";
export type OrderStatus = "Requested" | "Collected" | "Processing" | "Completed" | "Cancelled";
export type PrescriptionStatus = "Draft" | "Finalized" | "Cancelled";

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
