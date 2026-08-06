export type LaboratoryOrderStatus =
  | "Requested"
  | "Collected"
  | "Processing"
  | "Completed"
  | "Released"
  | "Cancelled";

export type LaboratoryResultType = "Numeric" | "Text";
export type LaboratoryInterpretation = "Normal" | "Low" | "High" | "Abnormal";

export interface LaboratoryResult {
  id: string;
  parameterName: string;
  resultType: LaboratoryResultType;
  numericValue: number | null;
  textValue: string | null;
  normalRange: string | null;
  units: string | null;
  interpretation: LaboratoryInterpretation | null;
  remarks: string | null;
  enteredBy: string | null;
  enteredAt: string | null;
}

export interface LaboratoryResultInput {
  parameterName: string;
  resultType: LaboratoryResultType;
  numericValue?: number | null;
  textValue?: string | null;
  normalRange?: string | null;
  units?: string | null;
  interpretation?: LaboratoryInterpretation | null;
  remarks?: string | null;
}

export interface LaboratoryAttachment {
  id: string;
  attachmentType: string;
  fileName: string;
  fileUrl: string;
  fileSizeBytes: number | null;
  uploadedBy: string | null;
  createdAt: string;
}

export interface LaboratoryOrder {
  id: string;
  orderId: string;
  orderNumber: string | null;
  visitId: string;
  visitNumber: string | null;
  patientId: string;
  patientName: string | null;
  doctorId: string | null;
  doctorName: string | null;
  templateId: string | null;
  testType: string;
  priority: string | null;
  status: LaboratoryOrderStatus;
  scheduledDate: string | null;
  collectedAt: string | null;
  collectedBy: string | null;
  processingStartedAt: string | null;
  completedAt: string | null;
  releasedAt: string | null;
  releasedBy: string | null;
  invoiceItemId: string | null;
  createdAt: string;
  results: LaboratoryResult[];
  attachments: LaboratoryAttachment[];
}

export interface LaboratoryDashboardStats {
  pending: number;
  collected: number;
  processing: number;
  completedToday: number;
  statOrders: number;
  cancelled: number;
}

export interface LaboratoryTemplateParameter {
  id?: string;
  parameterName: string;
  unit?: string | null;
  normalRange?: string | null;
  resultType: LaboratoryResultType;
  displayOrder?: number;
}

export interface LaboratoryTemplate {
  id: string;
  testName: string;
  testCategory: string | null;
  specimenType: string | null;
  defaultPrice: number;
  turnaroundTimeHours: number | null;
  isActive: boolean;
  parameters: LaboratoryTemplateParameter[];
  createdAt: string;
}

export const LAB_ORDER_STATUS_LABELS: Record<LaboratoryOrderStatus, string> = {
  Requested: "Requested",
  Collected: "Collected",
  Processing: "Processing",
  Completed: "Completed",
  Released: "Released",
  Cancelled: "Cancelled",
};

/** Contextual next action per status, matching the Laboratory Dashboard's
 * worklist action buttons. */
export function nextActionFor(status: LaboratoryOrderStatus): { label: string; action: "collect" | "process" | "results" | "release" } | null {
  switch (status) {
    case "Requested":
      return { label: "Collect Specimen", action: "collect" };
    case "Collected":
      return { label: "Start Processing", action: "process" };
    case "Processing":
      return { label: "Enter Results", action: "results" };
    case "Completed":
      return { label: "Release Results", action: "release" };
    default:
      return null;
  }
}

/** Client-side validation for the Result Entry form, mirroring the shape
 * of `validatePrescriptionItems` in `features/clinical-orders/types.ts`
 * (same-checks-both-sides pattern): every row needs a parameter name and a
 * value appropriate to its `resultType` (numeric rows need a numeric
 * value, text rows need non-empty text). Returns a list of human-readable
 * warnings; an empty list means the form is submittable. */
export function validateResultRows(rows: LaboratoryResultInput[]): string[] {
  const warnings: string[] = [];
  const withNames = rows.filter((r) => r.parameterName.trim().length > 0);
  if (withNames.length === 0) {
    warnings.push("At least one result parameter is required.");
    return warnings;
  }
  for (const row of withNames) {
    if (row.resultType === "Numeric" && (row.numericValue === null || row.numericValue === undefined)) {
      warnings.push(`Missing numeric value for '${row.parameterName}'.`);
    }
    if (row.resultType === "Text" && !row.textValue?.trim()) {
      warnings.push(`Missing text value for '${row.parameterName}'.`);
    }
  }
  const seen = new Map<string, number>();
  for (const row of withNames) {
    const key = row.parameterName.trim().toLowerCase();
    seen.set(key, (seen.get(key) ?? 0) + 1);
  }
  for (const [name, count] of seen) {
    if (count > 1) warnings.push(`Duplicate parameter entry: '${name}' appears ${count} times.`);
  }
  return warnings;
}
