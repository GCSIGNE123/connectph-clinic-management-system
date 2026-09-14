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
  // parameter definition to read this from). Retained for callers that need
  // template metadata; report layout is determined from the actual stored
  // result values by `isQualitativeCategoricalRow` below.
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
  // qualify for the compact categorical layout unless the stored result
  // values themselves are a complete Positive/Negative set.
  return order.results.map((result) => ({
    parameterName: result.parameterName,
    section: null,
    results: [result],
    options: null,
  }));
}

/** Compact qualitative report layout for tests whose actual stored results
 * are all categorical Positive/Negative values. This deliberately uses the
 * RESULT VALUE, not merely `options` metadata, so other Categorical tests
 * such as Blood Typing (A/B/AB/O) do not get mislabeled as a
 * Positive/Negative report. It also fixes legacy/older templates that have
 * Categorical results but no `options` array attached to the returned
 * parameter metadata - the report format is based on what is actually
 * printed (Positive/Negative), not on whether the configuration UI has a
 * choice list.
 *
 * Every result in the row must be Categorical and resolve to exactly one of
 * Positive or Negative (case-insensitive, surrounding whitespace ignored).
 * A mixed row, a blank value, or any other categorical value remains on the
 * normal five-column report layout. */
export function isQualitativeCategoricalRow(row: LaboratoryReportRow): boolean {
  if (row.results.length === 0) return false;
  return row.results.every((result) => {
    if (result.resultType !== "Categorical") return false;
    const value = reportResultValue(result)?.trim().toLowerCase();
    return value === "positive" || value === "negative";
  });
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
/** Medtech feedback (real A4 print review): these categories are already
 * the complete, standard term the clinic itself uses - unlike every other
 * category here (Hematology -> "HEMATOLOGY TEST", Blood Chemistry ->
 * "BLOOD CHEMISTRY TEST", ...), which the medtech has NOT asked to change,
 * the clinic doesn't write "Fecalysis Test" or "Urinalysis Test". An
 * explicit, named exception list (not a name/pattern guess) so adding the
 * next one stays a one-line, evidence-backed change. */
const BARE_CATEGORY_HEADINGS = new Set(["FECALYSIS", "URINALYSIS"]);

export function buildCategoryHeading(
  testCategory: string | null | undefined,
  adjacentLabel?: string | null
): string | null {
  const trimmedCategory = (testCategory ?? "").trim();
  if (!trimmedCategory) return null;

  const upperCategory = trimmedCategory.toUpperCase();
  const heading = upperCategory.endsWith("TEST") || BARE_CATEGORY_HEADINGS.has(upperCategory)
    ? upperCategory
    : `${upperCategory} TEST`;

  const trimmedAdjacent = (adjacentLabel ?? "").trim().toUpperCase();
  if (trimmedAdjacent && heading === trimmedAdjacent) return null;

  return heading;
}

/** Per-clinic manual-report reference (2026-09): the clinic's own existing
 * paper reports do NOT use one universal table for every test - Hematology
 * uses a 5-column PARAMETER/RESULT/UNIT/REFERENCE/REMARKS table, while
 * Blood Chemistry/Thyroid-PSA/Clotting-Bleeding-Time use a compact 3-column
 * TEST/RESULT/REFERENCE table with the unit folded into the REFERENCE text
 * instead of its own column, and a test with no configured unit/range at
 * all (Stool Examination, Gram Stain) uses a bare TEST/RESULT table with no
 * reference column at all. This is decided PER SECTION from the section's
 * OWN actual result data - never a test-name/category string match beyond
 * the one explicit "Hematology" signal below - so a future template needs
 * zero code changes to render correctly, exactly like the rest of this
 * module's existing convention.
 *
 * "detailed" requires BOTH the template's own `testCategory` containing
 * "Hematology" AND at least one Numeric result in this section - the
 * category alone is not enough (Clotting/Bleeding Time is also categorized
 * "Hematology" but its results are Text, and the clinic's own manual
 * report for it uses the compact 3-column layout, not the 5-column one -
 * see the "compact" fallback below). A Numeric result with no configured
 * unit still renders in "detailed" mode with a blank Unit cell (never
 * fabricating one) - unit presence gates only that one cell's content, not
 * which layout the whole section gets.
 *
 * "compact" is any section with at least one result carrying a
 * `normalRange` or `units` value to show in a REFERENCE column.
 *
 * "plain" is a section where no result has anything to put in a REFERENCE
 * column at all - matches the clinic's own Stool Examination/Gram Stain
 * paper reports, which have no reference/unit column whatsoever. */
export type SectionLayoutMode = "detailed" | "compact" | "plain";

export function resolveSectionLayoutMode(testCategory: string | null | undefined, rows: LaboratoryReportRow[]): SectionLayoutMode {
  const isHematologyCategory = /hematology/i.test(testCategory ?? "");
  const hasNumericResult = rows.some((row) => row.results.some((r) => r.resultType === "Numeric"));
  if (isHematologyCategory && hasNumericResult) return "detailed";

  const isChemistryCategory = /chemistry/i.test(testCategory ?? "");
  // A bare `units` value with no `normalRange` (e.g. Stool Exam's "PUS
  // CELLS"/"RBC", configured with unit "/HPF" but no established range)
  // only counts as reference evidence for Chemistry - the clinic's own
  // Blood Chemistry paper reports print a bare unit like "mg/dL" even
  // without a cutoff (see FBS/RBS's Glucose Random), but its Parasitology
  // (Stool Exam) reports show no Reference column at all despite the same
  // bare-unit configuration. Every other category needs a real range.
  const hasRealRange = rows.some((row) => row.results.some((r) => !!r.normalRange?.trim()));
  const hasBareUnit = rows.some((row) => row.results.some((r) => !!r.units?.trim()));
  const hasAnyReference = hasRealRange || (isChemistryCategory && hasBareUnit);

  // A genuine interpretation value (Low/High/Abnormal) must never silently
  // disappear from the report just because its section isn't Hematology -
  // e.g. an untemplated/ad-hoc Categorical result flagged Abnormal, or any
  // future non-Chemistry category this project doesn't have a manual
  // sample for yet. The one deliberate exception is Chemistry: the
  // clinic's own paper Blood Chemistry/Thyroid-PSA reports never print a
  // flag column at all (see this module's Blood-Chemistry reference note)
  // - the interpretation stays computed and stored either way, it's simply
  // never shown there, matching the clinic's own convention exactly.
  const hasInterpretation = rows.some((row) => row.results.some((r) => !!r.interpretation));
  if (hasInterpretation && !isChemistryCategory) return "detailed";

  return hasAnyReference ? "compact" : "plain";
}

/** Medtech feedback (Trichomonas Vaginalis Mount / Gram Stain / Sputum
 * Exam, real A4 print review): the clinic's own "Miscellaneous Report"
 * family (KOH Mount, Gram Stain, Trichomonas, Sputum Exam, Fecal Occult
 * Blood, Urinalysis, beta-HCG - everything actually categorized "Clinical
 * Microscopy" in this project, confirmed against the live template data)
 * shows a SPECIMEN column, unlike the genuinely different SEROLOGY/
 * IMMUNOLOGY family (Dengue, HBsAg, VDRL, ...), which the clinic's own
 * matrix-format samples never show one for. One shared check (never a
 * test-name match) so both the single-row "plain" table and the single-row
 * qualitative matrix apply the exact same rule. */
export function isClinicalMicroscopyCategory(testCategory: string | null | undefined): boolean {
  return /clinical microscopy/i.test(testCategory ?? "");
}

/** REFERENCE-column text for "compact" mode: the persisted `normalRange`
 * text, with `units` appended only when `normalRange` doesn't already
 * contain it (most of this project's Blood Chemistry-style templates
 * already bake the unit into their `normalRange` string, e.g.
 * "70-105 mg/dL" - appending again would duplicate it; a template that
 * stores a bare numeric range with the unit only in its separate `units`
 * field, e.g. Urinalysis's "0 - 5" + "/HPF", gets the unit appended so it
 * is never silently dropped). Falls back to whichever of the two is
 * actually present, and to "" (never invented) when neither is. */
export function compactReferenceValue(result: LaboratoryResult): string {
  const range = result.normalRange?.trim() ?? "";
  const unit = result.units?.trim() ?? "";
  if (range && unit) {
    return range.toLowerCase().includes(unit.toLowerCase()) ? range : `${range} ${unit}`;
  }
  return range || unit;
}

const MALE_FEMALE_RANGE_RE = /^(male\s*:?\s*.+?)\s*\/\s*(female\s*:?\s*.+)$/i;

/** Medtech feedback (Triglycerides, real A4 print review): a Male/Female
 * range (e.g. "Male: 60-165 / Female: 40-140 mg/dL") must never print as
 * one run-on line ("dli lng e one liner arun dli libog kitaon" - don't
 * make it one line, it's confusing to read) - each sex gets its own line.
 * Applies to every Blood-Chemistry-style test with this pattern (medtech:
 * "Apply to all lab tests nga naay Male and Female reference"), detected
 * from the stored text itself, never a test-name list. The unit is stored
 * only once, trailing the Female segment (e.g. "...40-140 mg/dL") - it's
 * stripped off first and then repeated on BOTH lines, matching the
 * medtech's own handwritten example ("Male : 60-165 mg/dL" / "Female:
 * 40-140 mg/dL"), rather than leaving the Male line's unit only implicit.
 * Falls back to the existing single-line value for every other (non-M/F)
 * range, so this is purely additive for the compact-mode reference cell. */
export function compactReferenceLines(result: LaboratoryResult): string[] {
  const range = result.normalRange?.trim() ?? "";
  const unit = result.units?.trim() ?? "";
  if (!range) return unit ? [unit] : [];

  const rangeWithoutTrailingUnit =
    unit && range.toLowerCase().endsWith(unit.toLowerCase()) ? range.slice(0, range.length - unit.length).trim() : range;

  const match = rangeWithoutTrailingUnit.match(MALE_FEMALE_RANGE_RE);
  if (match) {
    const [, male, female] = match;
    return unit ? [`${male.trim()} ${unit}`, `${female.trim()} ${unit}`] : [male.trim(), female.trim()];
  }

  return [compactReferenceValue(result)];
}

/** Working assumption (Stool Exam, 2026-09): a "plain" section (see
 * `resolveSectionLayoutMode`) has no Reference column at all, but a result
 * with a configured `units` value (e.g. PUS CELLS/RBC's "/HPF") must not
 * silently lose that unit just because there's nowhere else to print it -
 * the clinic's own manual report shows it appended to the result itself
 * ("1-2 /HPF"), not in a separate column. Only ever called for "plain"
 * mode - "detailed"/"compact" already have their own Unit/Reference cell
 * for this. Skips appending if the raw value already contains the unit
 * text, same de-dup convention as `compactReferenceValue`. */
export function plainResultValue(result: LaboratoryResult): string | null {
  const value = reportResultValue(result);
  const unit = result.units?.trim() ?? "";
  if (!value || !unit) return value;
  return value.toLowerCase().includes(unit.toLowerCase()) ? value : `${value} ${unit}`;
}

/** Compact letter the report header displays for the backend's raw
 * `Gender` enum value ("Male"/"Female"/"Other") - the application's own
 * existing patient-sex values (see `PatientGender` in
 * `features/patients/types.ts`), never a new value invented for this
 * report. Falls through to the value itself for anything unrecognized
 * (defensive only - every value this app actually stores is listed here)
 * rather than silently dropping it. */
const SEX_LETTER: Record<string, string> = { Male: "M", Female: "F", Other: "O" };

/** Client requirement: the report header's "Age / Sex" row, e.g. "22 yrs / M".
 * `age` is the backend's already-computed
 * `LaboratoryOrderRead.patient_age` (see that field's own doc comment for
 * the "age as of today, from the patient's existing birth_date" convention
 * it follows - this function does no date math of its own, purely
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
