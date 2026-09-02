import type { LaboratoryOrder, LaboratoryResult } from "@/features/laboratory/types";

/** Phase 4G: one printable row per template parameter, carrying every
 * matching `LaboratoryResult` (usually exactly one - MORE than one only
 * for a `requiresSite` parameter like KOH Mount, where each site's result
 * shares the same `parameterName` but must stay visually distinct, never
 * collapsed/overwritten - see `upsert_results`' no-uniqueness-constraint
 * storage this relies on). Never test-name-specific: driven entirely by
 * `order.template.parameters` (already `display_order`-sorted by the
 * backend relationship) and matched to `order.results` purely by
 * `parameterName` (case-insensitive), the same convention
 * `_apply_resolved_range_to_result` uses server-side. */
export interface LaboratoryReportRow {
  parameterName: string;
  section: string | null;
  results: LaboratoryResult[];
  // The matching template parameter's configured Categorical choice list -
  // only ever populated for a templated order (an untemplated result has no
  // parameter definition to read this from). Carried here purely so the
  // report can decide compact-vs-full layout per row without re-fetching
  // the template - see `isQualitativeCategoricalRow` below.
  options?: string[] | null;
}

export function buildReportRows(order: LaboratoryOrder): LaboratoryReportRow[] {
  const resultsByName = new Map<string, LaboratoryResult[]>();
  for (const result of order.results) {
    const key = result.parameterName.trim().toLowerCase();
    const existing = resultsByName.get(key);
    if (existing) {
      existing.push(result);
    } else {
      resultsByName.set(key, [result]);
    }
  }

  if (order.template) {
    return order.template.parameters
      .map((parameter) => ({
        parameterName: parameter.parameterName,
        section: parameter.section ?? null,
        results: resultsByName.get(parameter.parameterName.trim().toLowerCase()) ?? [],
        options: parameter.options ?? null,
      }))
      .filter((row) => row.results.length > 0);
  }

  // Untemplated order (test_type matched no active template): no template
  // means no defined order/section to respect - list results exactly as
  // stored, one row each, no section grouping invented. `options` is
  // unknown here (no parameter definition available), so these rows never
  // qualify for the compact categorical layout - they keep the existing
  // full rendering, same as before this change.
  return order.results.map((result) => ({
    parameterName: result.parameterName,
    section: null,
    results: [result],
    options: null,
  }));
}

/** Qualitative Positive/Negative (or any configured-options) Categorical
 * report layout signal - deliberately the EXACT SAME gate
 * `ResultEntryDialog`'s simplified data-entry UI already uses
 * (`resultType === "Categorical" && options.length > 0`), not a new rule
 * and not a test-name check. A Categorical parameter with no configured
 * options (e.g. Urinalysis's Color/Protein, still awaiting Administrator
 * configuration) does NOT qualify - it keeps the existing full-grid
 * report layout, since there is nothing indicating it's a simple
 * qualitative result until an Administrator configures it, matching the
 * result-entry side's own "never invent a constraint that wasn't
 * configured" rule. Every result on the row must agree (a `requiresSite`
 * row's multiple per-site results all share the same parameter/options). */
export function isQualitativeCategoricalRow(row: LaboratoryReportRow): boolean {
  return (
    Boolean(row.options && row.options.length > 0) &&
    row.results.length > 0 &&
    row.results.every((r) => r.resultType === "Categorical")
  );
}

/** Contiguous grouping by `section` - identical convention to
 * `ResultEntryDialog`'s `groupBySection`: a section header is only shown
 * once per contiguous run, and a template with no sections at all (CBC,
 * Blood Typing) produces a single unheaded group. */
export function groupReportRowsBySection(
  rows: LaboratoryReportRow[]
): { section: string | null; rows: LaboratoryReportRow[] }[] {
  const groups: { section: string | null; rows: LaboratoryReportRow[] }[] = [];
  for (const row of rows) {
    const last = groups[groups.length - 1];
    if (last && last.section === row.section) {
      last.rows.push(row);
    } else {
      groups.push({ section: row.section, rows: [row] });
    }
  }
  return groups;
}

/** Type-aware value rendering, driven entirely by `resultType` - never a
 * parameter/test-name check. Titer/Microscopy render from `textValue`
 * exactly like Text (Phase 4E: neither has a dedicated storage shape).
 * Categorical reads the Phase 3 `{"value": ...}` convention. Returns null
 * (never "-") when a result exists but genuinely has no value to show -
 * the caller decides how to represent that, e.g. Blank. */
export function reportResultValue(result: LaboratoryResult): string | null {
  switch (result.resultType) {
    case "Numeric":
      return result.numericValue === null ? null : String(result.numericValue);
    case "Categorical":
      return (result.structuredValue?.value as string | undefined) ?? null;
    case "Text":
    case "Titer":
    case "Microscopy":
    default:
      return result.textValue ?? null;
  }
}

/** Client requirement: an overall category heading ("HEMATOLOGY TEST",
 * "SEROLOGY TEST", "BLOOD CHEMISTRY TEST", ...) between the patient/order
 * info block and the results content, for EVERY report - standard and
 * qualitative/matrix alike - even when no individual parameter has a
 * `section` configured. Sourced entirely from the template's own already-
 * existing `testCategory` field (Admin-configured on the Laboratory
 * Templates page, e.g. "Hematology") - no new field, no migration, and
 * never derived from `test_type`/`testName` (which is the specific test,
 * not its category). Distinct from and layered ABOVE
 * `groupReportRowsBySection`'s per-parameter subsection headings (e.g.
 * "Physical Examination") - this is the one overall heading for the whole
 * report; those remain untouched, nested beneath it.
 *
 * Returns null (never fabricates a placeholder) when there is nothing to
 * base a heading on - an untemplated order, or a template with no
 * `testCategory` configured - matching this module's "never invent a
 * constraint/label that wasn't configured" convention throughout.
 *
 * Normalizes "<category> TEST" without ever doubling an already-present
 * "TEST" suffix (e.g. a category literally configured as "Hematology
 * Test" still renders "HEMATOLOGY TEST", not "HEMATOLOGY TEST TEST").
 *
 * `adjacentLabel` is an optional de-duplication guard for the qualitative
 * matrix layout, which already prints the parent test name as its own
 * first cell/row label directly below this heading (see
 * `QualitativeResultMatrix`) - if the computed heading would be an exact
 * (case-insensitive) repeat of that adjacent label, this returns null
 * rather than printing the same text twice in a row. Callers building a
 * standard (non-matrix) report simply omit this argument - there is no
 * equivalent adjacent-duplicate risk there. */
export function buildCategoryHeading(
  testCategory: string | null | undefined,
  adjacentLabel?: string | null
): string | null {
  const trimmedCategory = (testCategory ?? "").trim();
  if (!trimmedCategory) return null;

  const upperCategory = trimmedCategory.toUpperCase();
  const heading = upperCategory.endsWith("TEST") ? upperCategory : `${upperCategory} TEST`;

  const trimmedAdjacent = (adjacentLabel ?? "").trim().toUpperCase();
  if (trimmedAdjacent && heading === trimmedAdjacent) return null;

  return heading;
}

/** Compact letter the report header displays for the backend's raw
 * `Gender` enum value ("Male"/"Female"/"Other") - the application's own
 * existing patient-sex values (see `PatientGender` in
 * `features/patients/types.ts`), never a new value invented for this
 * report. Falls through to the value itself for anything unrecognized
 * (defensive only - every value this app actually stores is listed here)
 * rather than silently dropping it. */
const SEX_LETTER: Record<string, string> = { Male: "M", Female: "F", Other: "O" };

/** Client requirement: the report header's "Age / Sex" row, e.g.
 * "22 yrs / M". `age` is the backend's already-computed
 * `LaboratoryOrderRead.patient_age` (see that field's own doc comment for
 * the "age as of today, from the patient's existing birth_date" convention
 * it follows - the same one `MedicalCertificateDetail.patient_age` already
 * established) - this function does no date math of its own, purely
 * formatting. `sex` is `patient_sex`, mapped through `SEX_LETTER` above.
 *
 * Missing-data handling (never fabricates either half): a present value
 * always renders normally; a missing one renders as "-" (this module's
 * existing convention - see `InfoRow`'s own `value ?? "-"` fallback) UNLESS
 * BOTH are missing, in which case the whole row collapses to a single "-"
 * rather than the redundant "- / -". */
export function buildAgeSexLine(age: number | null | undefined, sex: string | null | undefined): string {
  const ageText = typeof age === "number" && Number.isFinite(age) ? `${age} yrs` : null;
  const sexText = sex ? (SEX_LETTER[sex] ?? sex) : null;

  if (!ageText && !sexText) return "-";
  return `${ageText ?? "-"} / ${sexText ?? "-"}`;
}
