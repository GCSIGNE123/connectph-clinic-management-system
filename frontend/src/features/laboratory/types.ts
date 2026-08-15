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
  // Feature 3: structured numeric bounds, denormalized from the template
  // parameter at submission time (same pattern as normalRange/units).
  rangeLow: number | null;
  rangeHigh: number | null;
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
  rangeLow?: number | null;
  rangeHigh?: number | null;
  // Transient only - used server-side to compute `interpretation` for
  // qualitative (Text) results, never persisted on LaboratoryResult.
  expectedNormalText?: string | null;
}

// Feature 4: matches backend `LaboratoryAttachmentType` exactly. The new
// upload control (Result Entry workflow) only ever sends "Image" - the
// other two members exist for schema completeness/future use (e.g. a
// scanned PDF report), same as the backend endpoint's conditional
// validation.
export type LaboratoryAttachmentType = "PDFReport" | "Image" | "ScannedResult";

export interface LaboratoryAttachment {
  id: string;
  attachmentType: LaboratoryAttachmentType;
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
  // Feature 3: the linked template's full definition (with per-parameter
  // ranges), letting Result Entry pre-populate rows in a single fetch.
  // Null when no template is linked, unchanged from before.
  template: LaboratoryTemplate | null;
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
  // Feature 3: structured, optional. Numeric parameters use
  // rangeLow/rangeHigh; qualitative (Text) parameters use
  // expectedNormalText. Left unset, auto-interpretation never activates
  // for that parameter - see `interpretResult` below.
  rangeLow?: number | null;
  rangeHigh?: number | null;
  expectedNormalText?: string | null;
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

/** Feature 3: client-side mirror of the backend's pure
 * `interpret_result()` (app/services/laboratory_interpretation.py) - used
 * for live, per-keystroke interpretation preview in Result Entry without a
 * server round-trip. Must stay behaviorally identical to the backend
 * function; the backend's computation on submit is always authoritative. */
export function interpretResult(params: {
  resultType: LaboratoryResultType;
  numericValue: number | null | undefined;
  textValue: string | null | undefined;
  rangeLow: number | null | undefined;
  rangeHigh: number | null | undefined;
  expectedNormalText: string | null | undefined;
}): LaboratoryInterpretation | null {
  const { resultType, numericValue, textValue, rangeLow, rangeHigh, expectedNormalText } = params;

  if (resultType === "Numeric") {
    if (rangeLow === null || rangeLow === undefined || rangeHigh === null || rangeHigh === undefined) return null;
    if (numericValue === null || numericValue === undefined || Number.isNaN(numericValue)) return null;
    if (numericValue < rangeLow) return "Low";
    if (numericValue > rangeHigh) return "High";
    return "Normal";
  }

  if (resultType === "Text") {
    if (!expectedNormalText?.trim()) return null;
    if (!textValue?.trim()) return null;
    return textValue.trim().toLowerCase() === expectedNormalText.trim().toLowerCase() ? "Normal" : "Abnormal";
  }

  return null;
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
