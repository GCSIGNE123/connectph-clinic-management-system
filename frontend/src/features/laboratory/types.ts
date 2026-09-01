export type LaboratoryOrderStatus =
  | "Requested"
  | "Collected"
  | "Processing"
  | "Completed"
  | "Released"
  | "Cancelled";

// Phase 3: Categorical added (Blood Typing's ABO Group/Rh Factor). Microscopy/
// Titer already exist on the backend (Phase 2A) but have no dedicated UI yet -
// listed here only for type accuracy against the real API shape, not implemented.
export type LaboratoryResultType = "Numeric" | "Text" | "Categorical" | "Microscopy" | "Titer";
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
  // Phase 3: Categorical (and future Microscopy) result payload - e.g.
  // {"value": "O"} for a Blood Typing ABO Group result. Null for
  // Numeric/Text results, unchanged.
  structuredValue: Record<string, unknown> | null;
  // Phase 4D: the specimen site this result was taken from (e.g. "Skin",
  // "Vaginal") - only meaningful when the parameter's `requiresSite` is
  // true (e.g. KOH Mount). Null for every other result, unchanged.
  site: string | null;
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
  // Phase 3: see LaboratoryResult.structuredValue above.
  structuredValue?: Record<string, unknown> | null;
  // Phase 4D: see LaboratoryResult.site above.
  site?: string | null;
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
  // null for a walk-in Laboratory queue ticket with no linked Order.
  orderId: string | null;
  orderNumber: string | null;
  visitId: string;
  visitNumber: string | null;
  queueNumber: string | null;
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
  // Phase 4G: report/print header branding - only populated by `getOrder`
  // (the single-order fetch the report view uses), null everywhere else
  // (listOrders/listForVisit/listForPatient/collect/etc.), unchanged.
  clinicName?: string | null;
  // Round 5 (report header contact info): same additive/GET-order-only
  // convention as `clinicName` above - existing `Clinic.address`/`city`/
  // `province`/`telephone`/`mobile`/`email` columns, joined server-side.
  clinicAddress?: string | null;
  clinicPhone?: string | null;
  clinicEmail?: string | null;
  // Round 7: the shared clinic branding logo (Clinic Settings -> Branding),
  // same additive/GET-order-only convention as `clinicName` above. Live
  // configuration, not a release-time snapshot - see the Round 7
  // implementation report.
  clinicLogoUrl?: string | null;
  // Round 6 (Laboratory Report Signatories): captured ONCE at release,
  // never re-resolved on reprint - see `LaboratoryOrder`'s backend model
  // docstring. All `null` on an order that hasn't been released yet, or
  // was released with no Pathologist selected / no signature configured
  // at that moment (never fabricated).
  pathologistId?: string | null;
  medTechNameSnapshot?: string | null;
  medTechLicenseSnapshot?: string | null;
  medTechSignatureSnapshotUrl?: string | null;
  pathologistNameSnapshot?: string | null;
  pathologistLicenseSnapshot?: string | null;
  pathologistSignatureSnapshotUrl?: string | null;
  // Phase 4I: optimistic-concurrency token - `ResultEntryDialog` echoes
  // this back as `expectedUpdatedAt` on save (see `enterResults` below),
  // so a save based on a stale snapshot (someone else saved first) is
  // rejected (409) instead of silently overwriting their changes.
  updatedAt: string;
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
  // Phase 3: a Categorical parameter's fixed choice list (e.g.
  // ["A","B","AB","O"]) - the frontend renders whatever this array
  // contains, never a hard-coded option set. Null/absent for Numeric/Text.
  options?: string[] | null;
  // Phase 4A: generic display-grouping label (e.g. "Physical Examination")
  // - null for templates/parameters with no natural sections (CBC, Blood
  // Typing). Phase 4B groups Result Entry rows by this field.
  section?: string | null;
  // Phase 4D: flags a parameter whose result needs a specimen site
  // captured per entry (e.g. KOH Mount "per site") - default false, so
  // every existing parameter is unaffected. Drives whether Result Entry
  // shows a generic site input, never a test-specific one.
  requiresSite?: boolean;
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

// --- Template Import/Export (bulk Excel maintenance) ---

export interface LaboratoryTemplateImportIssue {
  severity: "error" | "warning";
  sheet: string;
  row: number;
  template: string | null;
  parameter: string | null;
  reason: string;
}

export interface LaboratoryTemplateParameterDiff {
  added: string[];
  changed: string[];
  removed: string[];
  unchanged: string[];
}

export interface LaboratoryTemplateDiff {
  templateId: string | null;
  testName: string;
  action: "create" | "update";
  parameters: LaboratoryTemplateParameterDiff;
}

export interface LaboratoryTemplateImportPreview {
  templateCount: number;
  parameterCount: number;
  newTemplateCount: number;
  updatedTemplateCount: number;
  errors: LaboratoryTemplateImportIssue[];
  warnings: LaboratoryTemplateImportIssue[];
  diffs: LaboratoryTemplateDiff[];
  canCommit: boolean;
}

export interface LaboratoryTemplateImportResult {
  createdTemplateCount: number;
  updatedTemplateCount: number;
  parameterCount: number;
  templateNames: string[];
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
  // Qualitative/Categorical simplification: a Categorical result's value
  // (e.g. "Positive") - mirrors the backend's `categorical_value` param on
  // `interpret_result()`. Undefined/omitted for every non-Categorical call
  // site, unchanged.
  categoricalValue?: string | null;
}): LaboratoryInterpretation | null {
  const { resultType, numericValue, textValue, rangeLow, rangeHigh, expectedNormalText, categoricalValue } = params;

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

  if (resultType === "Categorical") {
    if (!expectedNormalText?.trim()) return null;
    if (!categoricalValue?.trim()) return null;
    return categoricalValue.trim().toLowerCase() === expectedNormalText.trim().toLowerCase() ? "Normal" : "Abnormal";
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
    // Phase 3: mirrors the backend's authoritative `_validate_categorical_value`
    // check (server-side is what actually enforces this) - this is only the
    // same "catch it before a round-trip" convenience the Numeric/Text checks
    // above already provide.
    if (row.resultType === "Categorical" && !row.structuredValue?.value) {
      warnings.push(`Missing selection for '${row.parameterName}'.`);
    }
  }
  // Phase 4H fix: a `requiresSite` parameter (e.g. KOH Mount) legitimately
  // submits several rows sharing one `parameterName`, differentiated only
  // by `site` - keying purely on name would flag that as a false
  // "duplicate". Dedupe on name+site instead, so a real duplicate (same
  // name, same site - including two site-less rows for a parameter that
  // isn't site-specific) is still caught.
  const seen = new Map<string, number>();
  for (const row of withNames) {
    const key = `${row.parameterName.trim().toLowerCase()}::${(row.site ?? "").trim().toLowerCase()}`;
    seen.set(key, (seen.get(key) ?? 0) + 1);
  }
  for (const [key, count] of seen) {
    if (count > 1) {
      const [name] = key.split("::");
      warnings.push(`Duplicate parameter entry: '${name}' appears ${count} times.`);
    }
  }
  return warnings;
}
